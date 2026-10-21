import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import ChatMessage as DbChatMessage
from routes import session_routes
from routes.history import history_routes
from src import turn_log
from src.auth_helpers import require_chat_api_token_scope
from tests.test_history_display_model_hydration import _database, _seed_session


@pytest.fixture
def review(monkeypatch, tmp_path):
    engine, factory = _database()
    _seed_session(factory, session_id="owned")
    _seed_session(factory, session_id="other", message_count=0)
    monkeypatch.setattr(history_routes, "SessionLocal", factory)
    monkeypatch.setattr(session_routes, "SessionLocal", factory)
    monkeypatch.setattr(session_routes, "effective_user", lambda request: "alice")
    monkeypatch.setattr(turn_log, "logging_enabled", lambda: True)
    monkeypatch.setenv("ODYSSEUS_TURN_LOG_DIR", str(tmp_path))
    manager = SimpleNamespace(get_session=lambda sid: SimpleNamespace(
        history=[], model="test", endpoint_url="local", name="test"))
    app = FastAPI()
    app.dependency_overrides[require_chat_api_token_scope] = lambda: None
    app.include_router(history_routes.setup_history_routes(manager))
    yield TestClient(app), factory, tmp_path
    turn_log._writer.submit(lambda: None).result(timeout=10)
    engine.dispose()


def test_reload_pagination_and_fallback_restore_ids_without_metadata(review):
    client, _, _ = review
    for path in ["/api/history/owned?limit=2", "/api/history/owned?limit=2&offset=0", "/api/history/owned"]:
        result = client.get(path)
        assert result.status_code == 200
        rows = result.json()["history"]
        assert all(row["metadata"]["_db_id"] for row in rows)


@pytest.mark.parametrize("payload,status", [
    ({"session_id": "owned", "message_id": ""}, 400),
    ({"session_id": "owned", "message_id": "message-0"}, 404),
    ({"session_id": "other", "message_id": "missing"}, 404),
    ({"session_id": "owned", "message_id": "missing"}, 404),
])
def test_rejects_invalid_or_nonassistant_identity(review, payload, status):
    client, _, _ = review
    assert client.post("/api/turns/flag", json=payload).status_code == status


def test_flag_correlates_directly_to_persisted_reply_and_diagnostic_turn(review, monkeypatch):
    client, factory, folder = review
    import core.session_manager as sm
    from core.models import ChatMessage
    from core.session_manager import SessionManager
    monkeypatch.setattr(sm, "SessionLocal", factory)
    manager = SessionManager.__new__(SessionManager)
    manager.sessions = {}
    reply = ChatMessage("assistant", "Source answer", metadata={
        "turn_id": "stable-turn", "model": "actual-v2.gguf", "requested_model": "old.gguf",
        "effective_sampling": [{"sent": {"temperature": 1.0}}],
        "retrieval": {"outcome": "retrieved"},
    })
    manager._persist_message("owned", reply)
    message_id = reply.metadata["_db_id"]
    result = client.post("/api/turns/flag", json={"session_id": "owned", "message_id": message_id})
    assert result.json() == {"ok": True, "recorded": True, "status": "saved"}
    turn_log._writer.submit(lambda: None).result(timeout=10)
    flag = json.loads((folder / "flags.jsonl").read_text().splitlines()[-1])
    diagnostic = json.loads((folder / "turns.jsonl").read_text().splitlines()[-1])
    assert flag["turn_id"] == diagnostic["turn_id"] == "stable-turn"
    assert flag["message_id"] == diagnostic["diagnostics"]["message_id"] == message_id
    assert diagnostic["diagnostics"]["actual_model"] == "actual-v2.gguf"
    assert diagnostic["diagnostics"]["requested_model"] == "old.gguf"
    assert diagnostic["diagnostics"]["sampling"][0]["sent"]["temperature"] == 1.0


def test_logging_disabled_and_failed_write_never_report_saved(review, monkeypatch):
    client, _, folder = review
    monkeypatch.setattr(turn_log, "logging_enabled", lambda: False)
    payload = {"session_id": "owned", "message_id": "message-1"}
    assert client.post("/api/turns/flag", json=payload).json()["status"] == "logging_disabled"
    monkeypatch.setattr(turn_log, "logging_enabled", lambda: True)
    monkeypatch.setattr(turn_log.os, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk failure")))
    assert client.post("/api/turns/flag", json=payload).json() == {"ok": False, "recorded": False, "status": "write_failed"}
    assert not (folder / "flags.jsonl").exists()


def test_foreign_session_is_not_flaggable(review, monkeypatch):
    client, factory, _ = review
    from core.database import Session as DbSession
    db = factory()
    db.query(DbSession).filter(DbSession.id == "owned").update({"owner": "someone_else"})
    db.commit()
    db.close()
    result = client.post("/api/turns/flag", json={"session_id": "owned", "message_id": "message-1"})
    assert result.status_code == 404
