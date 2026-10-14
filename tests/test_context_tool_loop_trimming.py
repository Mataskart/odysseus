"""Context shaping must preserve the active query and complete tool exchanges."""

import asyncio
import copy

import pytest

import src.context_compactor as compactor
from src.model_context import estimate_tokens


def tool_round(round_number, result_size=10000, argument_size=2):
    calls = [
        {
            "id": f"call_{round_number}_{index}",
            "type": "function",
            "function": {"name": "web_search", "arguments": "x" * argument_size},
        }
        for index in range(3)
    ]
    return [
        {"role": "assistant", "content": None, "tool_calls": calls},
        *[
            {"role": "tool", "tool_call_id": call["id"], "content": "r" * result_size}
            for call in calls
        ],
    ]


def assert_complete_tool_exchanges(messages):
    pending = set()
    for message in messages:
        if message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
            pending = {call["id"] for call in message.get("tool_calls", [])}
    assert not pending


@pytest.mark.parametrize("round_count", [4, 5, 6, 20])
@pytest.mark.parametrize("context_length", [2048, 42649])
def test_long_tool_loop_keeps_query_and_fits_budget(round_count, context_length):
    query = {"role": "user", "content": "Find unusual date ideas within 70km of Kaunas."}
    messages = [{"role": "system", "content": "You are helpful."}, query]
    for round_number in range(round_count):
        messages.extend(tool_round(round_number))
    original = copy.deepcopy(messages)

    trimmed = compactor.trim_for_context(messages, context_length, reserve_tokens=512)

    assert query in trimmed
    assert estimate_tokens(trimmed) <= context_length - 512
    assert trimmed[-1]["tool_call_id"] == f"call_{round_count - 1}_2"
    assert_complete_tool_exchanges(trimmed)
    assert messages == original
    assert compactor.trim_for_context(trimmed, context_length, reserve_tokens=512) == trimmed


def test_latest_user_query_survives_old_conversation_and_huge_tool_arguments():
    query = {"role": "user", "content": "CURRENT REQUEST"}
    messages = [
        {"role": "system", "content": "Persona"},
        {"role": "user", "content": "OLD REQUEST" * 1000},
        {"role": "assistant", "content": "old response" * 1000},
        query,
        *tool_round(1, result_size=30000, argument_size=40000),
    ]

    trimmed = compactor.trim_for_context(messages, 4096, reserve_tokens=512)

    assert query in trimmed
    assert estimate_tokens(trimmed) <= 3584
    assert_complete_tool_exchanges(trimmed)


def test_protected_context_counted_once_and_preserved():
    protected = {"role": "system", "content": "document " * 200, "_protected": True}
    query = {"role": "user", "content": "CURRENT REQUEST"}
    trimmed = compactor.trim_for_context(
        [{"role": "system", "content": "Persona"}, protected, query, *tool_round(1)],
        2048,
        reserve_tokens=512,
    )
    assert protected in trimmed
    assert query in trimmed
    assert estimate_tokens(trimmed) <= 1536
    assert_complete_tool_exchanges(trimmed)


def test_impossible_protected_context_fails_before_sending_oversized_request():
    with pytest.raises(compactor.ContextBudgetError, match="protected context"):
        compactor.trim_for_context(
            [
                {"role": "system", "content": "document " * 1000, "_protected": True},
                {"role": "user", "content": "CURRENT REQUEST"},
            ],
            1024,
            reserve_tokens=512,
        )


@pytest.mark.parametrize("has_prior_turn", [False, True])
def test_summarization_never_splits_the_active_tool_loop(monkeypatch, has_prior_turn):
    query = {"role": "user", "content": "CURRENT REQUEST"}
    active_turn = [query]
    for round_number in range(6):
        active_turn.extend(tool_round(round_number))
    prior_turn = [
        {"role": "user", "content": "earlier request"},
        {"role": "assistant", "content": "earlier response"},
    ] if has_prior_turn else []
    messages = [{"role": "system", "content": "Persona"}, *prior_turn, *active_turn]
    summary_calls = []

    async def summarize(*args, **kwargs):
        summary_calls.append(args[2])
        return "Earlier work summarized."

    monkeypatch.setattr(compactor, "get_context_length", lambda *args: 4096)
    monkeypatch.setattr(compactor, "resolve_endpoint", lambda *args, **kwargs: (None, None, None))
    monkeypatch.setattr(compactor, "llm_call_async", summarize)
    compacted, _, did_compact = asyncio.run(compactor.maybe_compact(
        None, "http://local/v1", "local-model", messages, persist=False,
    ))

    assert did_compact is has_prior_turn
    assert compacted[-len(active_turn):] == active_turn
    assert len(summary_calls) == int(has_prior_turn)
    if summary_calls:
        assert "CURRENT REQUEST" not in summary_calls[0][-1]["content"]
    trimmed = compactor.trim_for_context(compacted, 4096, reserve_tokens=512)
    assert query in trimmed
    assert estimate_tokens(trimmed) <= 3584
    assert_complete_tool_exchanges(trimmed)


def test_message_budget_includes_both_content_and_tool_arguments():
    message = tool_round(0, argument_size=40000)[0]
    message["content"] = "reasoning " * 1000
    trimmed = compactor._truncate_message_to_token_budget(message, 200)
    assert estimate_tokens([trimmed]) <= 200
    assert len(trimmed["tool_calls"]) == 3


def test_multimodal_current_query_keeps_images_and_fits_text_budget():
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,example"}}
    messages = [
        {"role": "system", "content": "Persona"},
        {"role": "user", "content": [
            {"type": "text", "text": "question " * 2000},
            image,
            {"type": "text", "text": "more details " * 2000},
        ]},
        *tool_round(1),
    ]
    trimmed = compactor.trim_for_context(messages, 2048, reserve_tokens=512)
    query = next(message for message in trimmed if message["role"] == "user")
    assert image in query["content"]
    assert estimate_tokens(trimmed) <= 1536
    assert_complete_tool_exchanges(trimmed)
