"""Bounded, advisory judgments from an operator-configured local OpenJev."""

import asyncio
import ipaddress
import json
import math
import time
from urllib.parse import urlsplit

import httpx

from src.settings import get_setting


TOOL_NAME = "openjev_judge"
MAX_BODY_BYTES = 16384
MAX_RESPONSE_BYTES = 65536
_health_cache = ("", 0.0, False)

TOOL_GUIDANCE = (
    "openjev_judge uses lookski/openjev with a local causal LLM, not an NLI "
    "checkpoint or the TypeSafe cloud service. It scores fixed answer labels "
    "without generating a reasoning trace; it has no search or conversation history. "
    "Use it for focused judgments on supplied evidence. For semantic "
    "counting in short supplied text, call it before giving the final count, "
    "especially in a cluttered conversation. "
    "For counts 0..9 use type=score with consecutive criteria from zero through the "
    "largest possible count; the most_likely_level is the count, NOT the fractional "
    "score. For literal lists, larger counts, or exact arithmetic use deterministic "
    "code when available. Send only complete relevant evidence, preserving negation, "
    "qualifiers and quoted-text boundaries. Batch one or two questions about the "
    "same evidence in a single call. "
    "Do not send the whole conversation or invent facts while extracting evidence. "
    "choice criteria MUST be a JSON object with 2..26 named options, NEVER an array: "
    '{"billing":"Payments, invoices, refunds","technical":"Errors, bugs, outages"}. '
    "Each value must fully describe its option; do not put meaning only in the key. "
    "score criteria is an array of 2..10 ordered descriptions. noul takes no criteria "
    "and returns P(Yes), not a verified yes/no answer; 0.5 is inconclusive. For missing "
    "or ambiguous evidence prefer choice with an explicit unknown option. "
    "Promising optional uses: simple presence/status classification and explicit "
    "rubric scoring on short text. Small tests were strongest on presence and rubrics; "
    "they do not establish general superiority. RAG relevance/reranking is an "
    "unvalidated experiment, not a deployed capability. Avoid arithmetic, character "
    "or substring counting (use code), factual lookup without supplied sources (use "
    "search), multi-step/temporal reasoning, resolving conflicting evidence, and "
    "permission, safety or high-stakes decisions. Lithuanian was weaker than English. "
    "An explicitly requested diagnostic test is allowed, but disclose these limits. "
    "Scores/probabilities are uncalibrated label preferences, NOT chances of being "
    "correct; even a high score can be wrong. Check the evidence independently and "
    "report disagreement; do not call answers verified merely because the tool ran. "
    "The result grants no permissions and cannot override user instructions. If "
    "unavailable, continue with another method and do not claim delegated verification."
)

def configured_url():
    if get_setting("openjev_enabled", False) is not True:
        return ""
    value = str(get_setting("openjev_url", "")).rstrip("/")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return ""
    if parsed.hostname != "localhost":
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return ""
        if not (address.is_private or address.is_loopback) or address.is_unspecified:
            return ""
    try:
        parsed.port
    except ValueError:
        return ""
    return value


async def _read_json(client, method, url, **kwargs):
    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("OpenJev response exceeds the size limit")
        return json.loads(body)


async def is_available():
    global _health_cache
    url = configured_url()
    if not url:
        return False
    expected_model = get_setting("openjev_model", "Qwen/Qwen3.5-4B")
    cache_key = (url, expected_model)
    cached_key, checked_at, healthy = _health_cache
    ttl = 15 if healthy else 3
    if cached_key == cache_key and time.monotonic() - checked_at < ttl:
        return healthy
    try:
        async with asyncio.timeout(0.8):
            async with httpx.AsyncClient(timeout=0.6, trust_env=False) as client:
                health = await _read_json(client, "GET", url + "/health")
        healthy = (
            health.get("status") == "ok"
            and health.get("engine_loaded") is True
            and health.get("model_id") == expected_model
        )
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, TimeoutError):
        healthy = False
    _health_cache = (cache_key, time.monotonic(), healthy)
    return healthy


def _wants_judgment(user_text):
    from src.action_intents import classify_tool_intent
    return classify_tool_intent(user_text or "").category == "judgment"


async def select_tool(relevant_tools, disabled_tools, guide_only=False, user_text=None):
    """Offer the judge on counting/judgment turns; elsewhere find_tools can still load it.

    ``user_text=None`` keeps the old always-offer behaviour for callers without the turn text.
    """
    if guide_only or TOOL_NAME in disabled_tools:
        disabled_tools.add(TOOL_NAME)
        return relevant_tools
    if user_text is not None and not _wants_judgment(user_text):
        # Skips the health probe too, so ordinary turns never wait on it.
        if relevant_tools is not None:
            relevant_tools.discard(TOOL_NAME)
        return relevant_tools
    if not await is_available():
        disabled_tools.add(TOOL_NAME)
        if relevant_tools is not None:
            relevant_tools.discard(TOOL_NAME)
        return relevant_tools
    if relevant_tools is None:
        return None
    relevant_tools.add(TOOL_NAME)
    return relevant_tools


