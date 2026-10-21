from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.chat_processor import ChatProcessor


def preface(monkeypatch, manager, *, enabled=True, history=None, text="find assessment dates in my files"):
    monkeypatch.setattr("src.rag_singleton.get_rag_manager", lambda: manager)
    processor = ChatProcessor(None, SimpleNamespace(rag_manager=None))
    messages, sources, _ = processor.build_context_preface(
        text, SimpleNamespace(history=history or []), use_rag=enabled,
        use_memory=False, use_skills=False, owner="ugne",
    )
    status = next(message["_retrieval_diagnostics"] for message in messages if "_retrieval_diagnostics" in message)
    return messages, sources, status


def test_recovers_from_missing_startup_manager(monkeypatch):
    manager = SimpleNamespace(search=Mock(return_value=[{
        "metadata": {"filename": "course.pdf"}, "document": "Assessment Oct 22", "similarity": .8,
    }]))
    messages, sources, status = preface(monkeypatch, manager)
    manager.search.assert_called_once_with("find assessment dates in my files", k=5, owner="ugne", raise_on_error=True)
    assert sources[0]["filename"] == "course.pdf"
    assert status["outcome"] == "retrieved"
    assert any("Assessment Oct 22" in m["content"] for m in messages)


@pytest.mark.parametrize("manager,enabled,outcome", [
    (None, True, "unavailable"), (None, False, "disabled"),
    (SimpleNamespace(search=lambda *a, **k: []), True, "no_matches"),
    (SimpleNamespace(search=lambda *a, **k: [{"similarity": .2}]), True, "below_threshold"),
])
def test_retrieval_outcomes_are_explicit(monkeypatch, manager, enabled, outcome):
    messages, sources, status = preface(monkeypatch, manager, enabled=enabled)
    assert status["outcome"] == outcome
    assert not sources
    assert any(outcome in m["content"] for m in messages)


def test_progress_check_searches_unresolved_objective(monkeypatch):
    manager = SimpleNamespace(search=Mock(return_value=[]))
    objective = "pasiek visus mana failus ir rask visu atsiskaitymu datas"
    preface(monkeypatch, manager, text="did you find?", history=[
        {"role": "user", "content": objective},
        {"role": "assistant", "content": "Pažiūrėsiu į tavo failus ir rasiu atsiskaitymų datas."},
    ])
    assert manager.search.call_args.args[0] == objective


def test_progress_check_preserves_pending_metadata_on_chat_messages(monkeypatch):
    manager = SimpleNamespace(search=Mock(return_value=[]))
    objective = "find assessment dates in my files"
    history = [
        SimpleNamespace(role="user", content=objective, metadata=None),
        SimpleNamespace(role="assistant", content="Search paused.", metadata={"pending_objective": objective}),
    ]
    preface(monkeypatch, manager, text="continue", history=history)
    assert manager.search.call_args.args[0] == objective


def test_singleton_serializes_lazy_initialization(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from src import rag_singleton, rag_vector
    manager = SimpleNamespace(healthy=True)
    create = Mock(return_value=manager)
    monkeypatch.setattr(rag_vector, "VectorRAG", create)
    monkeypatch.setattr(rag_singleton, "rag_instance", None)
    monkeypatch.setattr(rag_singleton, "_last_attempt", -100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: rag_singleton.get_rag_manager(), range(4)))
    assert results == [manager] * 4
    create.assert_called_once()


def test_singleton_retries_after_throttle(monkeypatch):
    from src import rag_singleton, rag_vector
    clock = [100.0]
    manager = SimpleNamespace(healthy=True)
    create = Mock(side_effect=[RuntimeError("offline"), manager])
    monkeypatch.setattr(rag_vector, "VectorRAG", create)
    monkeypatch.setattr(rag_singleton, "rag_instance", None)
    monkeypatch.setattr(rag_singleton, "_last_attempt", 0)
    monkeypatch.setattr(rag_singleton.time, "monotonic", lambda: clock[0])
    assert rag_singleton.get_rag_manager() is None
    assert rag_singleton.get_rag_manager() is None
    clock[0] += 31
    assert rag_singleton.get_rag_manager() is manager
    assert create.call_count == 2


def test_failed_collection_is_unavailable_instead_of_no_matches(monkeypatch):
    from src.rag_vector import VectorRAG
    rag = VectorRAG.__new__(VectorRAG)
    rag._healthy = True
    failed_collection = Mock()
    failed_collection.count.side_effect = RuntimeError("offline")
    rag._lanes = [SimpleNamespace(collection=failed_collection)]
    _, sources, status = preface(monkeypatch, rag)
    assert not sources
    assert status["outcome"] == "unavailable"
