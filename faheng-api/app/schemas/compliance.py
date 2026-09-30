"""履约模块 pydantic 模型（LLM 输出层 + API 请求层）"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContractMetaLLM(BaseModel):
    """合同元信息（LLM 提取，代码兜底校验）"""

    sign_date: str = ""  # 签署日 YYYY-MM-DD，空 = 未提取到
    contract_start: str = ""  # 合同起始日
    contract_end: str = ""  # 合同到期日


class ComplianceNodeLLM(BaseModel):
    """单个履约节点的结构化描述（LLM 只抽结构，不做日期加减）"""

    ref: str = Field(description="候选编号，如 C04#4.1(2)，必须来自候选列表")
    node_type: Literal[
        "payment",
        "deposit",
        "delivery",
        "expiry",
        "notice",
        "termination",
        "other",
    ] = "other"
    title: str = Field(description="节点短标题，12 字以内，如「支付季度租金」")
    description: str = Field(default="", description="义务内容一句话")
    anchor: Literal["absolute", "sign_date", "contract_start", "contract_end"] = (
        "sign_date"
    )
    anchor_date: str = Field(
        default="", description="anchor=absolute 时原样抄条款日期 YYYY-MM-DD"
    )
    offset_days: int = Field(
        default=0, description="锚点后天数偏移：签署后3日=3；每期开始前7日内=-7"
    )
    offset_months: int = Field(default=0, description="锚点后月数偏移：终止后2年=24")
    recurring: Literal["none", "monthly", "quarterly", "yearly"] = "none"
    needs_review: bool = Field(
        default=False, description="依赖未来事件（验收后/通知后）无法定日时为 true"
    )


class ComplianceLLMOut(BaseModel):
    """履约提取 LLM 批量输出 schema"""

    meta: ContractMetaLLM = Field(default_factory=ContractMetaLLM)
    nodes: list[ComplianceNodeLLM] = []


# ── API 请求体 ──


class MilestoneStatusIn(BaseModel):
    status: Literal["pending", "done", "skipped"]


class MilestoneDueDateIn(BaseModel):
    due_date: str  # "YYYY-MM-DD"；空串 = 清空回待确认


class NotificationReadIn(BaseModel):
    ids: list[int] = []
    all: bool = False
