"""The dashboard. Modern, playful, and refreshes itself while you work."""
from __future__ import annotations

import time
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

from .db import Store

# Day boundary helper -> epoch seconds for "today".
def _start_of_today() -> float:
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def _money(v: float) -> str:
    if v >= 1:
        return f"${v:,.2f}"
    if v >= 0.01:
        return f"${v:.3f}"
    return f"{v*100:.2f}¢"  # show sub-cent amounts in cents


def _compact(n: float) -> str:
    n = float(n)
    for unit in ("", "K", "M", "B"):
        if abs(n) < 1000:
            return f"{n:.0f}{unit}" if unit == "" else f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}T"


class StatCard(Static):
    """A single big-number card with an emoji and a label."""

    value: reactive[str] = reactive("—")

    def __init__(self, emoji: str, label: str, accent: str) -> None:
        super().__init__()
        self.emoji = emoji
        self.label = label
        self.accent = accent

    def watch_value(self, value: str) -> None:
        self.update(
            f"[{self.accent}]{self.emoji}  [b]{value}[/b][/]\n[dim]{self.label}[/dim]"
        )


class Tokenwatch(App):
    CSS = """
    Screen { background: $surface; }

    #cards { height: 7; padding: 1 1 0 1; }
    StatCard {
        width: 1fr;
        height: 100%;
        content-align: center middle;
        text-align: center;
        border: round $primary 30%;
        margin: 0 1;
        background: $panel;
    }

    #tables { padding: 1; height: 1fr; }
    .panel-title { text-style: bold; color: $accent; padding: 0 1; }
    DataTable { height: 1fr; background: $panel; border: round $primary 30%; }
    #left { width: 2fr; }
    #right { width: 3fr; margin-left: 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("t", "toggle_window", "Today / All-time"),
    ]

    today_only: reactive[bool] = reactive(True)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="cards"):
            yield StatCard("\U0001f4b8", "spend", "#7dd3fc")        # 💸
            yield StatCard("\U0001f9ee", "tokens", "#c4b5fd")       # 🧮
            yield StatCard("\U0001f4de", "calls", "#86efac")        # 📞
            yield StatCard("⚡", "avg latency", "#fcd34d")      # ⚡
        with Horizontal(id="tables"):
            with Vertical(id="left"):
                yield Static("By model", classes="panel-title")
                yield DataTable(id="models", zebra_stripes=True, cursor_type="row")
            with Vertical(id="right"):
                yield Static("Live feed", classes="panel-title")
                yield DataTable(id="feed", zebra_stripes=True, cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "tokenwatch"
        self.sub_title = "today"
        models = self.query_one("#models", DataTable)
        models.add_columns("model", "calls", "tokens", "cost")
        feed = self.query_one("#feed", DataTable)
        feed.add_columns("time", "model", "tokens", "cost", "ms", "")
        self.refresh_data()
        self.set_interval(2.0, self.refresh_data)

    def action_refresh(self) -> None:
        self.refresh_data()

    def action_toggle_window(self) -> None:
        self.today_only = not self.today_only
        self.sub_title = "today" if self.today_only else "all-time"
        self.refresh_data()

    def refresh_data(self) -> None:
        since = _start_of_today() if self.today_only else None
        totals = self.store.totals(since)

        cards = list(self.query(StatCard))
        cards[0].value = _money(totals["cost"])
        cards[1].value = _compact(totals["tokens"])
        cards[2].value = f"{int(totals['calls'])}"
        cards[3].value = f"{int(totals['avg_latency'])} ms"

        models = self.query_one("#models", DataTable)
        models.clear()
        for row in self.store.by_model(since):
            models.add_row(
                row["model"][:28],
                str(row["calls"]),
                _compact(row["tokens"]),
                _money(row["cost"]),
            )

        feed = self.query_one("#feed", DataTable)
        feed.clear()
        for r in self.store.recent(40):
            when = datetime.fromtimestamp(r["ts"]).strftime("%H:%M:%S")
            ok = "✓" if r["status"] < 400 else "✗"  # ✓ / ✗
            mark = "\U0001f30a" if r["stream"] else ""        # 🌊 for streamed
            feed.add_row(
                when,
                str(r["model"])[:24],
                _compact(r["total_tokens"]),
                _money(r["cost_usd"]),
                str(r["latency_ms"]),
                f"{ok} {mark}".strip(),
            )


def run(store: Store) -> None:
    Tokenwatch(store).run()
