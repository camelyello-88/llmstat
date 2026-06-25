import time

import pytest

from llmstat.db import Store


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "usage.db"))
    yield s
    s.close()


def _rec(store, **kw):
    base = dict(
        model="gpt-5.5-pro", prompt_tokens=100, completion_tokens=50,
        cost_usd=0.01, latency_ms=200, status=200, stream=False,
    )
    base.update(kw)
    store.record(**base)


def test_record_and_totals(store):
    _rec(store, prompt_tokens=100, completion_tokens=50, cost_usd=0.01)
    _rec(store, prompt_tokens=200, completion_tokens=100, cost_usd=0.02)
    t = store.totals()
    assert t["calls"] == 2
    assert t["tokens"] == 450  # (100+50) + (200+100)
    assert t["cost"] == pytest.approx(0.03)
    assert t["avg_latency"] == pytest.approx(200)


def test_totals_empty_db(store):
    t = store.totals()
    assert t["calls"] == 0
    assert t["tokens"] == 0
    assert t["cost"] == 0


def test_by_model_groups_and_orders_by_cost(store):
    _rec(store, model="glm-5.2", cost_usd=0.001)
    _rec(store, model="gpt-5.5-pro", cost_usd=0.05)
    _rec(store, model="gpt-5.5-pro", cost_usd=0.05)
    rows = store.by_model()
    assert rows[0]["model"] == "gpt-5.5-pro"  # highest cost first
    assert rows[0]["calls"] == 2
    assert rows[1]["model"] == "glm-5.2"


def test_since_filter_excludes_old_rows(store):
    _rec(store)
    future = time.time() + 3600
    assert store.totals(since=future)["calls"] == 0
    assert store.totals(since=0)["calls"] == 1


def test_recent_returns_newest_first(store):
    _rec(store, model="first")
    _rec(store, model="second")
    recent = store.recent(limit=10)
    assert recent[0]["model"] == "second"
    assert recent[1]["model"] == "first"
