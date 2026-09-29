"""中文合同条款切分（纯函数）。

规则（Plan: 合同解析 / 子项识别 / 导出系统重构）：
- 首个"第X条"匹配行之前 = preamble（标题/编号/双方信息）
- 每条款从"第X条"行起，到下一条款或签署区为止
- 签署区（（盖章）/授权代表/签署日期…出现在至少一个条款之后）起 = tail，不参与审查
- 降级：全文无"第X条"时按空行分块为伪条款，流程不中断
- 子项 N 级嵌套：X.Y / X.Y(Z) / X.Y(Z)(a) ...；display_no 保留原文样式，
  internal_no 半角规范化、重复递增（同一父级下出现两次 (1)/(2) → 内部
  2.3(1)/2.3(2)/2.3(3)/2.3(4)）。
- 同段落多子项（`<w:br/>` 分隔的多行）：按 \\n 拆行，各自成为独立 SubItem。
"""
from __future__ import annotations

import re
from typing import Iterable

from app.parser.docx_parser import ParagraphInfo
from app.schemas.review import Clause, SubItem

CLAUSE_RE = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+条")

# 条款内子项编号（基编号）：X.Y / X.Y.Z
# 例：3.1 / 5.3 / 10.3.2
BASE_SUBITEM_RE = re.compile(
    r"^\s*(\d+\.\d+(?:\.\d+)?)[\s　:：、]"
)
# 基编号：用于检测行首（不要求后跟分隔符，给 `3.1（1）` 这种也能命中基编号）
BASE_SUBITEM_DETECT_RE = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)?)")
# 嵌套编号（任意层级括号）：(Z) / （Z） / (a) / （A）等
# 按原始字符捕获，不做全角/半角归一
NESTED_NO_RE = re.compile(
    r"^\s*((?:\([0-9０-９a-zA-Z]+\)|（[0-9０-９a-zA-Z]+）))"
)
# 合并的子项正则（用于回退兼容）：基编号 + 可选嵌套编号 + 分隔符
SUBITEM_RE = re.compile(
    r"^\s*(\d+\.\d+(?:\.\d+)?((?:\([0-9０-９]+\)|（[0-9０-９]+）))*)[\s　:：、]"
)
SIGNATURE_HINTS = ("（盖章）", "(盖章)", "授权代表", "签署日期", "签字盖章", "（签字）", "(签字)")

# 条款标题行："第五条 合同金额与支付" → 编号 + 标题
CLAUSE_NO_RE = re.compile(r"^\s*(第[一二三四五六七八九十百零〇\d]+条)\s*(.*)$")


def _to_halfwidth(s: str) -> str:
    """把全角数字 ０-９ 转为半角；全角字母不转（仅数字会影响子项编号）。"""
    if not s:
        return s
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:  # 全角 0-9
            out.append(chr(code - 0xFEE0))
        elif ch in "（）":
            out.append({"（": "(", "）": ")"}[ch])
        else:
            out.append(ch)
    return "".join(out)


def _normalize_display_token(token: str) -> str:
    """display_no 形态：保留原始括号样式，仅把全角数字 → 半角数字；括号保持原样。

    用途：构造 internal_no 时提取"风格信息"，但 internal_no 内部统一使用半角括号。
    """
    if not token:
        return token
    return token.translate(
        str.maketrans("０１２３４５６７８９", "0123456789")
    )


def _make_internal_no(path_parts: list[str]) -> str:
    """由层级路径生成半角规范化的 internal_no。path_parts 用原文 display_no 样式。"""
    if not path_parts:
        return ""
    # 基编号（X.Y）保持半角；嵌套括号统一为半角+数字
    head = _to_halfwidth(path_parts[0])
    tail = []
    for p in path_parts[1:]:
        # p 形如 "（1）" / "(a)" → 规范成 "(1)" / "(a)"
        inner = _to_halfwidth(p.strip("（）()"))
        tail.append(f"({inner})")
    return head + "".join(tail)


class _NumberingRegistry:
    """跟踪 display_no 在同一父级下的出现次数，用于生成唯一 internal_no。

    例：原文中 "7.2(1) ... 7.2(2) ... 7.2(1) ... 7.2(2)"，
    internal_no 依次为 7.2(1) / 7.2(2) / 7.2(3) / 7.2(4)。
    """

    def __init__(self) -> None:
        self._counter: dict[tuple[str, str], int] = {}
        # key = (parent_internal_no, display_no) → 当前已分配次数

    def next_index(self, parent: str, display_no: str) -> int:
        key = (parent, display_no)
        n = self._counter.get(key, 0) + 1
        self._counter[key] = n
        return n


