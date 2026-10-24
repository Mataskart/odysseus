"""Custom tools retain their contracts across upstream authority and transport layers."""
import json
from types import SimpleNamespace

import pytest

from src.agent_runtime.authority import ExactOperation, create_request_authority
from src.tool_execution import NO_TOOL_SECURITY_CONTEXT, execute_tool_block
from src.tool_policy import ToolPolicy
from src.tool_types import ToolBlock


@pytest.mark.asyncio
async def test_knowledge_dispatch_preserves_authority_and_authenticated_owner(monkeypatch):
    from src.tools import knowledge

    calls = []

    def search(query, *, k, owner, raise_on_error):
        calls.append((query, owner))
        return [{"id": "lecture", "document": "Conditioning", "similarity": .9,
                 "metadata": {"filename": "lecture.pdf"}}]

    monkeypatch.setattr(knowledge, "get_rag_manager", lambda: SimpleNamespace(healthy=True, search=search))
    authority = create_request_authority("Search my course materials for conditioning", owner="alice")
    _, result = await execute_tool_block(
        ToolBlock("search_knowledge", '{"query":"conditioning","owner":"bob"}'),
        owner="alice", security_context=NO_TOOL_SECURITY_CONTEXT, request_authority=authority,
    )
    assert result["exit_code"] == 0
    assert calls == [("conditioning", "alice")]
    assert json.loads(result["output"])["sources"][0]["id"] == "lecture"


@pytest.mark.parametrize("tool,text", [
    ("search_knowledge", "Search my course materials for conditioning"),
    ("openjev_judge", "Use OpenJev to count the people"),
    ("find_tools", "Find an available capability"),
])
def test_custom_tools_cannot_override_explicit_denial(tool, text):
    policy = ToolPolicy(disabled_tools=frozenset({tool}))
    authority = create_request_authority(text, policy=policy)
    assert not authority.permits(ExactOperation.normalize(tool, '{}'))


def test_discovery_does_not_grant_discovered_execution():
    authority = create_request_authority("Find an available capability")
    assert authority.permits(ExactOperation.normalize("find_tools", '{"query":"notes"}'))
    assert not authority.permits(ExactOperation.normalize("bash", 'rm anything'))


def test_declared_qwen_xml_tool_preserves_name_without_guessing():
    from src.tool_parsing import parse_tool_blocks

    text = '<tool_call><function=environment_lookup><parameter=query>term</parameter></function></tool_call>'
    assert parse_tool_blocks(text) == []
    blocks = parse_tool_blocks(text, additional_tool_names={"environment_lookup"})
    assert len(blocks) == 1
    assert blocks[0].tool_type == "environment_lookup"
    assert json.loads(blocks[0].content) == {"query": "term"}


def test_injected_user_message_does_not_replace_actual_request():
    from src.context_compactor import trim_for_context

    query = {"role": "user", "content": "Find the course deadline"}
    messages = [query, {"role": "assistant", "content": "old " * 10000},
                {"role": "user", "content": "retrieval diagnostic " * 200,
                 "_agent_injected": True}]
    trimmed = trim_for_context(messages, 2048, reserve_tokens=512)
    assert query in trimmed


