"""中文合同条款切分（纯函数）。

规则：
- 首个"第X条"匹配行之前 = preamble（标题/编号/双方信息）
- 每条款从"第X条"行起，到下一条款或签署区为止
- 签署区（（盖章）/授权代表/签署日期…出现在至少一个条款之后）起 = tail，不参与审查
- 降级：全文无"第X条"时按空行分块为伪条款，流程不中断
"""
from __future__ import annotations

import re

from app.schemas.review import Clause

CLAUSE_RE = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+条")
SIGNATURE_HINTS = ("（盖章）", "(盖章)", "授权代表", "签署日期", "签字盖章", "（签字）", "(签字)")

# 条款标题行："第五条 合同金额与支付" → 编号 + 标题
CLAUSE_NO_RE = re.compile(r"^\s*(第[一二三四五六七八九十百零〇\d]+条)\s*(.*)$")


def split_clauses(lines: list[str]) -> tuple[list[Clause], list[str], list[str]]:
    """输入段落/行列表，输出 (clauses, preamble_lines, tail_lines)"""
    # 定位所有条款起始行与签署区起始行
    clause_starts: list[int] = []
    signature_start: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if CLAUSE_RE.match(stripped):
            if signature_start is None:  # 签署区之后不再视为条款
                clause_starts.append(i)
            continue
        if (
            signature_start is None
            and clause_starts  # 必须已出现过条款
            and any(h in stripped for h in SIGNATURE_HINTS)
        ):
            signature_start = i

    # 降级：无条款命中 → 按空行分块为伪条款
    if not clause_starts:
        return _fallback_split(lines)

    tail_from = signature_start if signature_start is not None else len(lines)

    preamble_lines = [l for l in lines[: clause_starts[0]] if l.strip()]
    tail_lines = [l for l in lines[tail_from:] if l.strip()]

    clauses: list[Clause] = []
    for n, start in enumerate(clause_starts):
        end = clause_starts[n + 1] if n + 1 < len(clause_starts) else tail_from
        block = lines[start:end]
        non_empty = [l for l in block if l.strip()]
        if not non_empty:
            continue
        first = non_empty[0].strip()
        m = CLAUSE_NO_RE.match(first)
        clause_no = m.group(1) if m else first[:12]
        title = (m.group(2).strip() if m and m.group(2) else "")
        clauses.append(
            Clause(
                clause_id=f"C{len(clauses) + 1:02d}",
                clause_no=clause_no,
                title=title,
                text="\n".join(non_empty),
                start_idx=start,
                end_idx=start + len(block) - 1,
            )
        )
    return clauses, preamble_lines, tail_lines


def _fallback_split(lines: list[str]) -> tuple[list[Clause], list[str], list[str]]:
    """伪条款降级：按空行分块，块数≥2 才切，否则整篇一块"""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    current_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            if not current:
                current_start = i
            current.append(line)
        else:
            if current:
                blocks.append((current_start, current))
                current = []
    if current:
        blocks.append((current_start, current))

    if len(blocks) <= 1:
        # 整篇一块：前几行作 preamble，其余为一个伪条款
        non_empty = [(i, l) for i, l in enumerate(lines) if l.strip()]
        if not non_empty:
            return [], [], []
        if len(non_empty) <= 3:
            return [], [l for _, l in non_empty], []
        pre = [l for _, l in non_empty[:3]]
        body = non_empty[3:]
        clause = Clause(
            clause_id="C01",
            clause_no=body[0][1].strip()[:12],
            title="",
            text="\n".join(l for _, l in body),
            start_idx=body[0][0],
            end_idx=body[-1][0],
        )
        return [clause], pre, []

    clauses: list[Clause] = []
    for start_idx, block in blocks:
        first = block[0].strip()
        clauses.append(
            Clause(
                clause_id=f"C{len(clauses) + 1:02d}",
                clause_no=first[:12],
                title="",
                text="\n".join(block),
                start_idx=start_idx,
                end_idx=start_idx + len(block) - 1,
            )
        )
    # 伪条款模式下 preamble/tail 为空（标题块也作为条款参与审查）
    return clauses, [], []
