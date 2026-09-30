"""履约模块 SQLite 访问层（stdlib sqlite3，零新依赖）

访问模式：**每操作短命连接**——`sqlite3.connect(path, timeout=5)` + WAL +
busy_timeout，用完即关。配合路由层 `asyncio.to_thread`，天然规避
`check_same_thread` 与跨线程共享连接的问题；多线程并发由 WAL + busy_timeout 兜住。

不存 docx 字节（保持"合同文件不落盘"产品口径），只存结构化节点与条款摘句。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS contracts (
  id              TEXT PRIMARY KEY,
  filename        TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|completed|failed
  error           TEXT,
  sign_date       TEXT,
  start_date      TEXT,
  end_date        TEXT,
  clause_count    INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  candidates_json TEXT NOT NULL DEFAULT '[]',
  created_at      TEXT NOT NULL,
  extracted_at    TEXT
);
CREATE TABLE IF NOT EXISTS milestones (
  id              TEXT PRIMARY KEY,
  contract_id     TEXT NOT NULL,
  recurring_group TEXT NOT NULL DEFAULT '',
  instance_index  INTEGER NOT NULL DEFAULT 0,
  node_type       TEXT NOT NULL DEFAULT 'other',
  title           TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  clause_ref      TEXT NOT NULL DEFAULT '',
  clause_text     TEXT NOT NULL DEFAULT '',
  due_date        TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|done|skipped
  needs_review    INTEGER NOT NULL DEFAULT 0,
  due_date_edited INTEGER NOT NULL DEFAULT 0,
  recurring       TEXT NOT NULL DEFAULT 'none',
  offset_days     INTEGER NOT NULL DEFAULT 0,
  done_at         TEXT,
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_milestones_contract ON milestones(contract_id);
CREATE INDEX IF NOT EXISTS idx_milestones_due ON milestones(status, due_date);
CREATE TABLE IF NOT EXISTS notifications (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  milestone_id TEXT NOT NULL,
  contract_id  TEXT NOT NULL,
  kind         TEXT NOT NULL,                      -- due_soon|overdue
  title        TEXT NOT NULL,
  content      TEXT NOT NULL DEFAULT '',
  due_date     TEXT,
  is_read      INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  UNIQUE(milestone_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read, id);
"""


def get_conn(db_path: Path | str | None = None) -> sqlite3.Connection:
    """打开一个短命连接（调用方负责 close；WAL + busy_timeout 抗并发）。"""
    conn = sqlite3.connect(
        str(db_path or settings.COMPLIANCE_DB_PATH),
        timeout=5,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def conn_ctx(db_path: Path | str | None = None):
    """with conn_ctx() as conn: ... —— 用完自动 commit/close。"""
    conn = get_conn(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def init_db(db_path: Path | str | None = None) -> None:
    """建目录建表 + 启动清扫（把 processing 置 failed：create_task 已随进程丢失）。"""
    path = Path(db_path or settings.COMPLIANCE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with conn_ctx(path) as conn:
        conn.executescript(DDL)
        conn.execute(
            "UPDATE contracts SET status='failed', error='服务重启导致提取中断' "
            "WHERE status='processing'"
        )