@pytest.mark.asyncio
@pytest.mark.parametrize("forced", [False, True])
async def test_deferred_tools_stay_filtered_after_route_enrichment(monkeypatch, forced):
    import src.agent_loop as agent

    monkeypatch.setattr(agent, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(agent, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(agent, "blocked_tools_for_owner", lambda owner: set())
    monkeypatch.setattr(agent, "estimate_tokens", lambda *args, **kwargs: 10)
    monkeypatch.setattr(agent, "_build_system_prompt", lambda messages, *args, **kwargs: (messages, []))
    offered = []

    async def stream(*args, **kwargs):
        offered.extend(schema["function"]["name"] for schema in kwargs.get("tools") or [])
        yield 'data: {"delta":"The source is unavailable."}\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(agent, "stream_llm_with_fallback", stream)
    async for _ in agent.stream_agent_loop(
        "http://127.0.0.1:8010/v1", "Qwen3.8-verification",
        [{"role": "user", "content": "Run bash pwd."}],
        relevant_tools={"bash", "pipeline", "ask_teacher", "trigger_research", "manage_research"},
        forced_tools={"pipeline"} if forced else set(),
        max_rounds=1, log_turns=False, _is_teacher_run=True,
    ):
        pass
    assert "bash" in offered
    assert ("pipeline" in offered) is forced
    assert not {"ask_teacher", "trigger_research", "manage_research"} & set(offered)


def test_local_qwen_gguf_preserves_native_contract_and_sampling():
    from src import agent_loop, llm_core
    from src.model_profiles import GENERIC_TOOL_SCHEMA_PROFILE, tool_schema_profile

    model = "/models/Qwen3.8-35B-A3B-Odysseus-v2-imatrix-Q4_K_M.gguf"
    assert tool_schema_profile(model) == GENERIC_TOOL_SCHEMA_PROFILE
    assert not agent_loop._is_qwen38_tool_router(model)
    assert not agent_loop._is_odysseus_qwen_model(model)
    payload = {"temperature": 0.6, "max_tokens": 8192}
    llm_core._apply_local_generation_stability(payload, "http://127.0.0.1:8000/v1", model)
    assert payload == {"temperature": 0.6, "max_tokens": 8192}


@pytest.mark.asyncio
async def test_discovery_selection_cannot_widen_request_authority(monkeypatch):
    from src.turn_contract import active_turn_contract, bind_turn_contract, offer_discovered_tools, resolve_turn_contract
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS
    from src import tool_execution

    policy = ToolPolicy(disabled_tools=frozenset({"python"}))
    contract = resolve_turn_contract(capabilities={"knowledge"}, schemas=FUNCTION_TOOL_SCHEMAS, policy=policy)
    authority = create_request_authority("Search my course materials", owner="alice", policy=policy)
    with bind_turn_contract(contract):
        updated = offer_discovered_tools(contract, {"bash", "python", "not_real"}, FUNCTION_TOOL_SCHEMAS)
        assert active_turn_contract() is updated
        assert updated.permits("bash")
        assert not updated.permits("python")
        assert "not_real" not in updated.offered
        _, result = await tool_execution.execute_tool_block(
            ToolBlock("bash", "pwd"), owner="alice", security_context=NO_TOOL_SECURITY_CONTEXT,
            request_authority=authority,
        )
        assert result["failure_kind"] == "request_authority_denied"
    assert active_turn_contract() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("temperature", [0.6, 1.0])
async def test_v2_agent_request_keeps_native_tools_and_requested_sampling(monkeypatch, temperature):
    import src.agent_loop as agent

    monkeypatch.setattr(agent, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(agent, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(agent, "blocked_tools_for_owner", lambda owner: set())
    monkeypatch.setattr(agent, "estimate_tokens", lambda *args, **kwargs: 10)
    monkeypatch.setattr(agent, "_build_system_prompt", lambda messages, *args, **kwargs: (messages, []))
    requests = []

    async def stream(*args, **kwargs):
        requests.append(kwargs)
        yield 'data: {"delta":"The command is unavailable."}\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(agent, "stream_llm_with_fallback", stream)
    async for _ in agent.stream_agent_loop(
        "http://127.0.0.1:8010/v1", "/models/Qwen3.8-35B-A3B-Odysseus-v2-imatrix-Q4_K_M.gguf",
        [{"role": "user", "content": "Run bash pwd."}],
        relevant_tools={"bash"}, forced_tools={"bash"}, temperature=temperature, max_tokens=8192,
        max_rounds=1, log_turns=False, _is_teacher_run=True,
    ):
        pass
    assert len(requests) == 1
    assert "bash" in {schema["function"]["name"] for schema in requests[0]["tools"]}
    assert requests[0]["temperature"] == temperature
    assert requests[0]["max_tokens"] == 8192


def test_declared_direct_xml_stripping_preserves_surrounding_prose():
    from src.tool_parsing import strip_tool_blocks

    text = 'Before. <environment_lookup>{"query":"term"}</environment_lookup> After.'
    cleaned = strip_tool_blocks(text, additional_tool_names={"environment_lookup"})
    assert "Before." in cleaned and "After." in cleaned
    assert "environment_lookup" not in cleaned and "query" not in cleaned
