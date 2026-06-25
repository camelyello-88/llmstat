"""llmstat command line: `serve` the proxy, `dash` the TUI, `demo` to try it."""
from __future__ import annotations

import argparse
import random
import sys
import time

from .db import DEFAULT_DB_PATH, Store
from .pricing import cost_for


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn  # imported lazily so `dash` works without a server stack

    from .proxy import build_app

    store = Store(args.db)
    app = build_app(args.upstream, store)
    print(f"\U0001f441️  llmstat proxy -> {args.upstream}")
    print(f"   point your client base_url at: http://{args.host}:{args.port}/v1")
    print(f"   writing usage to: {args.db}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _cmd_dash(args: argparse.Namespace) -> int:
    from .tui import run

    store = Store(args.db)
    run(store)
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    """Seed the db with believable traffic so you can see the dashboard now."""
    store = Store(args.db)
    models = [
        ("gpt-4o", 0.4), ("gpt-4o-mini", 0.9), ("claude-3-5-sonnet", 0.3),
        ("deepseek-chat", 0.6), ("o4-mini", 0.2),
    ]
    n = args.count
    now = time.time()
    for i in range(n):
        model, _ = random.choice(models)
        pt = random.randint(200, 6000)
        ct = random.randint(50, 2000)
        store._conn.execute(
            "INSERT INTO requests (ts, model, project, prompt_tokens, completion_tokens, "
            "total_tokens, cost_usd, latency_ms, status, stream) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                now - random.random() * 3600 * 8,
                model, random.choice([None, "chatbot", "batch-job"]),
                pt, ct, pt + ct, cost_for(model, pt, ct),
                random.randint(180, 4200),
                200 if random.random() > 0.05 else 500,
                1 if random.random() > 0.5 else 0,
            ),
        )
    store._conn.commit()
    print(f"Seeded {n} demo requests. Now run:  llmstat dash")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="llmstat",
        description="See what your LLM calls actually cost, in real time.",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="path to the usage database")
    sub = parser.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve", help="run the recording proxy")
    p_serve.add_argument("--upstream", required=True,
                         help="real OpenAI-compatible base url, e.g. https://api.openai.com")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8787)
    p_serve.set_defaults(func=_cmd_serve)

    p_dash = sub.add_parser("dash", help="open the live dashboard")
    p_dash.set_defaults(func=_cmd_dash)

    p_demo = sub.add_parser("demo", help="seed sample data to preview the dashboard")
    p_demo.add_argument("--count", type=int, default=120)
    p_demo.set_defaults(func=_cmd_demo)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
