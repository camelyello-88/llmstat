"""SQLite storage for request records. One small table, zero ceremony."""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Dict, List, Optional

DEFAULT_DB_PATH = os.path.expanduser("~/.tokenwatch/usage.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,
    model           TEXT    NOT NULL,
    project         TEXT,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL    NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    status          INTEGER NOT NULL DEFAULT 200,
    stream          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);
"""


class Store:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        status: int,
        stream: bool,
        project: Optional[str] = None,
    ) -> None:
        total = prompt_tokens + completion_tokens
        self._conn.execute(
            "INSERT INTO requests (ts, model, project, prompt_tokens, completion_tokens, "
            "total_tokens, cost_usd, latency_ms, status, stream) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                time.time(),
                model,
                project,
                prompt_tokens,
                completion_tokens,
                total,
                cost_usd,
                latency_ms,
                status,
                1 if stream else 0,
            ),
        )
        self._conn.commit()

    def totals(self, since: Optional[float] = None) -> Dict[str, float]:
        where = "WHERE ts >= ?" if since is not None else ""
        args = (since,) if since is not None else ()
        row = self._conn.execute(
            f"SELECT COUNT(*) AS calls, "
            f"COALESCE(SUM(total_tokens),0) AS tokens, "
            f"COALESCE(SUM(cost_usd),0) AS cost, "
            f"COALESCE(AVG(latency_ms),0) AS avg_latency "
            f"FROM requests {where}",
            args,
        ).fetchone()
        return dict(row) if row else {"calls": 0, "tokens": 0, "cost": 0, "avg_latency": 0}

    def by_model(self, since: Optional[float] = None) -> List[Dict]:
        where = "WHERE ts >= ?" if since is not None else ""
        args = (since,) if since is not None else ()
        rows = self._conn.execute(
            f"SELECT model, COUNT(*) AS calls, "
            f"COALESCE(SUM(total_tokens),0) AS tokens, "
            f"COALESCE(SUM(cost_usd),0) AS cost "
            f"FROM requests {where} GROUP BY model ORDER BY cost DESC",
            args,
        ).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 30) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT ts, model, total_tokens, cost_usd, latency_ms, status, stream "
            "FROM requests ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
