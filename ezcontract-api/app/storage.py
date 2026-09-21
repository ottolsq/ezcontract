"""内存 session 存储（demo 定位：重启即失，单进程内共享）"""
from __future__ import annotations

from app.schemas.draft import DraftSession
from app.schemas.review import ReviewSession

# 两类 session 共用一个 dict，按 id 索引
SESSIONS: dict[str, DraftSession | ReviewSession] = {}


def get_draft(session_id: str) -> DraftSession | None:
    s = SESSIONS.get(session_id)
    return s if isinstance(s, DraftSession) else None


def get_review(session_id: str) -> ReviewSession | None:
    s = SESSIONS.get(session_id)
    return s if isinstance(s, ReviewSession) else None
