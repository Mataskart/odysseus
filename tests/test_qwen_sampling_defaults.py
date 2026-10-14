from types import SimpleNamespace

import pytest

from routes import chat_helpers
from src import llm_core
from src.chat_handler import ChatHandler
from src.constants import DEFAULT_TEMPERATURE, QWEN_DEFAULT_TEMPERATURE


class _Response:
    is_success = True

    def __init__(self, message):
        self._message = message

    def json(self):
        return {"choices": [{"message": self._message}]}


def _capture_llm_call(monkeypatch, message):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, payload=json)
        return _Response(message)

    monkeypatch.setattr(llm_core, "httpx_post_kimi_aware", fake_post)
    monkeypatch.setattr(llm_core, "note_model_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_core, "_get_cached_response", lambda key: None)
    monkeypatch.setattr(llm_core, "_set_cached_response", lambda key, value: None)
    return sent


def test_thinking_off_reaches_local_chat_template_and_ignores_reasoning(monkeypatch):
    sent = _capture_llm_call(monkeypatch, {"content": "", "reasoning_content": "The user wants to find"})
    reply = llm_core.llm_call("http://127.0.0.1:8000/v1", "local/Qwen3.8", [{"role": "user", "content": "q"}],
                              max_tokens=50, thinking=False)
    assert sent["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert reply == ""


def test_thinking_off_is_not_sent_to_hosted_apis(monkeypatch):
    sent = _capture_llm_call(monkeypatch, {"content": "kaunas date ideas"})
    reply = llm_core.llm_call("https://api.openai.com/v1", "gpt-x", [{"role": "user", "content": "q"}], thinking=False)
    assert "chat_template_kwargs" not in sent["payload"]
    assert reply == "kaunas date ideas"


def test_default_calls_keep_reasoning_fallback(monkeypatch):
    sent = _capture_llm_call(monkeypatch, {"content": "", "reasoning_content": "thought"})
    reply = llm_core.llm_call("http://127.0.0.1:8000/v1", "local/Qwen3.8", [{"role": "user", "content": "q"}])
    assert "chat_template_kwargs" not in sent["payload"]
    assert reply == "thought"


def _handler(presets):
    return ChatHandler(None, None, None, None, SimpleNamespace(presets=presets), None)


@pytest.mark.parametrize("model, expected", [
    ("local/Qwen3.8-35B-A3B-Distill-Odysseus-FT-GGUF", QWEN_DEFAULT_TEMPERATURE),
    ("empero-ai/Qwen3.8-35B-A3B-Distill-GGUF", QWEN_DEFAULT_TEMPERATURE),
    ("gemma-4-26b", DEFAULT_TEMPERATURE),
])
def test_qwen_gets_recommended_temperature_without_a_preset(model, expected):
    preset = chat_helpers.extract_preset(_handler({}), None)
    assert chat_helpers.preset_temperature(preset, model) == expected


def test_an_explicit_preset_temperature_is_respected_for_qwen():
    handler = _handler({"warm": {"temperature": 1.0}, "plain": {"system_prompt": "Be brief."}})
    assert chat_helpers.preset_temperature(chat_helpers.extract_preset(handler, "warm"), "local/Qwen3.8") == 1.0
    assert chat_helpers.preset_temperature(chat_helpers.extract_preset(handler, "plain"), "local/Qwen3.8") == QWEN_DEFAULT_TEMPERATURE


def test_disabled_preset_temperature_does_not_count_as_explicit():
    handler = _handler({"off": {"enabled": False, "temperature": 1.0}})
    assert chat_helpers.preset_temperature(chat_helpers.extract_preset(handler, "off"), "local/Qwen3.8") == QWEN_DEFAULT_TEMPERATURE


def test_hand_built_or_duck_typed_presets_keep_their_temperature():
    assert chat_helpers.preset_temperature(chat_helpers.PresetInfo(0.7, 1024, None, None), "local/Qwen3.8") == 0.7
    assert chat_helpers.preset_temperature(SimpleNamespace(temperature=0.3), "local/Qwen3.8") == 0.3
