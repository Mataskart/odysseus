import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from src.tools import openjev


@pytest.fixture
def service(monkeypatch):
    settings = {"openjev_enabled": True, "openjev_url": "http://192.168.1.195:8771"}
    monkeypatch.setattr(openjev, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(openjev, "_health_cache", ("", 0.0, False))
    return settings


def mock_http(monkeypatch, handler):
    client_class = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(openjev.httpx, "AsyncClient", lambda **kwargs: client_class(transport=transport, **kwargs))


def count_payload():
    return {
        "state": "Present: Eglė, Tomas, Ugnė. Absent: Darius.",
        "questions": {"count": {"type": "score", "instructions": "How many people are present?", "criteria": ["Zero", "One", "Two", "Three"]}},
    }


def test_count_dispatch_keeps_fractional_score_separate_from_count(service, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "engine_loaded": True, "model_id": "Qwen/Qwen3.5-4B"})
        assert json.loads(request.content) == count_payload()
        assert request.headers["X-Request-Timeout-Ms"] == "10000"
        return httpx.Response(200, json={"model": "openjev/Qwen/Qwen3.5-4B", "answers": {
            "count": {"type": "score", "score": 2.7, "probabilities": {"0": 0, "1": 0, "2": .3, "3": .7}, "confidence": .6},
        }})

    mock_http(monkeypatch, respond)
    from src.agent_tools import ToolBlock, execute_tool_block, function_call_to_tool_block
    from src.tool_capabilities import ToolRunSecurityContext
    block = function_call_to_tool_block("openjev_judge", json.dumps(count_payload()))
    assert isinstance(block, ToolBlock)
    _, result = asyncio.run(execute_tool_block(block, security_context=ToolRunSecurityContext()))
    answer = result["answers"]["count"]
    assert answer["most_likely_level"] == 3
    assert answer["score"] == 2.7
    assert result["advisory"] and result["untrusted_content"]
    assert len(calls) == 2


@pytest.mark.parametrize("healthy", [True, False])
def test_health_controls_visibility_and_is_cached(service, monkeypatch, healthy):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "ok", "engine_loaded": healthy, "model_id": "Qwen/Qwen3.5-4B"})

    mock_http(monkeypatch, respond)

    async def select_twice():
        for _ in range(2):
            disabled = set()
            tools = await openjev.select_tool({"read_file", "openjev_judge"}, disabled)
            assert ("openjev_judge" in tools) is healthy
            assert ("openjev_judge" in disabled) is not healthy

    asyncio.run(select_twice())
    assert len(calls) == 1


def test_guide_only_and_explicit_disable_never_probe(service, monkeypatch):
    available = AsyncMock(side_effect=AssertionError("Must not probe"))
    monkeypatch.setattr(openjev, "is_available", available)
    asyncio.run(openjev.select_tool(set(), set(), guide_only=True))
    asyncio.run(openjev.select_tool(set(), {"openjev_judge"}))
    available.assert_not_called()


def test_healthy_tool_preserves_unfiltered_tool_fallback(service, monkeypatch):
    monkeypatch.setattr(openjev, "is_available", AsyncMock(return_value=True))
    disabled = set()
    assert asyncio.run(openjev.select_tool(None, disabled)) is None
    assert "openjev_judge" not in disabled


def test_restored_small_baseline_is_not_offered_as_quality_service(service, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "status": "ok", "engine_loaded": True, "model_id": "Qwen/Qwen3-0.6B",
    }))
    assert not asyncio.run(openjev.is_available())


@pytest.mark.parametrize("url", ["http://example.com", "http://8.8.8.8", "http://[", "http://0.0.0.0:8771", "http://localhost:bad", "http://user:pass@192.168.1.195", "http://192.168.1.195/other", "http://192.168.1.195?redirect=1"])
def test_only_operator_configured_local_origins_are_accepted(service, url):
    service["openjev_url"] = url
    assert openjev.configured_url() == ""


@pytest.mark.parametrize("change", [
    lambda payload: payload.update(url="http://other"),
    lambda payload: payload.update(state="x" * 6001),
    lambda payload: payload.update(questions={}),
    lambda payload: payload.update(questions={str(i): payload["questions"]["count"] for i in range(3)}),
    lambda payload: payload["questions"]["count"].update(criteria=[str(i) for i in range(11)]),
    lambda payload: payload["questions"]["count"].update(type="choice", criteria={str(i): str(i) for i in range(27)}),
])
def test_invalid_inputs_fail_before_network(service, monkeypatch, change):
    available = AsyncMock(side_effect=AssertionError("Must validate first"))
    monkeypatch.setattr(openjev, "is_available", available)
    payload = count_payload()
    change(payload)
    result = asyncio.run(openjev.OpenJevTool().execute(json.dumps(payload), {}))
    assert result["exit_code"] == 1
    available.assert_not_called()


