"""End-to-end proxy tests using an httpx.MockTransport as the fake upstream."""
import json

import httpx
import pytest
from starlette.testclient import TestClient

from llmstat.db import Store
from llmstat.proxy import build_app


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "usage.db"))
    yield s
    s.close()


def _client_with(handler, store):
    transport = httpx.MockTransport(handler)
    upstream_client = httpx.AsyncClient(base_url="https://upstream.test", transport=transport)
    app = build_app("https://upstream.test", store, client=upstream_client)
    return TestClient(app)


def test_non_streaming_records_usage_and_cost(store):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "gpt-5.5-pro",
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
        })

    client = _client_with(handler, store)
    resp = client.post("/v1/chat/completions", json={"model": "gpt-5.5-pro", "messages": []})
    assert resp.status_code == 200

    rows = store.by_model()
    assert len(rows) == 1
    assert rows[0]["model"] == "gpt-5.5-pro"
    assert rows[0]["tokens"] == 1_000_000
    assert rows[0]["cost"] == pytest.approx(2.50)  # 1M input tokens @ $2.50/1M


def test_failed_call_still_recorded(store):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client_with(handler, store)
    resp = client.post("/v1/chat/completions", json={"model": "gpt-5.5-pro", "messages": []})
    assert resp.status_code == 500

    recent = store.recent()
    assert len(recent) == 1
    assert recent[0]["status"] == 500
    assert recent[0]["cost_usd"] == 0.0


def test_streaming_usage_parsed_from_sse(store):
    sse = (
        b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b'data: {"model":"gpt-5.5-pro","choices":[],'
        b'"usage":{"prompt_tokens":1000000,"completion_tokens":0}}\n\n'
        b'data: [DONE]\n\n'
    )

    class _SSEStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            # Emit in two raw chunks to exercise the proxy's line buffering.
            yield sse[:40]
            yield sse[40:]

    def handler(request: httpx.Request) -> httpx.Response:
        # The proxy should have injected stream_options.include_usage.
        sent = json.loads(request.content)
        assert sent.get("stream_options", {}).get("include_usage") is True
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              stream=_SSEStream())

    client = _client_with(handler, store)
    with client.stream("POST", "/v1/chat/completions",
                       json={"model": "gpt-5.5-pro", "messages": [], "stream": True}) as resp:
        body = b"".join(resp.iter_bytes())

    # Client still receives the untouched stream, terminator included.
    assert b'"content":"hel"' in body and b'"content":"lo"' in body
    assert b"[DONE]" in body

    rows = store.by_model()
    assert len(rows) == 1
    assert rows[0]["model"] == "gpt-5.5-pro"
    assert rows[0]["tokens"] == 1_000_000
    assert rows[0]["cost"] == pytest.approx(2.50)
    assert store.recent()[0]["stream"] == 1


def test_project_tag_recorded(store):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "glm-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    client = _client_with(handler, store)
    client.post("/v1/chat/completions",
                json={"model": "glm-5.2", "messages": []},
                headers={"X-Llmstat-Project": "chatbot"})

    # project is stored; verify via a direct query through the connection.
    row = store._conn.execute("SELECT project FROM requests").fetchone()
    assert row["project"] == "chatbot"
