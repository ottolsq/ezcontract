"""docx 导出三条路径：
① DOCX 上传 → 原文档就地替换（保版式）
② PDF 上传 → 全文重建（降级，前端明示）
③ 起草 markdown → docx 轻量转换
另含审核报告导出。
"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.shared import Pt

from app.config import settings
from app.schemas.review import ReviewSession

# ---------- 公共工具 ----------


def _set_east_asia(run, font_name: str = "宋体") -> None:
    """中文必须显式设置 eastAsia 字体，否则 Word 打开异常"""
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), font_name)


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


# ---------- 路径③：markdown → docx（起草导出） ----------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def _add_md_paragraph(doc, text: str, style: str | None = None):
    """支持 **粗体** 拆 run 的段落"""
    p = doc.add_paragraph(style=style)
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            run = p.add_run(text[pos : m.start()])
            _set_east_asia(run)
        run = p.add_run(m.group(1))
        run.bold = True
        _set_east_asia(run)
        pos = m.end()
    if pos < len(text):
        run = p.add_run(text[pos:])
        _set_east_asia(run)
    return p


def export_markdown_docx(title: str, markdown: str, out_name: str) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            if level == 1:
                p = doc.add_heading("", level=0)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(text)
                _set_east_asia(run, "黑体")
            else:
                p = doc.add_heading("", level=level - 1)
                run = p.add_run(text)
                _set_east_asia(run, "黑体")
                run.bold = True
        elif _LIST_RE.match(stripped):
            _add_md_paragraph(doc, stripped)  # 原样保留编号字符，避开中文列表样式坑
        else:
            _add_md_paragraph(doc, stripped)

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