def test_choice_array_error_explains_object_shape_before_network(service, monkeypatch):
    available = AsyncMock(side_effect=AssertionError("Must validate first"))
    monkeypatch.setattr(openjev, "is_available", available)
    payload = {
        "state": "Payment was charged twice.",
        "questions": {"route": {
            "type": "choice", "instructions": "Which team?",
            "criteria": ["Billing", "Technical"],
        }},
    }
    result = asyncio.run(openjev.OpenJevTool().execute(json.dumps(payload), {}))
    assert result["exit_code"] == 1
    assert "questions.route.criteria" in result["error"]
    assert "JSON object" in result["error"]
    assert "not an array" in result["error"]
    assert '"unknown":"The evidence is insufficient"' in result["error"]
    available.assert_not_called()


@pytest.mark.parametrize("question,valid", [
    ({"type": "choice", "instructions": "Which team?", "criteria": {"billing": "Payments", "technical": "Bugs"}}, True),
    ({"type": "choice", "instructions": "Which team?", "criteria": {str(i): str(i) for i in range(26)}}, True),
    ({"type": "score", "instructions": "How many?", "criteria": [str(i) for i in range(10)]}, True),
    ({"type": "noul", "instructions": "Does the supplied text express urgency?"}, True),
    ({"type": "choice", "instructions": "Which team?", "criteria": ["Billing", "Technical"]}, False),
    ({"type": "choice", "instructions": "Which team?", "criteria": {"billing": "Payments"}}, False),
    ({"type": "choice", "instructions": "Which team?", "criteria": {str(i): str(i) for i in range(27)}}, False),
    ({"type": "choice", "instructions": "Which team?", "criteria": {"": "Payments", "technical": "Bugs"}}, False),
    ({"type": "choice", "instructions": "Which team?", "criteria": {"billing": "", "technical": "Bugs"}}, False),
    ({"type": "choice", "instructions": "Which team?"}, False),
    ({"type": "score", "instructions": "How severe?", "criteria": {"low": "Cosmetic", "high": "Outage"}}, False),
    ({"type": "score", "instructions": "How severe?", "criteria": ["Cosmetic"]}, False),
    ({"type": "score", "instructions": "How severe?", "criteria": [str(i) for i in range(11)]}, False),
    ({"type": "score", "instructions": "How severe?"}, False),
    ({"type": "noul", "instructions": "Urgent?", "criteria": ["No", "Yes"]}, False),
])
def test_native_schema_matches_runtime_question_shapes(question, valid):
    from jsonschema import Draft7Validator
    from src.agent_tools import FUNCTION_TOOL_SCHEMAS

    schema = next(item["function"]["parameters"] for item in FUNCTION_TOOL_SCHEMAS
                  if item["function"]["name"] == "openjev_judge")
    Draft7Validator.check_schema(schema)
    payload = {"state": "The supplied evidence.", "questions": {"probe": question}}
    assert Draft7Validator(schema).is_valid(payload) is valid
    if valid:
        openjev._validate_request(payload)
    else:
        with pytest.raises(ValueError):
            openjev._validate_request(payload)


@pytest.mark.parametrize("status", [413, 422, 503, 504])
def test_rejection_returns_failure_without_a_fabricated_judgment(service, monkeypatch, status):
    monkeypatch.setattr(openjev, "is_available", AsyncMock(return_value=True))
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"error": "unavailable"}))
    result = asyncio.run(openjev.OpenJevTool().execute(json.dumps(count_payload()), {}))
    assert str(status) in result["error"]
    assert "answers" not in result


def test_timeout_returns_prompt_failure(service, monkeypatch):
    monkeypatch.setattr(openjev, "is_available", AsyncMock(return_value=True))

    def respond(request):
        raise httpx.ReadTimeout("offline")

    mock_http(monkeypatch, respond)
    result = asyncio.run(openjev.OpenJevTool().execute(json.dumps(count_payload()), {}))
    assert "timed out" in result["error"]
    assert "answers" not in result


@pytest.mark.parametrize("probabilities", [
    {"0": float("nan"), "1": 0, "2": 0, "3": 1},
    {"0": 0, "1": 0, "2": 0, "3": .5},
    {"wrong": 1},
])
def test_invalid_distributions_are_rejected(probabilities):
    response = {"answers": {"count": {"type": "score", "score": 3, "probabilities": probabilities}}}
    with pytest.raises(ValueError):
        openjev._validate_answers(response, count_payload()["questions"])


