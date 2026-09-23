"""审查相关 pydantic 模型（API 层 + LLM 输出层）"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Clause(BaseModel):
    """切分后的合同条款（导出回填的锚点）"""

    clause_id: str  # "C01"，LLM 引用编号
    clause_no: str  # "第五条"（原文编号，展示用）
    title: str = ""  # 条款标题（如"第五条 合同金额与支付"取后半段）
    text: str  # 完整条款文本（多段落拼合）
    html: str = ""  # 包含原段落样式的安全 HTML，供前端展示用
    start_idx: int  # docx 段落起始下标（PDF 时为行号）
    end_idx: int  # 段落结束下标（含）


class RiskItem(BaseModel):
    """单条风险（LLM 单条输出 schema，risk_id/clause_no 由后端补充）"""

    clause_id: str
    title: str = Field(description="风险短标题，如：合同期内单方涨价")
    level: Literal["high", "medium", "low"]
    matched_rules: list[str] = []
    issue: str = Field(description="风险说明，80字以内")
    impact: str = Field(description="对甲方的影响，80字以内")
    suggestion: str = Field(description="完整、可直接替换原条款的条款文本")

    # 后端补充字段
    risk_id: str = ""
    clause_no: str = ""


class ReviewLLMOut(BaseModel):
    """审查 LLM 批量输出 schema"""

    risks: list[RiskItem]


class Decision(BaseModel):
    """法务对某条风险的决策"""

    risk_id: str
    type: Literal["accepted", "modified", "rejected"]
    text: str | None = None  # accepted=suggestion 原文；modified=用户编辑后文本
    reason: str | None = None  # rejected 时可选原因


class ReviewStats(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class ReviewSession(BaseModel):
    """一次审查的完整会话状态"""

    id: str
    filename: str
    file_type: Literal["docx", "pdf"]
    upload_path: str | None = None  # 已无状态化：合同字节仅内存驻留；DOCX 就地替换改用 `upload_bytes`

    # 解析结果
    clauses: list[Clause] = []
    preamble_text: str = ""  # 首条款前内容（标题/编号/双方信息）
    tail_text: str = ""  # 签署区（不参与审查，导出原样保留）
    # PDF 重建导出用：preamble/tail 的行列表
    preamble_lines: list[str] = []
    tail_lines: list[str] = []

    # 原始上传字节（DOCX 就地替换导出仍需打开原件；无状态化下保留在 session 内存中）
    upload_bytes: bytes | None = None

    # 审查状态机
    status: Literal["uploaded", "processing", "completed", "failed"] = "uploaded"
    progress: int = 0
    stage: str = ""
    error: str | None = None

    # 审查结果
    risks: list[RiskItem] = []
    score: int = 0
    truncated_salvaged: bool = False

    # 法务决策 risk_id -> Decision
    decisions: dict[str, Decision] = {}


class DecisionIn(BaseModel):
    decisions: list[Decision]
