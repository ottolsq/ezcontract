"""人员行程模块 Pydantic 模型"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ItineraryEventLLM(BaseModel):
    """LLM 从语音文本中抽取的单条行程"""

    artist_name: str = Field(default="", description="人员姓名；未提及则留空")
    event_date: str = Field(
        default="", description="行程日期，YYYY-MM-DD；未提及则留空"
    )
    time_range: str = Field(
        default="", description="时间段，如 '14:00-16:00' 或 '下午2点到4点'；未提及则留空"
    )
    title: str = Field(default="", description="行程事项，如 '品牌发布会'")
    event_type: Literal[
        "meeting", "performance", "activity", "interview", "recording", "other"
    ] = Field(default="other", description="事项类型")
    location: str = Field(default="", description="地点")
    summary: str = Field(default="", description="内容摘要")
    contacts: str = Field(default="", description="随行/对接人")
    materials: str = Field(default="", description="物料准备")
    notes: str = Field(default="", description="备注")


class ItineraryParseOut(BaseModel):
    """LLM 解析输出：可能一次语音包含多个人员的行程"""

    events: list[ItineraryEventLLM] = Field(default_factory=list)


# ── API 请求体 ──


class ArtistCreateIn(BaseModel):
    name: str
    color: str = "#2459a9"


class EventCreateIn(BaseModel):
    artist_id: str
    event_date: str  # YYYY-MM-DD
    start_time: str = ""
    end_time: str = ""
    title: str
    event_type: Literal[
        "meeting", "performance", "activity", "interview", "recording", "other"
    ] = "other"
    location: str = ""
    summary: str = ""
    contacts: str = ""
    materials: str = ""
    notes: str = ""


class EventUpdateIn(BaseModel):
    id: str
    artist_id: str | None = None
    event_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    title: str | None = None
    event_type: Literal[
        "meeting", "performance", "activity", "interview", "recording", "other"
    ] | None = None
    location: str | None = None
    summary: str | None = None
    contacts: str | None = None
    materials: str | None = None
    notes: str | None = None
    status: Literal["pending", "confirmed", "deleted"] | None = None


class VoiceParseIn(BaseModel):
    text: str
    default_artist_id: str | None = None  # 当前选中人员兜底


class ConfirmIn(BaseModel):
    events: list[EventCreateIn]
