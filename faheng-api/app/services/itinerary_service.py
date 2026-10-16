"""人员行程模块业务层（SQLite，复用 compliance_db）"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.config import settings
from app.llm.asr import transcribe
from app.llm.client import LLMConfigError, LLMFormatError, chat_json
from app.llm.prompts import build_itinerary_prompt
from app.schemas.itinerary import (
    ArtistCreateIn,
    ConfirmIn,
    EventCreateIn,
    EventUpdateIn,
    ItineraryParseOut,
    VoiceParseIn,
)
from app.services.compliance_db import conn_ctx, row_to_dict

logger = logging.getLogger(__name__)


EVENT_TYPE_MAP = {
    "会议": "meeting",
    "会谈": "meeting",
    "演出": "performance",
    "表演": "performance",
    "活动": "activity",
    "采访": "interview",
    "专访": "interview",
    "录制": "recording",
    "录音": "recording",
    "拍摄": "recording",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _normalize_time_range(text: str) -> tuple[str, str]:
    """把时间描述归一化为 HH:MM - HH:MM。"""
    if not text:
        return "", ""
    text = text.strip().replace("：", ":").replace("-", "~").replace("—", "~")

    # 先尝试 HH:MM - HH:MM
    m = re.match(
        r"(\d{1,2}):(\d{2})\s*[~到至-]\s*(\d{1,2}):(\d{2})", text
    )
    if m:
        return (
            f"{int(m.group(1)):02d}:{m.group(2)}",
            f"{int(m.group(3)):02d}:{m.group(4)}",
        )

    # 上午/下午 N 点
    m = re.search(r"(?:上午|早上|早晨)\s*(\d{1,2})\s*点", text)
    if m:
        h = int(m.group(1))
        return f"{h:02d}:00", ""
    m = re.search(r"(?:下午|晚上)\s*(\d{1,2})\s*点", text)
    if m:
        h = int(m.group(1)) + 12
        if h == 24:
            h = 0
        return f"{h:02d}:00", ""

    # 上午/下午 N 点到 M 点
    m = re.match(
        r"(?:上午|早上|早晨|下午|晚上)?\s*(\d{1,2})\s*点\s*[~到至]\s*(?:上午|早上|早晨|下午|晚上)?\s*(\d{1,2})\s*点",
        text,
    )
    if m:
        h1, h2 = int(m.group(1)), int(m.group(2))
        # 简单推断：如果提到下午/晚上，第二个时间加12
        return f"{h1:02d}:00", f"{h2:02d}:00"

    return "", ""


def _normalize_date(text: str) -> str:
    """把日期描述归一化为 YYYY-MM-DD。"""
    if not text:
        return ""
    text = text.strip()
    today = date.today()

    # 明确 YYYY-MM-DD
    m = re.match(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})[日号]?", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass

    # MM-DD / MM月DD日
    m = re.match(r"(\d{1,2})[-/.月](\d{1,2})[日号]?", text)
    if m:
        try:
            return date(today.year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass

    # 几月几号
    m = re.match(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text)
    if m:
        try:
            return date(today.year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass

    # 明天/后天/大后天
    if re.search(r"明天", text):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"后天", text):
        return (today + timedelta(days=2)).isoformat()
    if re.search(r"大后天", text):
        return (today + timedelta(days=3)).isoformat()
    if re.search(r"今天", text):
        return today.isoformat()

    return ""


def _detect_event_type(title: str, summary: str) -> str:
    """根据关键词推断事项类型。"""
    combined = (title + summary).lower()
    for keyword, value in EVENT_TYPE_MAP.items():
        if keyword in combined:
            return value
    return "other"


# ── 人员 CRUD ──


def create_artist(body: ArtistCreateIn) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "人员姓名不能为空")
    artist_id = _new_id()
    try:
        with conn_ctx() as conn:
            conn.execute(
                "INSERT INTO itinerary_artists (id, name, color, created_at) VALUES (?,?,?,?)",
                (artist_id, name, body.color or "#2459a9", _now()),
            )
    except Exception as e:  # noqa: BLE001
        if "UNIQUE" in str(e):
            raise HTTPException(400, f"人员 '{name}' 已存在") from None
        raise
    return {"id": artist_id, "name": name, "color": body.color or "#2459a9"}


def list_artists() -> list[dict]:
    with conn_ctx() as conn:
        rows = conn.execute(
            "SELECT a.*, (SELECT COUNT(*) FROM itinerary_events e WHERE e.artist_id=a.id AND e.status!='deleted') AS event_count "
            "FROM itinerary_artists a ORDER BY a.created_at DESC"
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def delete_artist(artist_id: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT id FROM itinerary_artists WHERE id=?", (artist_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "人员不存在")
        conn.execute("DELETE FROM itinerary_events WHERE artist_id=?", (artist_id,))
        conn.execute("DELETE FROM itinerary_artists WHERE id=?", (artist_id,))
    return {"ok": True}


# ── 语音解析 ──


def _looks_like_speech(text: str) -> bool:
    """廉价门禁：转写文本是否像"人在说话"。

    在发 LLM 之前拦截明显的无效输入（如测试时念的「1234567。」）：
    没有中文、或中文内容太短（单个语气词/一两个字）的文本不可能
    构成行程描述，直接秒拒省一次 LLM 往返。纯中文判断可能误伤
    外语语音——但 ASR 是中文模型，外语转写本来就不可靠，误伤可接受。
    """
    stripped = text.strip()
    if not stripped:
        return False
    cjk_count = sum(1 for ch in stripped if "一" <= ch <= "鿿")
    return cjk_count >= 4 or len(stripped) >= 20


async def parse_voice_audio(
    data: bytes, mime: str, filename: str | None, default_artist_id: str | None,
    default_date: str | None = None,
) -> dict:
    """浏览器录音 → ASR 转文字 → LLM 解析为行程草稿。"""
    text = await transcribe(data, mime=mime, filename=filename)
    logger.info("语音识别结果（%d 字符）：%s", len(text), text)
    if not text.strip():
        raise HTTPException(422, "未能识别到语音内容，请靠近麦克风重试")
    if not _looks_like_speech(text):
        raise HTTPException(
            422,
            f"未识别到有效语音内容（听到「{text[:20]}」），"
            "请说明人员、日期和事项后重试",
        )
    out = await parse_voice(
        VoiceParseIn(
            text=text, default_artist_id=default_artist_id, default_date=default_date
        )
    )
    return {**out, "text": text}


def _resolve_artist(
    name: str, default_artist_id: str | None = None
) -> tuple[str | None, str | None]:
    """根据人员名查找或创建人员，返回 (artist_id, artist_name)。"""
    name = name.strip() if name else ""
    with conn_ctx() as conn:
        # 1. 优先完全匹配
        if name:
            row = conn.execute(
                "SELECT id, name FROM itinerary_artists WHERE name=? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if row:
                return row["id"], row["name"]
        # 2. 使用默认人员
        if default_artist_id:
            row = conn.execute(
                "SELECT id, name FROM itinerary_artists WHERE id=?",
                (default_artist_id,),
            ).fetchone()
            if row:
                return row["id"], row["name"]
    return None, name or ""


def _artist_upsert(name: str) -> tuple[str, str]:
    """语音中提到新人名时自动创建；返回 (artist_id, artist_name)。"""
    name = name.strip() if name else ""
    if not name:
        raise HTTPException(400, "未能识别人员姓名")
    artist_id, artist_name = _resolve_artist(name)
    if artist_id:
        return artist_id, artist_name
    created = create_artist(ArtistCreateIn(name=name))
    return created["id"], created["name"]


async def parse_voice(body: VoiceParseIn) -> dict:
    """调用 LLM 解析语音文本为行程草稿。"""
    if not body.text.strip():
        raise HTTPException(400, "语音文本为空")

    try:
        llm_out: ItineraryParseOut = await chat_json(
            build_itinerary_prompt(body.text),
            schema=ItineraryParseOut,
            temperature=0.0,
            max_tokens=4000,
            salvage=True,
            # 语音录入是交互场景，用户在等结果；跳过思维链，秒级返回
            reasoning_effort="low",
        )
    except LLMConfigError:
        # 网关连接/服务故障：用户无需知道细节，提示联系管理员即可
        raise HTTPException(503, "AI 配置异常，请及时联系管理员") from None
    except LLMFormatError as e:
        raise HTTPException(422, f"AI 解析失败：{e}") from None

    events_out: list[dict[str, Any]] = []
    for ev in llm_out.events or []:
        artist_id, artist_name = _resolve_artist(
            ev.artist_name, body.default_artist_id
        )
        # 日期/时间代码兜底
        event_date = _normalize_date(ev.event_date) if ev.event_date else ""
        # 当日弹框语音录入：语音没提日期时以点击的日期为准（非法格式静默忽略）
        if not event_date and body.default_date:
            try:
                date.fromisoformat(body.default_date)
                event_date = body.default_date
            except ValueError:
                pass
        start_time, end_time = _normalize_time_range(ev.time_range)
        event_type = ev.event_type
        if event_type == "other":
            event_type = _detect_event_type(ev.title, ev.summary)

        events_out.append(
            {
                "artist_id": artist_id,
                "artist_name": artist_name,
                "event_date": event_date,
                "start_time": start_time,
                "end_time": end_time,
                "title": ev.title,
                "event_type": event_type,
                "location": ev.location,
                "summary": ev.summary,
                "contacts": ev.contacts,
                "materials": ev.materials,
                "notes": ev.notes,
                "raw_text": body.text,
                "needs_review": not (artist_id and event_date and ev.title),
            }
        )

    return {"events": events_out, "raw_text": body.text}


# ── 行程 CRUD ──


def create_event(body: EventCreateIn, raw_text: str = "", status: str = "confirmed") -> dict:
    if not body.event_date:
        raise HTTPException(400, "行程日期不能为空")
    if not body.title:
        raise HTTPException(400, "行程事项不能为空")

    event_id = _new_id()
    now = _now()
    with conn_ctx() as conn:
        conn.execute(
            "INSERT INTO itinerary_events ("
            "id, artist_id, event_date, start_time, end_time, title, event_type, "
            "location, summary, contacts, materials, notes, status, raw_text, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                body.artist_id,
                body.event_date,
                body.start_time or "",
                body.end_time or "",
                body.title,
                body.event_type,
                body.location or "",
                body.summary or "",
                body.contacts or "",
                body.materials or "",
                body.notes or "",
                status,
                raw_text,
                now,
                now,
            ),
        )
    return get_event(event_id)


def update_event(body: EventUpdateIn) -> dict:
    if not body.id:
        raise HTTPException(400, "行程 ID 不能为空")

    allowed = {
        "artist_id": body.artist_id,
        "event_date": body.event_date,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "title": body.title,
        "event_type": body.event_type,
        "location": body.location,
        "summary": body.summary,
        "contacts": body.contacts,
        "materials": body.materials,
        "notes": body.notes,
        "status": body.status,
    }
    fields = {k: v for k, v in allowed.items() if v is not None}
    if not fields:
        raise HTTPException(400, "没有要更新的字段")

    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields.keys())
    values = list(fields.values()) + [body.id]

    with conn_ctx() as conn:
        cur = conn.execute(
            f"UPDATE itinerary_events SET {cols} WHERE id=? AND status!='deleted'",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "行程不存在或已删除")
    return get_event(body.id)


def get_event(event_id: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT e.*, a.name AS artist_name, a.color AS artist_color "
            "FROM itinerary_events e JOIN itinerary_artists a ON a.id=e.artist_id "
            "WHERE e.id=? AND e.status!='deleted'",
            (event_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "行程不存在")
    return row_to_dict(row)


def delete_event(event_id: str) -> dict:
    with conn_ctx() as conn:
        cur = conn.execute(
            "UPDATE itinerary_events SET status='deleted', updated_at=? WHERE id=? AND status!='deleted'",
            (_now(), event_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "行程不存在")
    return {"ok": True}


def list_events(
    artist_id: str,
    month: str | None = None,
    event_date: str | None = None,
) -> list[dict]:
    conditions = ["e.artist_id=?", "e.status!='deleted'"]
    params: list[Any] = [artist_id]
    if event_date:
        conditions.append("e.event_date=?")
        params.append(event_date)
    elif month:
        # month 格式 2026-10
        conditions.append("e.event_date LIKE ?")
        params.append(f"{month}-%")

    where = " AND ".join(conditions)
    with conn_ctx() as conn:
        rows = conn.execute(
            f"SELECT e.*, a.name AS artist_name, a.color AS artist_color "
            f"FROM itinerary_events e JOIN itinerary_artists a ON a.id=e.artist_id "
            f"WHERE {where} ORDER BY e.event_date, e.start_time, e.created_at",
            params,
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ── 确认入库 ──


def confirm_events(body: ConfirmIn) -> dict:
    created = []
    for ev in body.events:
        artist_id = ev.artist_id
        # 如果 artist_id 为空或不存在的人员，按当前默认逻辑创建一个新人员兜底
        if not artist_id:
            artist_id, _ = _artist_upsert("未知人员")
        else:
            with conn_ctx() as conn:
                row = conn.execute(
                    "SELECT id FROM itinerary_artists WHERE id=?", (artist_id,)
                ).fetchone()
            if row is None:
                artist_id, _ = _artist_upsert("未知人员")
        created.append(
            create_event(
                EventCreateIn(
                    artist_id=artist_id,
                    event_date=ev.event_date,
                    start_time=ev.start_time,
                    end_time=ev.end_time,
                    title=ev.title,
                    event_type=ev.event_type,
                    location=ev.location,
                    summary=ev.summary,
                    contacts=ev.contacts,
                    materials=ev.materials,
                    notes=ev.notes,
                ),
                raw_text="",
                status="confirmed",
            )
        )
    return {"events": created}
