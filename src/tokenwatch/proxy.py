"""A transparent OpenAI-compatible proxy that records token usage.

Point your client's base_url at tokenwatch instead of the real API; we forward
every request upstream untouched, then read the `usage` block out of the
response (works for both plain JSON and streamed SSE with usage enabled).
"""
from __future__ import annotations

import json
import time
from typing import Optional

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from .db import Store
from .pricing import cost_for

# Headers we must not forward verbatim to the upstream (hop-by-hop / host).
_STRIP_REQUEST_HEADERS = {"host", "content-length", "connection"}
_STRIP_RESPONSE_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def _project_from(request: Request) -> Optional[str]:
    """Let users tag traffic via an X-Tokenwatch-Project header."""
    return request.headers.get("x-tokenwatch-project")


def _extract_usage(payload: dict) -> Optional[dict]:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        return usage
    return None


def build_app(upstream: str, store: Store) -> Starlette:
    upstream = upstream.rstrip("/")
    client = httpx.AsyncClient(base_url=upstream, timeout=httpx.Timeout(600.0))

    async def proxy(request: Request) -> Response:
        body = await request.body()
        path = request.url.path
        model_hint = ""
        is_stream = False
        try:
            parsed = json.loads(body) if body else {}
            model_hint = parsed.get("model", "")
            is_stream = bool(parsed.get("stream"))
        except (ValueError, AttributeError):
            parsed = {}

        fwd_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in _STRIP_REQUEST_HEADERS
        }
        project = _project_from(request)
        started = time.monotonic()

        # --- Streaming path: tee the SSE stream, parse usage from the chunks ---
        if is_stream:
            # Nudge OpenAI-compatible servers to include usage in the final chunk.
            if parsed and "stream_options" not in parsed:
                parsed["stream_options"] = {"include_usage": True}
                body = json.dumps(parsed).encode()

            req = client.build_request(
                request.method, path, headers=fwd_headers, content=body,
                params=request.query_params,
            )
            upstream_resp = await client.send(req, stream=True)

            async def tee():
                captured = {"usage": None}
                buf = b""
                try:
                    async for raw in upstream_resp.aiter_raw():
                        yield raw
                        buf += raw
                        # Parse complete SSE lines for usage; keep the tail.
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if line.startswith(b"data:"):
                                data = line[len(b"data:"):].strip()
                                if data and data != b"[DONE]":
                                    try:
                                        obj = json.loads(data)
                                        u = _extract_usage(obj)
                                        if u:
                                            captured["usage"] = u
                                    except ValueError:
                                        pass
                finally:
                    await upstream_resp.aclose()
                    _save(captured["usage"], model_hint, project,
                          upstream_resp.status_code, started, True, store)

            resp_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in _STRIP_RESPONSE_HEADERS
            }
            return StreamingResponse(
                tee(),
                status_code=upstream_resp.status_code,
                headers=resp_headers,
                media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
            )

        # --- Non-streaming path ---
        upstream_resp = await client.request(
            request.method, path, headers=fwd_headers, content=body,
            params=request.query_params,
        )
        usage = None
        try:
            payload = upstream_resp.json()
            usage = _extract_usage(payload)
        except ValueError:
            pass
        _save(usage, model_hint, project, upstream_resp.status_code, started, False, store)

        resp_headers = {
            k: v for k, v in upstream_resp.headers.items()
            if k.lower() not in _STRIP_RESPONSE_HEADERS
        }
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )

    routes = [Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])]
    app = Starlette(routes=routes)
    app.state.client = client
    return app


def _save(usage, model_hint, project, status, started, stream, store: Store) -> None:
    latency_ms = int((time.monotonic() - started) * 1000)
    if not usage:
        # Still record the call so failures/unknowns show up in the dashboard.
        store.record(
            model=model_hint or "unknown", prompt_tokens=0, completion_tokens=0,
            cost_usd=0.0, latency_ms=latency_ms, status=status, stream=stream,
            project=project,
        )
        return
    model = usage.get("model") or model_hint or "unknown"
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    store.record(
        model=model, prompt_tokens=pt, completion_tokens=ct,
        cost_usd=cost_for(model, pt, ct), latency_ms=latency_ms,
        status=status, stream=stream, project=project,
    )
