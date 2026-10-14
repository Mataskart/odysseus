"""Brave gets the user's query unchanged, valid freshness codes, and plain-text snippets."""

import httpx
import pytest

from services.search import core, providers
from services.search.analytics import RateLimitError


@pytest.fixture
def brave(monkeypatch):
    monkeypatch.setattr(providers, "_get_provider_key", lambda name: "k", raising=False)
    monkeypatch.setattr(providers, "_safesearch_for", lambda *_a, **_k: "moderate", raising=False)
    calls = []

    def respond(status=200, body=None):
        def get(url, headers=None, params=None, timeout=None):
            calls.append(params)
            request = httpx.Request("GET", url)
            return httpx.Response(status, json=body or {}, request=request)
        monkeypatch.setattr(providers.httpx, "get", get)

    return calls, respond


def test_query_is_sent_unchanged_with_brave_freshness(brave):
    calls, respond = brave
    respond(body={"web": {"results": [{
        "url": "https://example.com/qwen",
        "title": "Install <strong>Qwen</strong>",
        "description": "Run <strong>Qwen 3.5</strong> on Ubuntu &amp; Arch",
        "extra_snippets": ["Needs 8 GB VRAM."],
        "age": "2 days ago",
    }]}})

    results = providers.brave_search("how do I install  Qwen 3.5 on Ubuntu", 5, "week")

    assert calls[0]["q"] == "how do I install Qwen 3.5 on Ubuntu"
    assert calls[0]["freshness"] == "pw"
    assert results == [{
        "title": "Install Qwen",
        "url": "https://example.com/qwen",
        "snippet": "Run Qwen 3.5 on Ubuntu & Arch … Needs 8 GB VRAM.",
        "age": "2 days ago",
    }]


def test_rate_limit_moves_the_chain_on_without_a_second_brave_call(brave, monkeypatch):
    calls, respond = brave
    respond(status=429)
    with pytest.raises(RateLimitError):
        providers.brave_search("weather Vilnius", 5)

    fallback_calls = []
    monkeypatch.setattr(core, "_build_provider_chain", lambda primary: ["brave", "duckduckgo"])

    def call(name, query, count, time_filter=None):
        if name == "brave":
            return providers.brave_search(query, count, time_filter)
        fallback_calls.append(query)
        return []

    monkeypatch.setattr(core, "_call_provider", call)
    calls.clear()
    core.comprehensive_web_search("weather Vilnius", return_sources=True)
    assert len(calls) == 1
    assert fallback_calls == ["weather Vilnius"]
