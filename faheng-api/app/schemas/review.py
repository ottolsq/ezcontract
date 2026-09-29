"""审查相关 pydantic 模型（API 层 + LLM 输出层）"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SubItem(BaseModel):
    """条款内子项（X.Y / X.Y(Z) / X.Y(Z)(a) 等 N 级嵌套）。

    字段语义：
    - `sub_item_no`：向后兼容字段，等于 `internal_no`（前端旧版直接读这个字段）。
    - `display_no`：合同原文里出现的编号字符串（保留全角/半角括号、数字/字母样式）；
      导出回填时作为前缀拼回正文。
    - `internal_no`：全局唯一定位键（半角规范化、重复递增），用于下游 LLM 引用与导出
      的精确段匹配。
    - `level`：在 clause 内的层级（1 = X.Y，2 = (Z) 嵌套，3 = (a) 等）。
    - `path_parts`：层级路径列表，如 `["3.1", "(1)"]`；用于推断父级与同级编号样式。
    - `line_in_paragraph`：同一段落内第几行（0-based），处理 `<w:br/>` 分隔的多子项段。
    """

    sub_item_no: str = ""  # 向后兼容：= internal_no
    display_no: str = ""  # 原文显示编号，如 "（1）" / "(a)"
    internal_no: str = ""  # 全局唯一定位键，如 "3.1(1)" / "7.2(3)"
    level: int = 1  # 层级：1=X.Y, 2=(Z), 3=(a)...
    path_parts: list[str] = []  # 层级路径，如 ["3.1", "(1)"]
    line_in_paragraph: int = 0  # 同段多子项时第几行
    start_idx: int  # 段落在原始文档中的绝对下标
    end_idx: int

    def model_post_init(self, __context):  # type: ignore[override]
        # 让 sub_item_no 与 internal_no 自动同步（向后兼容）
        if not self.sub_item_no and self.internal_no:
            object.__setattr__(self, "sub_item_no", self.internal_no)
        elif not self.internal_no and self.sub_item_no:
            object.__setattr__(self, "internal_no", self.sub_item_no)
        return None


class Clause(BaseModel):
    """切分后的合同条款（导出回填的锚点）"""

    clause_id: str  # "C01"，LLM 引用编号
    clause_no: str  # "第五条"（原文编号，展示用）
    title: str = ""  # 条款标题（如"第五条 合同金额与支付"取后半段）
    text: str  # 完整条款文本（多段落拼合）
    html: str = ""  # 包含原段落样式的安全 HTML，供前端展示用
    start_idx: int  # docx 段落起始下标（PDF 时为行号）
    end_idx: int  # 段落结束下标（含）
    subitems: list[SubItem] = []  # 条款内 X.Y 子项（与段落下标对齐）


class RiskItem(BaseModel):
    """单条风险（LLM 单条输出 schema，risk_id/clause_no 由后端补充）"""

    clause_id: str
    title: str = Field(description="风险短标题，如：合同期内单方涨价")
    level: Literal["high", "medium", "low"]
    matched_rules: list[str] = []
    issue: str = Field(description="风险说明，80字以内")
    impact: str = Field(description="对甲方的影响，80字以内")
    suggestion: str = Field(description="完整、可直接替换原条款的条款文本")
    sub_item_no: str = Field(default="", description="风险指向的子项编号（如 5.3），无法定位或针对整条款时留空")
    # Plan B：精确编辑指令（向后兼容默认 replace）
    # - replace:     替换 clause_id ( + 可选 sub_item_no ) 对应的单位
    # - insert_after / insert_before: 在 anchor_clause_id ( + 可选 anchor_sub_item_no ) 后/前插入新单位
    # - delete:      删除 clause_id ( + 可选 sub_item_no ) 对应的单位
    operation: Literal["replace", "insert_after", "insert_before", "delete"] = "replace"
    anchor_clause_id: str = Field(default="", description="insert_* 时必填的锚点条款 id")
    anchor_sub_item_no: str = Field(default="", description="insert_* 时可选的锚点子项编号")
    new_clause_no: str = Field(default="", description="新增整条款时给出第X条编号")
    new_clause_title: str = Field(default="", description="新增整条款时给出标题")

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
    sub_item_no: str | None = None  # 与 RiskItem.sub_item_no 对齐，便于导出/重渲染直接命中子项段落
    # Plan B：透传 operation / anchor / new 字段，导出按单位执行
    operation: Literal["replace", "insert_after", "insert_before", "delete"] | None = None
    anchor_clause_id: str | None = None
    anchor_sub_item_no: str | None = None
    new_clause_no: str | None = None
    new_clause_title: str | None = None


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
    # 前端富文本展示用：preamble/tail 的安全 HTML（含原 docx 段落样式）
    preamble_html: str = ""
    tail_html: str = ""

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
