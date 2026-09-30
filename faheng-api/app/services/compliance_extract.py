"""履约节点候选预筛选（纯函数，不调 LLM）

流程：把每个条款的段落按 \\n 拆成行 → 行命中日期/时间关键词即成为候选 →
按 subitems 的 (start_idx, line_in_paragraph) 把行归属到子项，生成稳定 ref
（如 `C04#4.1(2)`）。preamble/tail 中命中日期的行只作为元信息（签署日期等）
供 LLM 提取 meta，不作为节点来源。

预筛原则：宁多勿漏 —— LLM 在 prompt 约束下会丢弃"无时间约束"的候选；
但关键词要避免高频误命中（"支付"单独出现不算，防止"支付方式为银行转账"混入）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.parser.docx_parser import ParagraphInfo
from app.schemas.review import Clause, SubItem
from app.services.compliance_dates import DATE_RE

# 时间约束关键词（"支付"单独不算；"支付周期/按季/每月"等周期词才算）
TIME_KW_RE = re.compile(
    r"期限|日内|日前|之前|以内|期满|到期|终止|生效|"
    r"每季|每月|每年|每半年|按季|按月|按年|"
    r"支付周期|周期|签署|退还|交付|验收|结算|书面通知|"
    r"\d+\s*个月|\d+\s*年|\d+\s*日|\d+\s*天"
)

MAX_CANDIDATES = 24
MAX_TEXT_CHARS = 200


@dataclass
class CandidateUnit:
    """一个预筛候选：条款内某一行（可能归属某个子项）"""

    ref: str  # "C04#4.1(2)"（子项行）或 "C04#L2"（无子项归属的正文行）
    display_ref: str  # "第4条 4.1（2）"（display_no 保留原文样式）
    text: str  # 命中的原文行（截断到 MAX_TEXT_CHARS）
    meta: dict = field(default_factory=dict)  # 扩展位：para_idx/line_no


def iter_clause_lines(
    clause: Clause, paragraphs: list[ParagraphInfo]
) -> list[tuple[int, int, str]]:
    """把条款段落拆成行，返回 [(para_idx, line_no, line_text)]。

    para_idx 为文档段落绝对下标，line_no 为段内行号（0 起，与 SubItem.line_in_paragraph 对齐）。
    """
    out: list[tuple[int, int, str]] = []
    for i in range(clause.start_idx, min(clause.end_idx + 1, len(paragraphs))):
        for line_no, line in enumerate(paragraphs[i].text.split("\n")):
            if line.strip():
                out.append((i, line_no, line.strip()))
    return out


def assign_line_to_subitem(
    clause: Clause, para_idx: int, line_no: int
) -> SubItem | None:
    """找 (para_idx, line_no) 位置所属的子项：按 (start_idx, line_in_paragraph)
    排序后取「位置 ≤ 该行」的最近一个；无 → None（条款根正文）。

    同段落多行共享 start_idx，靠 line_in_paragraph 区分；子项行自身也命中自己。
    """
    best: SubItem | None = None
    for s in clause.subitems:
        if s.start_idx > para_idx:
            continue
        if s.start_idx == para_idx and s.line_in_paragraph > line_no:
            continue
        # 该子项位于本行或之前
        if best is None or (s.start_idx, s.line_in_paragraph) > (
            best.start_idx,
            best.line_in_paragraph,
        ):
            best = s
    return best


def _line_is_candidate(line: str) -> bool:
    """命中日期或时间关键词 → 候选行。"""
    return bool(DATE_RE.search(line) or TIME_KW_RE.search(line))


def prefilter_candidates(
    clauses: list[Clause],
    paragraphs: list[ParagraphInfo],
) -> list[CandidateUnit]:
    """扫描全部条款行，产出候选列表（按条款顺序，截断到 MAX_CANDIDATES）。"""
    out: list[CandidateUnit] = []
    for clause in clauses:
        for para_idx, line_no, line in iter_clause_lines(clause, paragraphs):
            if len(out) >= MAX_CANDIDATES:
                return out
            if not _line_is_candidate(line):
                continue
            sub = assign_line_to_subitem(clause, para_idx, line_no)
            if sub is not None and sub.internal_no:
                ref = f"{clause.clause_id}#{sub.internal_no}"
                display_ref = f"{clause.clause_no} {sub.display_no or sub.internal_no}"
            else:
                # 无子项归属：用段内序号做稳定 ref
                body_line = sum(
                    1
                    for p, l, _ in iter_clause_lines(clause, paragraphs)
                    if (p, l) < (para_idx, line_no)
                )
                ref = f"{clause.clause_id}#L{body_line}"
                display_ref = clause.clause_no
            out.append(
                CandidateUnit(
                    ref=ref,
                    display_ref=display_ref,
                    text=line[:MAX_TEXT_CHARS],
                    meta={"para_idx": para_idx, "line_no": line_no},
                )
            )
    return out


def collect_meta_lines(
    preamble: list[ParagraphInfo], tail: list[ParagraphInfo]
) -> list[str]:
    """preamble/tail 中含日期的行（签署日期等），仅供 LLM 提取 meta。"""
    out: list[str] = []
    for p in [*preamble, *tail]:
        for line in p.text.split("\n"):
            line = line.strip()
            if line and DATE_RE.search(line):
                out.append(line[:MAX_TEXT_CHARS])
    return out[:10]