def _scan_subitems_in_paragraph(
    text: str,
    *,
    registry: _NumberingRegistry,
    default_start: int,
    last_base: list[SubItem | None],
) -> list[SubItem]:
    """扫描一段文本（含 \\n 分隔的多行），生成 N 级嵌套子项列表。

    同一段落内的多个子项共享 start_idx/end_idx，靠 `line_in_paragraph` 区分。
    每段多子项：找到基编号 X.Y 后，按出现顺序收集后续嵌套括号；行内连续嵌套
    （如 `3.1(1)(a)` 形态）也支持。

    跨段落子项：嵌套编号独立成段（无基编号前缀）时，归属到 `last_base[0]`
    即最近一次出现的 X.Y 子项。`last_base` 由调用方传入并在每命中基编号时
    更新，从而支持「3.1 标题 + （1）独立段 + （2）独立段」的真实版式。

    重复 display_no 处理：同级基编号覆盖范围内（如 7.2 下的 (1)/(2)）若
    出现重复 display_no（如 7.2(1)/7.2(2)/7.2(1)/7.2(2)），内部编号追加 .N
    后缀保证唯一；display_no 仍保留原文样式。
    """
    items: list[SubItem] = []
    lines = text.split("\n")
    if not lines:
        return items

    # 段落级 subitems：每条 line_in_paragraph 对应一个最深层子项
    for line_idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        bm = BASE_SUBITEM_DETECT_RE.match(stripped)
        if not bm:
            # 不以基编号开头，可能是嵌套条目段（如整段都是 (1)(2)(3)）。
            # 尝试匹配嵌套编号；若匹配到，归属到上一个基编号作为同级。
            nm = NESTED_NO_RE.match(stripped)
            if nm and last_base[0] is not None:
                parent = last_base[0]
                # 父级 = path_parts 去掉最后一层；若 parent 本身就是 X.Y 基项，
                # 则 path_parts[:-1] = [] → 用 [base_no] 作为锚
                anchor_parts = (
                    list(parent.path_parts[:-1])
                    if len(parent.path_parts) > 1
                    else list(parent.path_parts)
                )
                _append_nested(
                    items,
                    nm.group(1),
                    parent_path_parts=anchor_parts,
                    registry=registry,
                    line_in_paragraph=line_idx,
                    start_idx=default_start,
                    end_idx=default_start,
                )
            continue

        base_no_raw = bm.group(1)  # 如 "3.1" 或 "3.1.1"
        # 找到第一个嵌套编号起点
        rest = stripped[bm.end():]
        nested_tokens: list[str] = []
        # 递归扫嵌套
        cursor = 0
        while cursor < len(rest):
            # 跳过空白分隔
            while cursor < len(rest) and rest[cursor] in " \t　:":
                cursor += 1
            if cursor >= len(rest):
                break
            m = re.match(r"([\(（][0-9０-９a-zA-Z]+[)）])", rest[cursor:])
            if not m:
                break
            nested_tokens.append(m.group(1))
            cursor += m.end()

        path_parts: list[str] = [base_no_raw] + nested_tokens
        # display_no：基编号 + 各嵌套 token（保留原文括号样式）
        display_no = base_no_raw + "".join(nested_tokens)
        # 父级 = path_parts 去掉最后一层
        parent_path_parts = path_parts[:-1]
        parent_internal_no = _make_internal_no(parent_path_parts)
        internal_no = _make_internal_no(path_parts)
        # 重复计数：(父级 internal_no, display_no)
        registry_idx = registry.next_index(parent_internal_no, display_no)
        if registry_idx > 1:
            internal_no = f"{internal_no}.{registry_idx}"

        si = SubItem(
            sub_item_no=internal_no,
            display_no=display_no,
            internal_no=internal_no,
            level=len(path_parts),
            path_parts=path_parts,
            line_in_paragraph=line_idx,
            start_idx=default_start,
            end_idx=default_start,
        )
        items.append(si)
        # 跨段落跟踪：本段路径作为后续孤儿段的父级（含所有嵌套）
        last_base[0] = si

    return items


def _append_nested(
    items: list[SubItem],
    nested_token: str,
    *,
    parent_path_parts: list[str],
    registry: _NumberingRegistry,
    line_in_paragraph: int,
    start_idx: int,
    end_idx: int,
) -> None:
    """在已发现的子项同级追加一条（仅嵌套条目的孤儿段）。

    嵌套段没有独立基编号（基编号在前一段），属于父级 X.Y 的同名同级目录：
    父级内部编号 = X.Y；display_no = X.Y + nested_token 原文；
    internal_no = X.Y(nested_token) 半角规范化后，再按同级去重加 .N 后缀。
    """
    if not parent_path_parts:
        return
    base_disp = parent_path_parts[0]  # X.Y
    # 父级 display 已有 token（除基编号外）的拼接
    parent_disp_tokens = parent_path_parts[1:]
    parent_disp_no = base_disp + "".join(parent_disp_tokens)  # X.Y(...)
    display_no = parent_disp_no + nested_token  # X.Y(...)(新) 原文样式
    parent_internal_no = _make_internal_no(parent_path_parts)
    internal_no = f"{parent_internal_no}{_to_halfwidth(nested_token.strip('（）()')) and '(' + _to_halfwidth(nested_token.strip('（）()')) + ')' or ''}"
    # 简化：直接生成 X.Y(nested)
    inner = _to_halfwidth(nested_token.strip("（）()"))
    internal_no = f"{parent_internal_no}({inner})"
    registry_idx = registry.next_index(parent_internal_no, display_no)
    if registry_idx > 1:
        internal_no = f"{internal_no}.{registry_idx}"
    items.append(
        SubItem(
            sub_item_no=internal_no,
            display_no=display_no,
            internal_no=internal_no,
            level=len(parent_path_parts) + 1,
            path_parts=list(parent_path_parts) + [nested_token],
            line_in_paragraph=line_in_paragraph,
            start_idx=start_idx,
            end_idx=end_idx,
        )
    )


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

        # N 级嵌套子项扫描（display_no / internal_no 双轨）
        registry = _NumberingRegistry()
        subitems: list[SubItem] = []
        # last_base 用单元素 list 做可变引用，跨段落传递最近一次的 X.Y 锚点
        last_base: list[SubItem | None] = [None]
        for i in range(start, end + 1):
            t = paragraphs[i].text.strip()
            if not t:
                continue
            subitems.extend(
                _scan_subitems_in_paragraph(
                    t, registry=registry, default_start=i, last_base=last_base
                )
            )

        clauses.append(
            Clause(
                clause_id=f"C{len(clauses) + 1:02d}",
                clause_no=clause_no,
                title=title,
                text="\n".join(p.text for p in non_empty_text),
                html="".join(p.html for p in block),
                start_idx=start,
                end_idx=start + len(block) - 1,
                subitems=subitems,
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
