"""AI calls go through the AI router, and failures read as plain words.

Run from apps/engine:  python -m pytest test/test_ai_client.py -q
"""
import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_client  # noqa: E402

_REAL_ASYNC_CLIENT = httpx.AsyncClient  # captured once: _client() may be called repeatedly in a test


def _client(monkeypatch, handler, key="ar_test_key"):
    """An AIClient whose HTTP calls are answered by `handler(request)`."""
    monkeypatch.setenv("AI_ROUTER_KEY", key)
    monkeypatch.setenv("AI_ROUTER_URL", "http://router.test/v1/")
    monkeypatch.setenv("AI_ROUTER_MODEL", "auto")
    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", factory)
    return ai_client.AIClient()


def _ask(client, prompt="How is the market?"):
    return asyncio.run(client.generate(prompt))


def test_sends_an_openai_style_request_to_the_router(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "## Outlook\nSteady."}}]})

    out = _ask(_client(monkeypatch, handler))
    assert out == "## Outlook\nSteady."
    assert seen["url"] == "http://router.test/v1/chat/completions"
    assert seen["auth"] == "Bearer ar_test_key"
    assert seen["body"]["model"] == "auto"                    # never a pinned model id
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert seen["body"]["messages"][1]["content"] == "How is the market?"


def test_no_key_is_reported_as_not_set_up_without_calling_anything(monkeypatch):
    called = []
    client = _client(monkeypatch, lambda r: called.append(1) or httpx.Response(200, json={}), key="")
    assert "not set up" in _ask(client) and called == []


def test_a_busy_or_failing_router_gives_plain_words_never_the_raw_error(monkeypatch):
    raw = '{ "error": { "code": 503, "message": "This model is currently experiencing high demand." } }'
    for status in (429, 500, 503):
        out = _ask(_client(monkeypatch, lambda r, s=status: httpx.Response(s, text=raw)))
        assert "unavailable right now" in out
        assert "503" not in out and "experiencing high demand" not in out and "{" not in out


def test_a_rejected_key_says_so(monkeypatch):
    out = _ask(_client(monkeypatch, lambda r: httpx.Response(401, json={"error": "revoked"})))
    assert "rejected this project's key" in out


def test_timeouts_unreachable_and_unreadable_answers_do_not_raise(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    assert "did not answer in time" in _ask(_client(monkeypatch, timeout))
    assert "could not be reached" in _ask(_client(monkeypatch, refused))
    assert "could not be read" in _ask(_client(monkeypatch, lambda r: httpx.Response(200, json={"choices": []})))
    assert "empty answer" in _ask(
        _client(monkeypatch, lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}))
    )


def test_the_engine_no_longer_calls_a_provider_directly():
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "analysis.py")).read()
    for gone in ("openrouter.ai", "generativelanguage.googleapis.com", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        assert gone not in src


# ── Headlines: Yahoo's news feed may fail without taking the analysis down ───

class _Ticker:
    def __init__(self, news=None, fail=False):
        self._news, self._fail = news, fail

    @property
    def news(self):
        if self._fail:
            raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***")
        return self._news


def _with_rss(monkeypatch, titles=None, fail=False):
    import routers.analysis as analysis

    async def fake_rss():
        if fail:
            raise RuntimeError("feeds unreachable")
        return list(titles or [])

    monkeypatch.setattr(analysis, "_rss_titles", fake_rss)
    return analysis


def test_yahoo_headlines_are_used_when_they_work(monkeypatch):
    analysis = _with_rss(monkeypatch, ["rss one"])
    yahoo = [{"content": {"title": "ONGC wins block"}}, {"content": {"title": "Oil steady"}}]
    out = asyncio.run(analysis.headlines_for(_Ticker(news=yahoo), 5))
    assert out and "rss one" not in out


def test_a_failed_or_empty_yahoo_feed_falls_back_to_the_apps_own_feeds(monkeypatch):
    analysis = _with_rss(monkeypatch, ["Sensex ends higher", "ONGC Q2 profit rises", "Rupee weakens"])
    assert asyncio.run(analysis.headlines_for(_Ticker(fail=True), 2)) == ["Sensex ends higher", "ONGC Q2 profit rises"]
    assert asyncio.run(analysis.headlines_for(_Ticker(news=[]), 5, match="ONGC.NS")) == ["ONGC Q2 profit rises"]
    assert asyncio.run(analysis.headlines_for(_Ticker(fail=True), 5, match="INFY")) == []


def test_when_every_news_source_fails_the_answer_is_empty_not_an_error(monkeypatch):
    analysis = _with_rss(monkeypatch, fail=True)
    assert asyncio.run(analysis.headlines_for(_Ticker(fail=True), 5)) == []


def test_analysis_endpoints_never_return_a_raw_exception_message():
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "analysis.py")).read()
    assert '"message": str(e)' not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
