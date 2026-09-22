"""docx 导出三条路径：
① DOCX 上传 → 原文档就地替换（保版式）
② PDF 上传 → 全文重建（降级，前端明示）
③ 起草 markdown → docx 轻量转换（无 HTML 时降级）
④ 起草 HTML → docx 高保真映射（前端 TipTap WYSIWYG 导出，主路径）
另含审核报告导出。
"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt
from bs4 import BeautifulSoup

from app.config import settings
from app.schemas.review import ReviewSession

# ---------- 公共样式（公文风：A4 + 仿宋小四 + 1.5 倍行距） ----------

# 正文字体
_BODY_FONT_SIZE = Pt(12)        # 小四
_BODY_FONT_NAME = "仿宋_GB2312"
_BODY_FONT_FALLBACK = "仿宋"
# 标题字体（黑体；方正小标宋做首选，无则回落黑体）
_TITLE_FONT_NAME = "方正小标宋简体"
_TITLE_FONT_FALLBACK = "黑体"
_HEADING_FONT_NAME = "黑体"
_LINE_SPACING = 1.5
# A4 可用宽度（约 21cm - 左 2.5 - 右 2.5 = 16cm），导出表格宽度参考
_TABLE_WIDTH = Cm(16.0)


def _apply_page_setup(doc) -> None:
    """A4 纸 + 与前端 TipTap .docx-page 一致的边距（上下 28mm，左右 25mm）"""
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.8)
        section.bottom_margin = Cm(2.8)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)


def _apply_body_format(paragraph, *, alignment: WD_ALIGN_PARAGRAPH | None = None) -> None:
    """正文段落：1.5 倍行距 + 首行缩进 2 字符 + 两端对齐"""
    pf = paragraph.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING
    paragraph.alignment = alignment if alignment is not None else WD_ALIGN_PARAGRAPH.JUSTIFY
    # 首行缩进 2 字符（firstLineChars=200，单位 1/100 字符）
    pPr = paragraph._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = pPr.makeelement(qn("w:ind"), {})
        pPr.append(ind)
    ind.set(qn("w:firstLineChars"), "200")
    ind.set(qn("w:firstLine"), str(int(_BODY_FONT_SIZE.pt * 20)))


def _set_run_fonts(run, east_asia: str) -> None:
    """显式写入西文+中文+东亚字体；eastAsia 缺失时回落 fallback 由调用方传入"""
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), east_asia)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")


def _style_run(run, *, size: Pt | None = None, bold: bool = False, ea: str = _BODY_FONT_NAME) -> None:
    """统一 run 字体：西文 Times New Roman + 中文显式 eastAsia"""
    if size is None:
        size = _BODY_FONT_SIZE
    run.font.name = "Times New Roman"
    run.font.size = size
    run.bold = bold
    _set_run_fonts(run, east_asia=ea)

# ---------- 公共工具 ----------


def _set_east_asia(run, font_name: str = _BODY_FONT_NAME) -> None:
    """中文必须显式设置 eastAsia 字体，否则 Word 打开异常"""
    _style_run(run, ea=font_name)


def _new_paragraph_after(anchor_paragraph, text: str):
    """在锚段落后插入一个同格式段落（deepcopy XML，改文本）"""
    from docx.text.paragraph import Paragraph

    new_p = deepcopy(anchor_paragraph._p)
    anchor_paragraph._p.addnext(new_p)
    para = Paragraph(new_p, anchor_paragraph._parent)
    _replace_paragraph_text(para, text)
    return para


def _replace_paragraph_text(paragraph, text: str) -> None:
    """保样式替换段落文本：保留首 run 的字体属性，清空其余 run"""
    runs = paragraph.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
    else:
        run = paragraph.add_run(text)
        _set_east_asia(run)


def _highlight(paragraph) -> None:
    for r in paragraph.runs:
        if r.text.strip():
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW


# ---------- 路径①：DOCX 就地替换 ----------

LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}


def _decided_replacements(session: ReviewSession) -> dict[str, list[str]]:
    """按条款聚合最终替换文本。

    同一条款多个已采纳/修改的风险：按等级从高到低，各替换文本合并为多段。
    rejected / 未决策：不替换。
    """
    risk_map = {r.risk_id: r for r in session.risks}
    by_clause: dict[str, list[tuple[int, str]]] = {}
    for d in session.decisions.values():
        if d.type not in ("accepted", "modified"):
            continue
        risk = risk_map.get(d.risk_id)
        if risk is None:
            continue
        text = (d.text or "").strip() or risk.suggestion
        by_clause.setdefault(risk.clause_id, []).append(
            (LEVEL_ORDER.get(risk.level, 3), text)
        )
    return {
        cid: [t for _, t in sorted(items, key=lambda x: x[0])]
        for cid, items in by_clause.items()
    }


def _replace_clause_span(doc, session: ReviewSession) -> None:
    """把决策后的替换文本写回 docx 原件（只动命中条款的段落区间）"""
    clause_map = {c.clause_id: c for c in session.clauses}
    replacements = _decided_replacements(session)

    # 收集需要删除的段落区间（先记录元素引用，避免索引位移）
    to_delete: list = []
    for cid, new_texts in replacements.items():
        clause = clause_map[cid]
        paras = doc.paragraphs
        first = paras[clause.start_idx]

        lines = [l for l in "\n".join(new_texts).splitlines() if l.strip()]
        if not lines:
            continue

        # 首段：保样式改文本 + 高亮
        _replace_paragraph_text(first, lines[0])
        _highlight(first)

        # 区间内其余段落标记删除
        for p in paras[clause.start_idx + 1 : clause.end_idx + 1]:
            to_delete.append(p._p)

        # 追加段落（倒序插在 first 之后，保持顺序）——注意要在删除之前基于 XML 插入
        anchor = first
        for extra in lines[1:]:
            anchor = _new_paragraph_after(anchor, extra)
            _highlight(anchor)

    # 统一删除旧段落
    for el in to_delete:
        el.getparent().remove(el)


def export_docx_inplace(session: ReviewSession) -> Path:
    from docx import Document

    doc = Document(session.upload_path)
    _replace_clause_span(doc, session)
    out = settings.EXPORT_DIR / f"{session.id}_final.docx"
    doc.save(str(out))
    return out


# ---------- 路径②：PDF 重建 ----------


def _build_rebuilt_docx(session: ReviewSession) -> "object":
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    clause_map = {c.clause_id: c for c in session.clauses}
    replacements = _decided_replacements(session)

    # 标题（preamble 第一行）
    title = session.preamble_lines[0] if session.preamble_lines else session.filename
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(16)
    _set_east_asia(run, "黑体")

    # preamble 其余行
    for line in session.preamble_lines[1:]:
        p = doc.add_paragraph()
        run = p.add_run(line)
        _set_east_asia(run)

    # 条款（应用替换 + 高亮）
    for c in session.clauses:
        new_texts = replacements.get(c.clause_id)
        if new_texts:
            for line in [l for l in "\n".join(new_texts).splitlines() if l.strip()]:
                p = doc.add_paragraph()
                run = p.add_run(line)
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                _set_east_asia(run)
        else:
            for line in c.text.splitlines():
                p = doc.add_paragraph()
                run = p.add_run(line)
                _set_east_asia(run)

    # tail
    for line in session.tail_lines:
        p = doc.add_paragraph()
        run = p.add_run(line)
        _set_east_asia(run)
    return doc


def export_docx_rebuilt(session: ReviewSession) -> Path:
    doc = _build_rebuilt_docx(session)
    out = settings.EXPORT_DIR / f"{session.id}_final.docx"
    doc.save(str(out))
    return out


def export_final_docx(session: ReviewSession) -> Path:
    if session.file_type == "docx":
        return export_docx_inplace(session)
    return export_docx_rebuilt(session)


# ---------- 路径③：markdown → docx（起草导出 - 降级） ----------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def _add_md_paragraph(doc, text: str, style: str | None = None, *, indent: bool = True):
    """支持 **粗体** 拆 run 的段落；正文样式（首行缩进/行距/字体）由 _apply_body_format 统一应用"""
    p = doc.add_paragraph(style=style)
    _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY if indent else WD_ALIGN_PARAGRAPH.LEFT)
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            run = p.add_run(text[pos : m.start()])
            _style_run(run)
        run = p.add_run(m.group(1))
        _style_run(run, bold=True)
        pos = m.end()
    if pos < len(text):
        run = p.add_run(text[pos:])
        _style_run(run)
    return p


def export_markdown_docx(title: str, markdown: str, out_name: str) -> Path:
    from docx import Document

    doc = Document()
    _apply_page_setup(doc)

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            # 大标题：方正小标宋简体 / 黑体回落，二号，加粗居中
            if level == 1:
                p = doc.add_paragraph()
                _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.CENTER)
                pPr = p._p.get_or_add_pPr()
                ind = pPr.find(qn("w:ind"))
                if ind is not None:
                    pPr.remove(ind)
                run = p.add_run(text)
                _style_run(run, size=Pt(22), bold=True, ea=_TITLE_FONT_NAME)
                # Word 若找不到方正小标宋会自动回落；保留单字声明即可
            else:
                # 一级标题：黑体小四，加粗左对齐
                p = doc.add_paragraph()
                _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.LEFT)
                pPr = p._p.get_or_add_pPr()
                ind = pPr.find(qn("w:ind"))
                if ind is not None:
                    pPr.remove(ind)
                run = p.add_run(text)
                _style_run(run, size=Pt(14), bold=True, ea=_HEADING_FONT_NAME)
        elif _LIST_RE.match(stripped):
            # 列表项保留编号字符 + 首行缩进 2 字符
            _add_md_paragraph(doc, stripped, indent=True)
        else:
            _add_md_paragraph(doc, stripped, indent=True)

    out = settings.EXPORT_DIR / out_name
    doc.save(str(out))
    return out


# ---------- 路径④：HTML → docx（前端 TipTap WYSIWYG 导出 - 主路径） ----------
# 与前端 RichEditor 的 .docx-prose / .docx-page CSS 严格对齐，确保导出效果 = 页面效果


def _parse_text_align(style: str | None) -> WD_ALIGN_PARAGRAPH:
    if not style:
        return WD_ALIGN_PARAGRAPH.JUSTIFY
    s = style.lower()
    if "center" in s:
        return WD_ALIGN_PARAGRAPH.CENTER
    if "right" in s:
        return WD_ALIGN_PARAGRAPH.RIGHT
    if "justify" in s:
        return WD_ALIGN_PARAGRAPH.JUSTIFY
    if "left" in s:
        return WD_ALIGN_PARAGRAPH.LEFT
    return WD_ALIGN_PARAGRAPH.JUSTIFY


def _shade_cell(cell, hex_color: str) -> None:
    """给单元格加底纹（用于表头浅灰底）"""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = tc_pr.makeelement(qn("w:shd"), {})
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)


def _set_table_borders(table) -> None:
    """给表格加 1pt 黑色边框，与前端 .docx-table 风格一致"""
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = tbl_pr.makeelement(qn("w:tblBorders"), {})
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = borders.makeelement(qn(f"w:{edge}"), {})
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")  # 1pt = sz 8
        el.set(qn("w:color"), "1d2b4f")


def _add_html_runs(paragraph, element, *, size: Pt, east_asia: str) -> None:
    """递归处理 inline 节点：strong/em/u/s/a/span 以及纯文本。

    python-docx 的 run 不能嵌套；遇到 strong+em 这种需要拆为多个 run。
    简化策略：把每个 inline 节点按样式合并为同一 run 的属性，文本用 get_text() 展平；
    子节点继续递归以保留顺序与嵌套样式。
    """
    for child in element.children:
        if getattr(child, "name", None) is None:
            text = str(child)
            if text:
                run = paragraph.add_run(text)
                _style_run(run, size=size, ea=east_asia)
            continue

        tag = child.name.lower()
        if tag == "br":
            # 段落内换行：插入一个 break
            run = paragraph.add_run()
            br = run._element.makeelement(qn("w:br"), {})
            run._element.append(br)
            continue

        # 行内元素：先把自身的样式应用到一个 run（用自身文本）
        own_text = child.get_text() if list(child.children) else ""
        if own_text:
            run = paragraph.add_run(own_text)
            bold = tag in ("strong", "b")
            italic = tag in ("em", "i")
            underline = tag in ("u",)
            strike = tag in ("s", "del", "strike")
            run.bold = bold
            run.italic = italic
            if underline:
                run.underline = True
            if strike:
                run.font.strike = True
            run.font.size = size
            _set_run_fonts(run, east_asia=east_asia)


def _add_paragraph_from_element(doc, p_elem) -> None:
    """<p> 节点映射为 docx 段落：保留对齐、首行缩进、行间距；行内样式递归处理"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING
    pf.space_after = Pt(8)

    align = _parse_text_align(p_elem.get("style"))
    p.alignment = align

    # 居中段落无首行缩进（与前端 h1/居中段对齐）
    if align != WD_ALIGN_PARAGRAPH.CENTER:
        pf.first_line_indent = Cm(0.74)  # ≈ 2em @ 12pt
    _add_html_runs(p, p_elem, size=_BODY_FONT_SIZE, east_asia=_BODY_FONT_NAME)