def test_registration_routing_and_existing_authority_gates():
    from src.action_intents import classify_tool_intent
    from src.agent_tools import TOOL_HANDLERS, TOOL_TAGS, FUNCTION_TOOL_SCHEMAS, parse_tool_blocks
    from src.tool_capabilities import capabilities_for_tool, ResultIntegrity, ToolEffect, ToolRunSecurityContext
    from src.tool_security import PLAN_MODE_READONLY_TOOLS
    from src.tool_policy import known_tool_names
    assert "openjev_judge" in TOOL_HANDLERS
    assert "openjev_judge" in TOOL_TAGS
    assert "openjev_judge" in known_tool_names()
    assert "openjev_judge" in PLAN_MODE_READONLY_TOOLS
    assert any(schema["function"]["name"] == "openjev_judge" for schema in FUNCTION_TOOL_SCHEMAS)
    assert parse_tool_blocks('```openjev_judge\n' + json.dumps(count_payload()) + '\n```')[0].tool_type == "openjev_judge"
    capabilities = capabilities_for_tool("openjev_judge")
    assert capabilities.known
    assert capabilities.result_integrity == ResultIntegrity.EXTERNAL_UNTRUSTED
    assert capabilities.effects == frozenset({ToolEffect.NETWORK_EGRESS})
    assert not ToolRunSecurityContext(external_untrusted_context_seen=True).decision_for("openjev_judge").allowed
    for text in ["Count the present people", "Can you count these?", "In this list, how many passed?", "Kiek žmonių dalyvauja?", "Suskaičiuok obuolius", "Use OpenJev for this decision"]:
        assert classify_tool_intent(text).category == "judgment"
    assert not classify_tool_intent("Can you explain how counting works?").needs_tools


def test_native_prompt_requires_counting_delegation_only_when_tool_is_offered():
    from src.agent_loop import _assemble_prompt
    prompt = _assemble_prompt({"openjev_judge"}, compact=True)
    assert "call it before giving the final count" in prompt
    disabled_prompt = _assemble_prompt({"openjev_judge"}, {"openjev_judge"}, compact=True)
    assert "call it before giving the final count" not in disabled_prompt


def test_agent_loop_offers_and_executes_delegation(service, monkeypatch):
    import src.agent_loop as agent_loop

    def respond(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "engine_loaded": True, "model_id": "Qwen/Qwen3.5-4B"})
        return httpx.Response(200, json={"model": "openjev/Qwen/Qwen3.5-4B", "answers": {
            "count": {"type": "score", "score": 3, "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1}},
        }})

    mock_http(monkeypatch, respond)
    monkeypatch.setattr(agent_loop, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(agent_loop, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(agent_loop, "estimate_tokens", lambda *args, **kwargs: 100)
    monkeypatch.setattr(agent_loop, "_build_system_prompt", lambda messages, *args, **kwargs: (messages, []))
    rounds = []

    async def model_stream(candidates, messages, **kwargs):
        rounds.append(messages)
        offered = {schema["function"]["name"] for schema in kwargs["tools"]}
        assert "openjev_judge" in offered
        if len(rounds) == 1:
            call = {"name": "openjev_judge", "arguments": json.dumps(count_payload())}
            yield 'data: ' + json.dumps({"type": "tool_calls", "calls": [call]}) + '\n\n'
        else:
            assert any(message.get("role") == "tool" and 'most_likely_level' in message.get("content", "") for message in messages)
            yield 'data: ' + json.dumps({"delta": "Three people are present."}) + '\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", model_stream)

    async def run():
        return [chunk async for chunk in agent_loop.stream_agent_loop(
            'http://127.0.0.1:8000/v1', 'Qwen3.8-35B',
            [{"role": "user", "content": "Count the people present: Eglė, Tomas, Ugnė. Darius is absent."}],
            relevant_tools={"ask_user"}, max_rounds=3, log_turns=False, context_length=4096,
        )]

    chunks = asyncio.run(run())
    assert len(rounds) == 2
    assert any('Three people are present.' in chunk for chunk in chunks)
    outputs = [json.loads(chunk.removeprefix('data: ')) for chunk in chunks if '"type": "tool_output"' in chunk]
    result = json.loads(outputs[0]["output"])
    assert result["answers"]["count"]["most_likely_level"] == 3
    assert result["advisory"] is True
    assert "not probabilities of correctness" in result["limitations"]


def test_judge_is_offered_only_for_judgment_turns(service, monkeypatch):
    available = AsyncMock(return_value=True)
    monkeypatch.setattr(openjev, "is_available", available)

    async def select(text):
        return await openjev.select_tool({"read_file", "openjev_judge"}, set(), user_text=text)

    assert "openjev_judge" not in asyncio.run(select("Load runtime-skill, then use it."))
    available.assert_not_awaited()
    assert "openjev_judge" in asyncio.run(select("How many tickets mention refunds?"))
