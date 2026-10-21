import asyncio
import json
from types import SimpleNamespace

import pytest

from src.rag_vector import VectorRAG
from src.tools import knowledge
from src.tools.discovery import discover_tools
from src.agent_tools import FUNCTION_TOOL_SCHEMAS
from tests.helpers.embedding_lanes import FakeCollection, FakeEmbedder


@pytest.mark.parametrize("owner", ["matas", "ugne", "future_user"])
def test_tool_searches_shared_and_own_material_without_other_private_sources(monkeypatch, owner):
    collection = FakeCollection("knowledge-test")
    collection.add(
        ids=["course", "matas-private", "ugne-private", "ownerless"],
        embeddings=[[1.0]] * 4,
        documents=["conditioning course", "conditioning matas", "conditioning ugne", "conditioning ownerless"],
        metadatas=[
            {"owner": "matas", "visibility": "shared", "filename": "lecture.pdf"},
            {"owner": "matas"}, {"owner": "ugne"}, {},
        ],
    )
    rag = VectorRAG.__new__(VectorRAG)
    rag._healthy = True
    rag._lanes = [SimpleNamespace(
        name="fastembed", collection=collection,
        client=FakeEmbedder(1, "test", ""), count=collection.count,
        encode=lambda texts: [[1.0] for _ in texts],
    )]
    monkeypatch.setattr(knowledge, "get_rag_manager", lambda: rag)
    result = asyncio.run(knowledge.search_knowledge('{"query":"conditioning","owner":"other"}', owner=owner))
    sources = json.loads(result["output"])["sources"]
    expected = {"course"}
    if owner in {"matas", "ugne"}:
        expected.add(owner + "-private")
    assert {source["id"] for source in sources} == expected
    assert next(source for source in sources if source["id"] == "course")["filename"] == "lecture.pdf"


@pytest.mark.parametrize("owner", [None, "", " "])
def test_missing_owner_never_runs_unscoped_search(monkeypatch, owner):
    def unexpected():
        pytest.fail("Must not initialize an unscoped search")
    monkeypatch.setattr(knowledge, "get_rag_manager", unexpected)
    assert asyncio.run(knowledge.search_knowledge('{"query":"anything"}', owner=owner))["exit_code"] == 1


def test_moodle_discovery_prioritizes_content_search_over_bad_vector_matches(monkeypatch):
    index = SimpleNamespace(retrieve=lambda query, k: ["suggest_document", "glob", "list_downloads"])
    monkeypatch.setattr("src.tool_index.get_tool_index", lambda: index)
    _, result = asyncio.run(discover_tools(
        '{"query":"Moodle course materials, documents, files, search Moodle","limit":1}',
        FUNCTION_TOOL_SCHEMAS, set(),
    ))
    assert result["discovered_tools"] == ["search_knowledge"]
    _, disabled = asyncio.run(discover_tools(
        '{"query":"Moodle course materials","limit":5}', FUNCTION_TOOL_SCHEMAS, {"search_knowledge"},
    ))
    assert "search_knowledge" not in disabled["discovered_tools"]


def test_tool_unavailability_is_reported_without_filesystem_substitution(monkeypatch):
    monkeypatch.setattr(knowledge, "get_rag_manager", lambda: None)
    result = asyncio.run(knowledge.search_knowledge('{"query":"conditioning"}', owner="ugne"))
    assert result["exit_code"] == 1
    assert "unavailable" in result["error"]


def test_native_call_preserves_query_and_classifies_read_only():
    from src.tool_schemas import function_call_to_tool_block
    from src.tool_capabilities import capabilities_for_tool, ToolEffect
    from src.tool_security import PLAN_MODE_READONLY_TOOLS, NON_ADMIN_BLOCKED_TOOLS
    block = function_call_to_tool_block("search_knowledge", '{"query":"sąlyginis dirgiklis"}')
    assert block.tool_type == "search_knowledge"
    assert json.loads(block.content)["query"] == "sąlyginis dirgiklis"
    assert capabilities_for_tool("search_knowledge").effects == {ToolEffect.READ_PRIVATE}
    assert "search_knowledge" in PLAN_MODE_READONLY_TOOLS
    assert "search_knowledge" not in NON_ADMIN_BLOCKED_TOOLS
