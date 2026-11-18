"""SQLite 持久化层。

两张单例表：
- pending     : 待确认的预览（安全表 payload，不含隐藏格真实计数）
- publication : 已发布的安全表（确认后写入，重启后可查；不可替换）

发布动作在单个事务内完成（写 publication + 清 pending），
失败不会产生部分公开结果。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publication (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    published_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ---------------------------------------------------------- pending

    def get_pending(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT payload, created_at FROM pending WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload["created_at"] = row["created_at"]
        return payload

    def set_pending(self, payload: dict) -> None:
        """保存/替换待确认预览（发布前允许重新上传）。"""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO pending (id, payload, created_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, "
                "created_at = excluded.created_at",
                (json.dumps(payload, ensure_ascii=False), _utcnow()),
            )

    def delete_pending(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pending WHERE id = 1")

    # ---------------------------------------------------------- publication

    def get_publication(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT payload, published_at FROM publication WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload["published_at"] = row["published_at"]
        return payload

    def publish(self, payload: dict) -> bool:
        """原子发布：写入 publication 并清空 pending。

        已存在发布结果时拒绝（返回 False），保证确认后不接受替换文件。
        """
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                exists = cur.execute(
                    "SELECT 1 FROM publication WHERE id = 1"
                ).fetchone()
                if exists:
                    cur.execute("ROLLBACK")
                    return False
                cur.execute(
                    "INSERT INTO publication (id, payload, published_at) "
                    "VALUES (1, ?, ?)",
                    (json.dumps(payload, ensure_ascii=False), _utcnow()),
                )
                cur.execute("DELETE FROM pending")
                cur.execute("COMMIT")
                return True
            except Exception:
                cur.execute("ROLLBACK")
                raise
