# Contributing to llmstat

Thanks for taking a look! llmstat is intentionally small — a local proxy, one
SQLite file, and a TUI. Contributions that keep it lean and fast are very welcome.

## Dev setup

```bash
git clone https://github.com/camelyello-88/llmstat
cd llmstat
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Try it without any API key:

```bash
llmstat demo   # seed sample traffic
llmstat dash   # open the dashboard
llmstat top    # one-line status bar
```

## What's especially useful

- **Pricing updates** — model prices change constantly. PRs to `src/llmstat/pricing.py`
  are easy wins. (Users can also override locally via `~/.llmstat/pricing.json`.)
- **Provider quirks** — if a provider's `usage` block or SSE format isn't parsed
  correctly, a failing test in `tests/test_proxy.py` plus a fix is the gold standard.
- **Dashboard polish** — new views, better layout, more themes.

## Guidelines

- Add or update a test for any behavior change. The suite runs in well under a second.
- Keep dependencies minimal — textual, starlette, uvicorn, httpx is the whole stack.
- No telemetry, no network calls except the proxy forwarding. Local-first is the point.

## Roadmap ideas

See the [Roadmap](README.md#roadmap) in the README. Open an issue before large changes
so we can agree on the shape first.

MIT licensed — by contributing you agree your work ships under the same license.