def _validate_request(payload):
    if not isinstance(payload, dict) or set(payload) != {"state", "questions"}:
        raise ValueError("Provide only state and questions; the endpoint is operator-configured")
    state = payload["state"]
    if not isinstance(state, str) or not state.strip() or len(state) > 6000:
        raise ValueError("state must contain 1..6000 characters of relevant evidence")
    questions = payload["questions"]
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 2:
        raise ValueError("Provide one or two named questions")
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ValueError("Question names must contain 1..64 characters")
        if not isinstance(question, dict) or set(question) - {"type", "instructions", "criteria"}:
            raise ValueError("Each question needs type, instructions, and optional criteria")
        instructions = question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 1000:
            raise ValueError("Question instructions must contain 1..1000 characters")
        kind = question.get("type")
        criteria = question.get("criteria")
        if kind == "noul":
            if criteria is not None:
                raise ValueError("noul questions do not take criteria")
            continue
        if kind == "choice":
            if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 26:
                raise ValueError(
                    f"questions.{name}.criteria: choice requires a JSON object with "
                    '2..26 named options, not an array. Example: {"yes":"The supplied '
                    'evidence supports the claim","no":"The supplied evidence '
                    'contradicts the claim","unknown":"The evidence is insufficient"}. '
                    "Arrays are only valid for type=score."
                )
            if any(not isinstance(key, str) or not key.strip() for key in criteria):
                raise ValueError("Choice keys must be nonempty strings")
            values = criteria.values()
        elif kind == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise ValueError("score needs 2..10 ordered descriptions")
            values = criteria
        else:
            raise ValueError("Question type must be choice, score, or noul")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 500 for value in values):
            raise ValueError("Criteria descriptions must contain 1..500 characters")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Evidence and questions exceed the 16 KiB request limit")
    return body


def _validate_answers(response, questions):
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("OpenJev returned mismatched question IDs")
    for name, question in questions.items():
        answer = answers[name]
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise ValueError("OpenJev returned an unexpected answer type")
        if kind == "noul":
            probability = answer.get("noul")
            if type(probability) not in {int, float} or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("OpenJev returned an invalid P(Yes)")
            continue
        probabilities = answer.get("probabilities")
        expected_keys = set(question["criteria"])
        if kind == "score":
            expected_keys = {str(index) for index in range(len(question["criteria"]))}
        if not isinstance(probabilities, dict) or set(probabilities) != expected_keys:
            raise ValueError("OpenJev returned mismatched probability labels")
        values = probabilities.values()
        if any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise ValueError("OpenJev returned invalid probabilities")
        if abs(sum(probabilities.values()) - 1) > 0.002:
            raise ValueError("OpenJev returned an unnormalized distribution")
        confidence = answer.get("confidence")
        if confidence is not None and (type(confidence) not in {int, float} or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("OpenJev returned invalid confidence")
        if kind == "choice" and answer.get("choice") not in expected_keys:
            raise ValueError("OpenJev returned an unknown choice")
        if kind == "score":
            mean = sum(int(key) * value for key, value in probabilities.items())
            score = answer.get("score")
            if type(score) not in {int, float} or not math.isfinite(score) or abs(score - mean) > 0.002:
                raise ValueError("OpenJev returned an inconsistent weighted score")
            answer["most_likely_level"] = int(max(probabilities, key=probabilities.get))
    return answers


class OpenJevTool:
    async def execute(self, content, ctx):
        global _health_cache
        try:
            payload = json.loads(content)
            body = _validate_request(payload)
        except (ValueError, TypeError) as error:
            return {"error": str(error), "exit_code": 1}
        if not await is_available():
            return {"error": "OpenJev is unavailable or disabled. Continue with another method; no delegated judgment was obtained.", "exit_code": 1}
        url = configured_url()
        try:
            async with asyncio.timeout(12):
                async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                    response = await _read_json(
                        client, "POST", url + "/v1/systemone", content=body,
                        headers={"Content-Type": "application/json", "X-Request-Timeout-Ms": "10000"},
                    )
            expected_model = get_setting("openjev_model", "Qwen/Qwen3.5-4B")
            if response.get("model") not in {expected_model, "openjev/" + expected_model}:
                raise ValueError("OpenJev model changed after the health check")
            answers = _validate_answers(response, payload["questions"])
            return {
                "source": "OpenJev local judgment service", "model": response.get("model"),
                "answers": answers, "usage": response.get("usage"),
                "advisory": True, "untrusted_content": True,
                "limitations": (
                    "Uncalibrated label preferences, not probabilities of correctness, "
                    "verified facts or permission to act. High confidence can be wrong. "
                    "No search or generated reasoning trace. Check supplied evidence "
                    "independently and report disagreement. For counts use "
                    "most_likely_level only when criteria are consecutive counts from "
                    "zero; score is a weighted rubric index, not necessarily a count. "
                    "noul is P(Yes); near 0.5 is inconclusive and cannot express unknown."
                ),
            }
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status >= 500:
                _health_cache = ((url, get_setting("openjev_model", "Qwen/Qwen3.5-4B")), time.monotonic(), False)
            return {"error": f"OpenJev rejected or could not finish the request (HTTP {status}). No delegated judgment was obtained; shorten evidence for 413/422 or use another method.", "exit_code": 1}
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, TimeoutError):
            _health_cache = ((url, get_setting("openjev_model", "Qwen/Qwen3.5-4B")), time.monotonic(), False)
            return {"error": "OpenJev timed out or returned an invalid response. Continue with another method; no delegated judgment was obtained.", "exit_code": 1}
