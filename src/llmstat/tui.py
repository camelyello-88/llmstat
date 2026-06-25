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

    def __init__(self, emoji: str, label: str, card_id: str) -> None:
        super().__init__(id=card_id)
        self.emoji = emoji
        self.label = label

    def watch_value(self, value: str) -> None:
        # Color comes from CSS; markup just sets size/weight so it pops on pastel.
        self.update(f"{self.emoji}  [b]{value}[/b]\n[dim]{self.label}[/dim]")


# Pastel palette. Light = dark ink on soft pastels; dark = light ink on muted pastels.
_INK = "#3b3654"
_INK_DARK = "#ece9ff"

class Llmstat(App):
    CSS = f"""
    /* ---------- shared layout ---------- */
    #cards {{ height: 7; padding: 1 1 0 1; }}
    StatCard {{
        width: 1fr;
        height: 100%;
        content-align: center middle;
        text-align: center;
        margin: 0 1;
    }}
    #tables {{ padding: 1; height: 1fr; }}
    #title-models {{ text-style: bold; padding: 0 1; }}
    #title-feed {{ text-style: bold; padding: 0 1; }}
    DataTable {{ height: 1fr; }}
    DataTable > .datatable--header {{ text-style: bold; }}
    #left {{ width: 4fr; }}
    #right {{ width: 5fr; margin-left: 1; }}

    /* ---------- LIGHT theme (default) ---------- */
    Screen {{ background: #faf7ff; }}
    Header {{ background: #ddd6fe; color: {_INK}; text-style: bold; }}
    Footer {{ background: #ddd6fe; color: {_INK}; }}
    Footer > .footer--key {{ background: #c4b5fd; color: {_INK}; }}
    StatCard {{ border: round white; color: {_INK}; }}
    #card-spend   {{ background: #bae6fd; border: round #7dd3fc; }}
    #card-tokens  {{ background: #ddd6fe; border: round #c4b5fd; }}
    #card-calls   {{ background: #bbf7d0; border: round #6ee7b7; }}
    #card-latency {{ background: #fde2b3; border: round #fdba74; }}
    #title-models {{ color: #d946ef; }}
    #title-feed   {{ color: #0ea5e9; }}
    DataTable {{ background: #fdfcff; color: {_INK}; }}
    #models {{ border: round #f0abfc; }}
    #feed   {{ border: round #93c5fd; }}
    DataTable > .datatable--header {{ background: #ede9fe; color: {_INK}; }}
    DataTable > .datatable--odd-row {{ background: #f7f3ff; }}
    DataTable > .datatable--cursor {{ background: #fbcfe8; color: {_INK}; }}

    /* ---------- DARK theme (Screen.dark) ---------- */
    Screen.dark {{ background: #161226; }}
    Screen.dark Header {{ background: #2a2342; color: {_INK_DARK}; }}
    Screen.dark Footer {{ background: #2a2342; color: {_INK_DARK}; }}
    Screen.dark Footer > .footer--key {{ background: #4c3f73; color: {_INK_DARK}; }}
    Screen.dark StatCard {{ border: round #2a2342; color: {_INK_DARK}; }}
    Screen.dark #card-spend   {{ background: #1e3a5f; border: round #38bdf8; }}
    Screen.dark #card-tokens  {{ background: #352d5c; border: round #a78bfa; }}
    Screen.dark #card-calls   {{ background: #1e4035; border: round #34d399; }}
    Screen.dark #card-latency {{ background: #4a3520; border: round #fb923c; }}
    Screen.dark #title-models {{ color: #f0abfc; }}
    Screen.dark #title-feed   {{ color: #7dd3fc; }}
    Screen.dark DataTable {{ background: #1d1830; color: {_INK_DARK}; }}
    Screen.dark #models {{ border: round #7e3a8c; }}
    Screen.dark #feed   {{ border: round #3a5a8c; }}
    Screen.dark DataTable > .datatable--header {{ background: #2a2342; color: {_INK_DARK}; }}
    Screen.dark DataTable > .datatable--odd-row {{ background: #221c38; }}
    Screen.dark DataTable > .datatable--cursor {{ background: #5a2a4a; color: {_INK_DARK}; }}
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("t", "toggle_window", "Today / All-time"),
        ("d", "toggle_theme", "Dark / Light"),
    ]

    today_only: reactive[bool] = reactive(True)
    dark_mode: reactive[bool] = reactive(False)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store

    def action_toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.screen.set_class(self.dark_mode, "dark")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="cards"):
            yield StatCard("\U0001f4b8", "spend", "card-spend")        # 💸
            yield StatCard("\U0001f9ee", "tokens", "card-tokens")      # 🧮
            yield StatCard("\U0001f4de", "calls", "card-calls")        # 📞
            yield StatCard("⚡", "avg latency", "card-latency")    # ⚡
        with Horizontal(id="tables"):
            with Vertical(id="left"):
                yield Static("✨ By model", id="title-models")
                yield DataTable(id="models", zebra_stripes=True, cursor_type="row")
            with Vertical(id="right"):
                yield Static("\U0001f4e1 Live feed", id="title-feed")
                yield DataTable(id="feed", zebra_stripes=True, cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "llmstat"
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
    Llmstat(store).run()