def _add_heading_from_element(doc, h_elem, level: int) -> None:
    """<h1>/<h2> 节点映射为 docx 段落"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING

    if level == 1:
        size = Pt(22)
        east_asia = _TITLE_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_after = Pt(18)
    else:  # h2/h3 都用 H2 样式（一级标题）
        size = Pt(14)
        east_asia = _HEADING_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.LEFT
        pf.space_before = Pt(18)
        pf.space_after = Pt(10)

    p.alignment = align
    # 标题无首行缩进
    pPr = p._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = pPr.makeelement(qn("w:ind"), {})
        pPr.append(ind)
    ind.set(qn("w:firstLineChars"), "0")
    ind.set(qn("w:firstLine"), "0")

    run = p.add_run(h_elem.get_text())
    _style_run(run, size=size, bold=True, ea=east_asia)


def _add_list_from_element(doc, list_elem) -> None:
    """<ul>/<ol> 节点映射为多个 docx 段落，悬挂缩进 2em"""
    is_ordered = list_elem.name == "ol"
    idx = 1
    for li in list_elem.find_all("li", recursive=False):
        marker = f"{idx}. " if is_ordered else "•  "
        idx += 1
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        pf.line_spacing = _LINE_SPACING
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(-0.74)  # 悬挂缩进：首行顶格，二行起缩进
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        marker_run = p.add_run(marker)
        _style_run(marker_run)
        _add_html_runs(p, li, size=_BODY_FONT_SIZE, east_asia=_BODY_FONT_NAME)


def _add_table_from_element(doc, table_elem) -> None:
    """<table> 节点映射为 docx 表格：等宽列、1pt 黑边、表头加粗居中浅灰底"""
    rows = table_elem.find_all("tr", recursive=False)
    if not rows:
        return
    # 按 tr 里的 td/th 总数取最大列数（容忍 colspan=1）
    col_count = max(
        (len(r.find_all(["td", "th"], recursive=False)) for r in rows),
        default=0,
    )
    if col_count <= 0:
        return

    table = doc.add_table(rows=len(rows), cols=col_count)
    table.autofit = False
    table.allow_autofit = False
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 均匀列宽
    col_w = Cm(16.0 / col_count)
    table.width = Cm(16.0)
    for r in table.rows:
        for c in r.cells:
            c.width = col_w
    _set_table_borders(table)

    for i, tr in enumerate(rows):
        cells = tr.find_all(["td", "th"], recursive=False)
        for j, cell in enumerate(cells):
            if j >= col_count:
                break
            target = table.rows[i].cells[j]
            target.text = ""
            p = target.paragraphs[0]
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            p.paragraph_format.line_spacing = _LINE_SPACING
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.first_line_indent = Cm(0)

            is_header = cell.name == "th"
            if is_header:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _shade_cell(target, "f0f4fa")
            else:
                p.alignment = _parse_text_align(cell.get("style"))

            _add_html_runs(
                p,
                cell,
                size=_BODY_FONT_SIZE,
                east_asia=_HEADING_FONT_NAME if is_header else _BODY_FONT_NAME,
            )
            # 表头 run 加粗
            if is_header:
                for r in p.runs:
                    r.bold = True


def _iter_block_elements(root):
    """遍历 root 的直接子节点中的块级元素（h1/h2/h3/p/ul/ol/table）"""
    for child in root.children:
        if getattr(child, "name", None) is None:
            continue
        tag = child.name.lower()
        if tag in ("h1", "h2", "h3", "p", "ul", "ol", "table", "blockquote", "div"):
            if tag == "div":
                # 递归 div 内层
                yield from _iter_block_elements(child)
            else:
                yield child


def export_html_docx(title: str, html: str, out_name: str) -> Path:
    """把 TipTap 导出的 HTML 转为 docx，版式与前端 A4 页面严格一致。"""
    from docx import Document

    if not html or not html.strip():
        # 空内容时退回 markdown（兼容旧的空调用）
        return export_markdown_docx(title, "", out_name)

    doc = Document()
    _apply_page_setup(doc)

    soup = BeautifulSoup(f"<body>{html}</body>", "html.parser")
    body = soup.find("body") or soup

    for elem in _iter_block_elements(body):
        tag = elem.name.lower()
        if tag == "h1":
            _add_heading_from_element(doc, elem, 1)
        elif tag in ("h2", "h3"):
            _add_heading_from_element(doc, elem, 2)
        elif tag == "p":
            _add_paragraph_from_element(doc, elem)
        elif tag in ("ul", "ol"):
            _add_list_from_element(doc, elem)
        elif tag == "table":
            _add_table_from_element(doc, elem)
        elif tag == "blockquote":
            # 引用当作正文段落处理
            _add_paragraph_from_element(doc, elem)

    out = settings.EXPORT_DIR / out_name
    doc.save(str(out))
    return out


# ---------- 审核报告 ----------


def export_review_report(session: ReviewSession) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # 标题
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("合同审核报告")
    run.bold = True
    run.font.size = Pt(18)
    _set_east_asia(run, "黑体")

    meta = [
        f"合同文件：{session.filename}",
        f"审查结果：共 {len(session.risks)} 项风险，风险分 {session.score}/100",
        f"高风险 {sum(1 for r in session.risks if r.level == 'high')} 项 / "
        f"中风险 {sum(1 for r in session.risks if r.level == 'medium')} 项",
    ]
    for line in meta:
        p = doc.add_paragraph()
        run = p.add_run(line)
        _set_east_asia(run)

    # 逐项决策表
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    headers = ["条款", "风险", "等级", "决策", "说明"]
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        _set_east_asia(run)

    decision_label = {"accepted": "已采纳", "modified": "修改后采纳", "rejected": "不采纳"}
    for r in session.risks:
        d = session.decisions.get(r.risk_id)
        row = table.add_row().cells
        values = [
            r.clause_no,
            r.title,
            {"high": "高", "medium": "中", "low": "低"}[r.level],
            decision_label.get(d.type, "待处理") if d else "待处理",
            (d.reason or (d.text or "")[:60] or "—") if d else "—",
        ]
        for i, v in enumerate(values):
            row[i].text = ""
            run = row[i].paragraphs[0].add_run(str(v))
            _set_east_asia(run)

    # 结论
    processed = len(session.decisions)
    conclusion = (
        f"处理进度：{processed}/{len(session.risks)}。"
        + (
            "所有风险已处理完毕，可导出修改后合同。"
            if processed >= len(session.risks)
            else "仍有待处理风险项，建议完成处理后再导出最终合同。"
        )
    )
    p = doc.add_paragraph()
    run = p.add_run(conclusion)
    _set_east_asia(run)

    out = settings.EXPORT_DIR / f"{session.id}_report.docx"
    doc.save(str(out))
    return out
