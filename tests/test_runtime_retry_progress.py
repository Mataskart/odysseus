import asyncio
import json

import pytest

import src.agent_loop as agent
from src.tool_loop_guard import RepeatedReadGuard
from src.tool_policy import known_tool_names


def empty(guard, pattern, **options):
    arguments = {"path": "/tmp/search-scope", "pattern": pattern, **options}
    guard.observe("grep", json.dumps(arguments), {"output": f"No matches for {pattern!r}", "exit_code": 0})


def test_narrower_literal_search_after_empty_broader_search_stops():
    guard = RepeatedReadGuard()
    empty(guard, "shipment")
    empty(guard, "shipment-reference")
    assert guard.stop == ("grep", "empty")
    assert "already exhausted" in guard.final_answer("Search files")


@pytest.mark.parametrize("first,second,first_options,second_options", [
    ("stale", "active", {}, {}),
    ("stale-123", "stale", {}, {}),
    ("stale", "stale-123", {}, {"path": "/tmp/another-scope"}),
    ("stale", "stale-123", {"glob": "*.md"}, {"glob": "*.txt"}),
    ("STALE", "STALE-123", {}, {"ignore_case": True}),
    ("a.b", "a.b-more", {}, {}),
    ("Straße", "strasse-extra", {"ignore_case": True}, {"ignore_case": True}),
])
def test_different_or_broader_searches_are_not_stopped(first, second, first_options, second_options):
    guard = RepeatedReadGuard()
    empty(guard, first, **first_options)
    empty(guard, second, **second_options)
    assert guard.stop is None


def test_changed_search_options_can_recover_before_guard_stops():
    guard = RepeatedReadGuard()
    empty(guard, "reference")
    guard.observe("grep", '{"pattern":"reference","ignore_case":true}',
                  {"output": "notes.txt:1:REFERENCE PK-7319", "exit_code": 0})
    assert guard.stop is None
    empty(guard, "reference")
    assert guard.stop is None


def test_search_case_and_result_limit_variations_do_not_hide_repeated_empty_query():
    guard = RepeatedReadGuard()
    empty(guard, "reference", max_results=10)
    empty(guard, "reference", ignore_case=True, max_results=50)
    assert guard.stop == ("grep", "empty")


@pytest.mark.parametrize("error", ["not found", "permission denied"])
def test_pagination_does_not_hide_repeated_failed_file(error):
    guard = RepeatedReadGuard()
    for offset in [1, 100]:
        guard.observe("read_file", json.dumps({"path": "/tmp/report", "offset": offset, "limit": 20}),
                      {"error": error, "exit_code": 1})
    assert guard.stop is not None


def test_distinct_failed_sources_only_get_one_notice_and_remain_recoverable():
    guard = RepeatedReadGuard()
    for index in range(5):
        guard.observe("read_file", f"/tmp/report-{index}", {"error": "not found"})
        if index < 2:
            assert guard.take_retry_notice() is None
        elif index == 2:
            assert "independent sources" in guard.take_retry_notice()
        else:
            assert guard.take_retry_notice() is None
        assert guard.stop is None
    guard.observe("read_file", "/tmp/final-report", {"output": "PK-7319", "exit_code": 0})
    assert guard.stop is None
    assert guard.take_retry_notice() is None


def test_case_insensitive_broader_empty_search_covers_narrower_literal():
    guard = RepeatedReadGuard()
    empty(guard, "shipment", ignore_case=True)
    empty(guard, "SHIPMENT-123")
    assert guard.stop == ("grep", "empty")


def test_successful_alternative_clears_redundant_search_stop():
    guard = RepeatedReadGuard()
    empty(guard, "shipment")
    empty(guard, "shipment-123")
    assert guard.stop is not None
    guard.observe("read_file", "/tmp/public-copy", {"output": "PK-7319", "exit_code": 0})
    assert guard.stop is None
    assert not guard.redundant_search


@pytest.mark.parametrize("error", ["not found", "permission denied"])
def test_only_requested_source_stops_without_guessing_other_filenames(error):
    guard = RepeatedReadGuard(
        user_text="Read /tmp/work/report.txt. Stay inside /tmp/work.", read_file_only=True,
    )
    guard.observe("read_file", "/tmp/work/report.txt", {"error": error, "exit_code": 1})
    assert guard.stop is not None
    assert "corrected path" in guard.final_answer("Read the file")
    assert "twice" not in guard.final_answer("Read the file")


@pytest.mark.parametrize("user_text", [
    "Read /tmp/work/old.txt; the replacement is /tmp/work/new.txt. Stay inside /tmp/work.",
    "Try /tmp/a.txt, /tmp/b.txt, /tmp/c.txt, /tmp/d.txt in order.",
])
def test_explicit_alternatives_are_exempt_from_single_source_stop(user_text):
    guard = RepeatedReadGuard(user_text=user_text, read_file_only=True)
    assert guard.requested_source is None
    for path in ["/tmp/work/old.txt", "/tmp/a.txt", "/tmp/b.txt"]:
        guard.observe("read_file", path, {"error": "not found"})
        assert guard.stop is None


def test_single_source_can_still_recover_with_listing_or_discovery_available():
    guard = RepeatedReadGuard(user_text="Read /tmp/report.txt", read_file_only=False)
    guard.observe("read_file", "/tmp/report.txt", {"error": "not found"})
    assert guard.stop is None


def test_single_source_transient_failure_can_be_retried():
    guard = RepeatedReadGuard(user_text="Read /tmp/report.txt", read_file_only=True)
    guard.observe("read_file", "/tmp/report.txt", {"error": "temporary timeout"})
    assert guard.stop is None


def test_later_batch_failures_do_not_change_the_requested_source_failure():
    guard = RepeatedReadGuard(user_text="Read /tmp/report.txt", read_file_only=True)
    guard.observe("read_file", "/tmp/report.txt", {"error": "not found"})
    for _ in range(2):
        guard.observe("read_file", "/tmp", {"error": "is a directory"})
    assert guard.stop == ("read_file", "not_found")
    assert "source was not found" in guard.final_answer("Read the file")


@pytest.mark.parametrize("tool,disabled", [("read_file", False), ("read_file", True), ("find_tools", False)])
def test_forced_tools_survive_conflicting_intent_but_not_policy(monkeypatch, tool, disabled):
    monkeypatch.setattr(agent, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(agent, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(agent, "blocked_tools_for_owner", lambda owner: set())
    monkeypatch.setattr(agent, "estimate_tokens", lambda *args, **kwargs: 10)
    monkeypatch.setattr(agent, "_classify_agent_request", lambda *args: {
        "domains": {"web"}, "retrieval_query": "Search the web", "low_signal": False,
    })
    monkeypatch.setattr(agent, "_build_system_prompt", lambda messages, *args, **kwargs: (messages, []))
    offered = []

    async def stream(candidates, messages, **kwargs):
        offered.extend(schema["function"]["name"] for schema in (kwargs.get("tools") or []))
        yield 'data: {"delta":"The requested source is unavailable."}\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(agent, "stream_llm_with_fallback", stream)

    async def collect():
        return [chunk async for chunk in agent.stream_agent_loop(
            "http://127.0.0.1:8010/v1", "Qwen3.8-verification",
            [{"role": "user", "content": "Read the shipment reference and report it."}],
            relevant_tools=set(), forced_tools={tool},
            disabled_tools=known_tool_names() - (set() if disabled else {tool}),
            max_rounds=1, log_turns=False, _is_teacher_run=True,
        )]

    asyncio.run(collect())
    assert (tool in offered) is not disabled
