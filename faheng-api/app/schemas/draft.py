"""起草相关 pydantic 模型"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DraftGenerateIn(BaseModel):
    keywords: str  # 必填，如"ERP软件 采购 私有云部署 三年"
    contract_type: str | None = None  # 采购合同 / NDA / 服务合同...
    party_a: str | None = None
    party_b: str | None = None
    extra_requirements: str | None = None


class DraftLLMOut(BaseModel):
    """起草/修订 LLM 输出 schema"""

    title: str
    markdown: str


class ReviseIn(BaseModel):
    instruction: str


class ContentIn(BaseModel):
    markdown: str


class ExportIn(BaseModel):
    """导出请求体：前端 TipTap 的 HTML（可选）；不传则降级走 markdown 导出"""

    html: str | None = None


class HistoryItem(BaseModel):
    instruction: str
    result_title: str = ""


class DraftSession(BaseModel):
    id: str
    title: str
    markdown: str
    keywords: str
    history: list[HistoryItem] = []

    # 起草状态机（与审查对齐，支持前端恢复）
    status: Literal["idle", "processing", "completed", "failed"] = "idle"
    progress: int = 0
    stage: str = ""
    error: str | None = None
