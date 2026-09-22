"""中文合同条款切分（纯函数）。

规则：
- 首个"第X条"匹配行之前 = preamble（标题/编号/双方信息）
- 每条款从"第X条"行起，到下一条款或签署区为止
- 签署区（（盖章）/授权代表/签署日期…出现在至少一个条款之后）起 = tail，不参与审查
- 降级：全文无"第X条"时按空行分块为伪条款，流程不中断
"""
from __future__ import annotations

import re

from app.parser.docx_parser import ParagraphInfo
from app.schemas.review import Clause

CLAUSE_RE = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+条")
SIGNATURE_HINTS = ("（盖章）", "(盖章)", "授权代表", "签署日期", "签字盖章", "（签字）", "(签字)")

# 条款标题行："第五条 合同金额与支付" → 编号 + 标题
CLAUSE_NO_RE = re.compile(r"^\s*(第[一二三四五六七八九十百零〇\d]+条)\s*(.*)$")


def split_clauses(
    paragraphs: list[ParagraphInfo],
) -> tuple[list[Clause], list[ParagraphInfo], list[ParagraphInfo]]:
    """输入段落列表，输出 (clauses, preamble_paragraphs, tail_paragraphs)

    `start_idx / end_idx` 指向输入列表中的下标（含空段），导出回填依赖它。
    """
    lines = [p.text for p in paragraphs]

    clause_starts: list[int] = []
    signature_start: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if CLAUSE_RE.match(stripped):
            if signature_start is None:
                clause_starts.append(i)
            continue
        if (
            signature_start is None
            and clause_starts
            and any(h in stripped for h in SIGNATURE_HINTS)
        ):
            signature_start = i

    if not clause_starts:
        return _fallback_split(paragraphs)

    tail_from = signature_start if signature_start is not None else len(paragraphs)

    preamble = [p for p in paragraphs[: clause_starts[0]] if p.text.strip()]
    tail = [p for p in paragraphs[tail_from:] if p.text.strip()]

    clauses: list[Clause] = []
    for n, start in enumerate(clause_starts):
        end = clause_starts[n + 1] if n + 1 < len(clause_starts) else tail_from
        block = paragraphs[start:end]
        non_empty_text = [p for p in block if p.text.strip()]
        if not non_empty_text:
            continue
        first = non_empty_text[0].text.strip()
        m = CLAUSE_NO_RE.match(first)
        clause_no = m.group(1) if m else first[:12]
        title = m.group(2).strip() if m and m.group(2) else ""
        clauses.append(
            Clause(
                clause_id=f"C{len(clauses) + 1:02d}",
                clause_no=clause_no,
                title=title,
                text="\n".join(p.text for p in non_empty_text),
                html="".join(p.html for p in block),
                start_idx=start,
                end_idx=start + len(block) - 1,
            )
        )
    return clauses, preamble, tail


def _fallback_split(
    paragraphs: list[ParagraphInfo],
) -> tuple[list[Clause], list[ParagraphInfo], list[ParagraphInfo]]:
    """伪条款降级：按空行分块，块数≥2 才切，否则整篇一块"""
    blocks: list[tuple[int, list[ParagraphInfo]]] = []
    current: list[ParagraphInfo] = []
    current_start = 0
    for i, p in enumerate(paragraphs):
        if p.text.strip():
            if not current:
                current_start = i
            current.append(p)
        else:
            if current:
                blocks.append((current_start, current))
                current = []
    if current:
        blocks.append((current_start, current))

    if len(blocks) <= 1:
        non_empty = [(i, p) for i, p in enumerate(paragraphs) if p.text.strip()]
        if not non_empty:
            return [], [], []
        if len(non_empty) <= 3:
            return [], [p for _, p in non_empty], []
        pre = [p for _, p in non_empty[:3]]
        body = non_empty[3:]
        clause = Clause(
            clause_id="C01",
            clause_no=body[0][1].text.strip()[:12],
            title="",
            text="\n".join(p.text for _, p in body),
            html="".join(p.html for _, p in body),
            start_idx=body[0][0],
            end_idx=body[-1][0],
        )
        return [clause], pre, []

    clauses: list[Clause] = []
    for start_idx, block in blocks:
        first = block[0].text.strip()
        clauses.append(
            Clause(
                clause_id=f"C{len(clauses) + 1:02d}",
                clause_no=first[:12],
                title="",
                text="\n".join(p.text for p in block),
                html="".join(p.html for p in block),
                start_idx=start_idx,
                end_idx=start_idx + len(block) - 1,
            )
        )
    return clauses, [], []
