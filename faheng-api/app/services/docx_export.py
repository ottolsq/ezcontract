"""docx 导出三条路径：
① DOCX 上传 → 原文档就地替换（保版式）
② PDF 上传 → 全文重建（降级，前端明示）
③ 起草 markdown → docx 轻量转换（无 HTML 时降级）
④ 起草 HTML → docx 高保真映射（前端 TipTap WYSIWYG 导出，主路径）
另含审核报告导出。

无状态化：所有导出函数返回 ``io.BytesIO``，不落盘。
"""
from __future__ import annotations

import io
import re
from copy import deepcopy

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from bs4 import BeautifulSoup

from app.schemas.review import ReviewSession

# ---------- 公共样式（公文风：A4 + 仿宋小四 + 1.5 倍行距） ----------

# 正文字体（本机实际安装：仿宋 simfang.ttf，无 仿宋_GB2312）
_BODY_FONT_SIZE = Pt(12)        # 小四
_BODY_FONT_NAME = "仿宋"
_BODY_FONT_FALLBACK = "仿宋"
# 标题字体（本机实际安装：黑体 simhei.ttf，无 方正小标宋）
_TITLE_FONT_NAME = "黑体"
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
    """正文段落：1.5 倍行距 + 首行缩进 2 字符；对齐方式由调用方决定（默认左对齐）"""
    pf = paragraph.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING
    paragraph.alignment = alignment if alignment is not None else WD_ALIGN_PARAGRAPH.LEFT
    # 首行缩进 2 字符（firstLineChars=200，单位 1/100 字符）
    pPr = paragraph._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = pPr.makeelement(qn("w:ind"), {})
        pPr.append(ind)
    ind.set(qn("w:firstLineChars"), "200")
    # firstLine 是不支持 firstLineChars 的渲染器的回退值：2 字符 = 2 × 字号
    ind.set(qn("w:firstLine"), str(int(_BODY_FONT_SIZE.pt * 2 * 20)))


def _remove_first_line_indent(paragraph) -> None:
    """去掉首行缩进（标题等元素 CSS text-indent: 0）"""
    pPr = paragraph._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is not None:
        pPr.remove(ind)


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


def export_docx_inplace(session: ReviewSession) -> io.BytesIO:
    from docx import Document

    if not session.upload_bytes:
        # 理论不会发生（schema 保证 docx 上传时填充），兜底走重建
        return export_docx_rebuilt(session)
    doc = Document(io.BytesIO(session.upload_bytes))
    _replace_clause_span(doc, session)
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
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


def export_docx_rebuilt(session: ReviewSession) -> io.BytesIO:
    doc = _build_rebuilt_docx(session)
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out


def export_final_docx(session: ReviewSession) -> io.BytesIO:
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
    _apply_body_format(p)
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


def export_markdown_docx(title: str, markdown: str, out_name: str) -> io.BytesIO:
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
            if level == 1:
                # 大标题：黑体二号，加粗居中
                p = doc.add_paragraph()
                _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.CENTER)
                _remove_first_line_indent(p)
                run = p.add_run(text)
                _style_run(run, size=Pt(22), bold=True, ea=_TITLE_FONT_NAME)
            elif level == 2:
                # 条款标题：黑体四号，加粗左对齐顶格
                p = doc.add_paragraph()
                _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.LEFT)
                _remove_first_line_indent(p)
                run = p.add_run(text)
                _style_run(run, size=Pt(14), bold=True, ea=_HEADING_FONT_NAME)
            else:
                # 子项标题 X.Y：黑体小四，左缩进 2 字符（与 HTML 路径 h3 一致）
                p = doc.add_paragraph()
                _apply_body_format(p, alignment=WD_ALIGN_PARAGRAPH.LEFT)
                pf = p.paragraph_format
                pf.left_indent = Cm(0.74)
                pf.first_line_indent = Cm(0)
                pf.space_before = Pt(8)
                pf.space_after = Pt(6)
                run = p.add_run(text)
                _style_run(run, size=_BODY_FONT_SIZE, bold=True, ea=_HEADING_FONT_NAME)
        elif _LIST_RE.match(stripped):
            # 列表项保留编号字符 + 首行缩进 2 字符
            _add_md_paragraph(doc, stripped, indent=True)
        else:
            _add_md_paragraph(doc, stripped, indent=True)

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out


# ---------- HTML 归一化（导出前把 LLM 输出抖动的格式修齐） ----------

# 匹配 `1.1 / 1.2 / 10.3` 这种子项编号（X.Y），后面必须跟空白字符
_SUBITEM_RE = re.compile(r"^\s*\d+\.\d+(?:\.\d+)?[\s　:：、]")
# 匹配 `甲方 / 乙方` 等常见合同当事人称呼行（中文括号 + 身份 + 冒号）
_PARTY_LINE_RE = re.compile(
    r"^[\s　]*(?:甲方|乙方|丙方|丁方|出租方|承租方|采购方|供应方|卖方|买方|委托方|受托方)"
    r"(?:[（(][^)）]+[)）])?"
    r"[\s　]*[:：]"
)
# 匹配"第X条 / 第X章" 之类中文条款标题（用于清理后兜底）
_CLAUSE_TITLE_RE = re.compile(r"^[\s　]*第[一二三四五六七八九十百零0-9]+[条章节款项][\s　]")
# 匹配"鉴于"开头的引言段
_WHEREAS_RE = re.compile(r"^[\s　]*鉴于[\s　，,]")


def _split_text_by_br(p_elem) -> list[tuple[list, bool]]:
    """把 <p> 节点按 <br> 切成多段。

    返回 [(buf, has_inline_decoration), ...]，buf 是该段原始子节点列表（不调用 str()
    序列化,否则 <strong> 等 inline 标签会被转成字面量 HTML 文本）。
    has_inline_decoration 表示该段是否带 strong/em 等行内样式（仍带则不归一化为
    H3 / 称呼行,因为这些是行内语义）。
    """
    lines: list[tuple[list, bool]] = []
    buf: list = []
    for child in p_elem.children:
        if getattr(child, "name", None) is None:
            buf.append(child)
            continue
        tag = child.name.lower()
        if tag == "br":
            if buf:
                # 探测这段文本里是否含有 strong/em 等行内标签
                has_inline = any(
                    getattr(g, "name", None) and g.name.lower() in {"strong", "em", "b", "i", "u", "s"}
                    for g in buf
                )
                lines.append((buf, has_inline))
            buf = []
        else:
            buf.append(child)
    if buf:
        has_inline = any(
            getattr(g, "name", None) and g.name.lower() in {"strong", "em", "b", "i", "u", "s"}
            for g in buf
        )
        lines.append((buf, has_inline))
    return lines


def _new_paragraph_from_inlines(inlines: list, *, style: str | None = None) -> "BeautifulSoup":
    """造一个 <p>，把 inline 节点链 deepcopy 进去,保留 strong/em/u 等嵌套结构。"""
    new_p = BeautifulSoup("", "html.parser").new_tag("p")
    if style:
        new_p["style"] = style
    for child in inlines:
        new_p.append(deepcopy(child))
    return new_p


def _new_paragraph_from_text(text: str, *, style: str | None = None) -> "BeautifulSoup":
    """造一个干净的 <p>...</p>，只放纯文本"""
    p = BeautifulSoup("", "html.parser").new_tag("p")
    if style:
        p["style"] = style
    p.string = text
    return p


def _new_heading_from_text(level: int, text: str) -> "BeautifulSoup":
    tag_name = f"h{level}"
    h = BeautifulSoup("", "html.parser").new_tag(tag_name)
    h.string = text
    return h


def _collect_strong_texts(p_elem) -> list[str]:
    """收集 <p> 内所有 <strong>/<b> 节点的纯文本片段。

    返回的文本是按出现顺序、保持原始标点/空白不变的字符串列表。
    用于让生成的 h3 节点能保留部分加粗范围。
    """
    texts: list[str] = []
    for strong in p_elem.find_all(["strong", "b"]):
        s = strong.get_text()
        if s:
            texts.append(s)
    return texts


def _new_heading_from_text_with_partial_bold(level: int, text: str, bold_substrings: list[str]) -> "BeautifulSoup":
    """造一个带部分加粗的 h3：text 中属于 bold_substrings 的子串用 <strong> 包裹，其余纯文本。

    用于处理 `1.1 <strong>租赁物</strong>：指...` 这种源 HTML：
    - 整段文字进 h3，strong 范围内的部分加粗，其余普通；
    - 标签不会出现在最终 docx 里，只是过渡结构。
    """
    tag_name = f"h{level}"
    h = BeautifulSoup("", "html.parser").new_tag(tag_name)

    # 按 strong_substrings 在 text 中的位置顺序产出带 strong 包裹的混合文本
    if not bold_substrings:
        h.string = text
        return h

    # 按字符串长度从长到短匹配（避免短字符串抢先匹配错位）
    substrs = sorted(set(bold_substrings), key=lambda s: (-len(s), s))

    remaining = text
    # 使用循环：每次找首个出现的 bold 子串，拆成前/中/后
    while remaining:
        # 找出 remaining 中最早出现的 bold 子串
        first_pos = None
        first_match = None
        for sub in substrs:
            idx = remaining.find(sub)
            if idx < 0:
                continue
            if first_pos is None or idx < first_pos:
                first_pos = idx
                first_match = sub
        if first_match is None:
            if remaining:
                h.append(remaining)
            break
        if first_pos > 0:
            h.append(remaining[:first_pos])
        s_tag = BeautifulSoup("", "html.parser").new_tag("strong")
        s_tag.string = first_match
        h.append(s_tag)
        remaining = remaining[first_pos + len(first_match):]
    return h


def _strip_leading_strong_decoration(text: str) -> tuple[bool, str]:
    """剥掉行首的 **...** 包裹，返回 (是否原本有粗体, 去粗体后文本)"""
    s = text.lstrip()
    if s.startswith("**") and "**" in s[2:]:
        end = s.find("**", 2)
        if end > 2:
            inner = s[2:end]
            # 只在 inner 全是中英文字符时认为是有意义的粗体强调
            if re.fullmatch(r"[一-鿿\w\s　·•（）()：:/、\-]+", inner):
                return True, (s[: s.find("**")] + s[end + 2 :]).strip()
    return False, text




def _is_party_line(text: str) -> bool:
    return bool(_PARTY_LINE_RE.match(text))


def _is_subitem_line(text: str) -> bool:
    return bool(_SUBITEM_RE.match(text))


def _is_clause_title_line(text: str) -> bool:
    return bool(_CLAUSE_TITLE_RE.match(text))


def _is_whereas_line(text: str) -> bool:
    return bool(_WHEREAS_RE.match(text))


def _classify_line(text: str) -> str | None:
    """分类一行文本：'h2' / 'h3' / 'p' / None。None 表示无特殊处理（仍作 p）。"""
    if _is_clause_title_line(text):
        return "h2"
    if _is_subitem_line(text):
        return "h3"
    if _is_party_line(text):
        return "p"
    if _is_whereas_line(text):
        return "p"
    return None


def _split_subitem_with_colon(text: str) -> tuple[str, str] | None:
    """若文本形如 `X.Y 标题：描述`，拆成 (heading, rest)。

    heading = `X.Y 标题`（去掉行首 `**` 装饰），rest = `描述`（可能为 ""）。
    返回 None 表示不是这种格式。

    启发：标题应当较短（≤12 中文字符 + 标点）且不含 `，` `。` `；` 等强停顿标点，
    避免把 `3.1 合同总价款为人民币【金额】元（大写：【金额大写】）...` 这种长描述误判。
    标题内不允许出现未闭合的 `（` 或 `(`。
    """
    m = _SUBITEM_RE.match(text)
    if not m:
        return None
    after_marker = text[m.end():]
    sep = re.search(r"[：:]", after_marker)
    if not sep:
        return None
    heading = after_marker[: sep.start()].strip()
    rest = after_marker[sep.end():].strip()
    if not heading:
        return None
    # 标题里不允许 `，` `。` `；` `？` `！` `—` 等强停顿
    if re.search(r"[，。；？!！—]", heading):
        return None
    # 标题里不允许出现未闭合的 `（` 或 `(`
    if heading.count("（") > heading.count("）"):
        return None
    if heading.count("(") > heading.count(")"):
        return None
    # 标题里不允许出现 `【...】` 占位符说明后面还有内容
    if "【" in heading and "】" not in heading:
        return None
    # 长度启发：标题应当较短
    if len(heading) > 16:
        return None
    full_heading = f"{text[m.start():m.end()].strip()} {heading}"
    return full_heading, rest


def normalize_html_for_export(html: str) -> str:
    """导出前归一化：把 LLM 输出抖动的格式修齐，让 docx 排版与前端展示一致。

    处理：
    1. <p> 内的 <br> 分隔多行，按行内容分类重整：
       - 匹配 `X.Y ` 子项编号（剥离行首 `**` 粗体后）→ 升级为 <h3>；
       - 匹配 "甲方：..." / "乙方：..." 称呼行 → 单独成段；
       - 匹配 "第X条" 条款标题 → 升级为 <h2>；
       - 匹配 "鉴于" 引言 → 单独成段；
       - 其他 → 按行拆段。
    2. 单行 <p> 内 `X.Y 标题：描述` 形式 → 拆成 `<h3>X.Y 标题</h3>` + `<p>描述</p>`。
    3. 单行 <p> 内的行首 `**X.Y 标题**` 包裹 → 剥成 <h3>，让 X.Y 也能继承缩进。
    4. 空 <p> → 删除。
    """
    if not html or not html.strip():
        return html

    soup = BeautifulSoup(f"<body>{html}</body>", "html.parser")
    body = soup.find("body") or soup

    paragraphs = body.find_all("p", recursive=False)
    for p in list(paragraphs):
        # 只处理顶级 <p>
        if p.find_parent("p") is not None:
            continue

        text = p.get_text().strip()

        # 单行 <p>：检查是否整段就是 X.Y 子项（带 ** 粗体或裸文本）
        if not p.find("br"):
            if not text:
                p.decompose()
                continue
            stripped_bold, cleaned = _strip_leading_strong_decoration(text)
            # 形如 `1.1 ERP软件：指...` → 拆成 `<h3>1.1 ERP软件</h3>` + `<p>指...</p>`
            split = _split_subitem_with_colon(cleaned)
            if split is not None:
                heading, rest = split
                # 计算原 <p> 内 strong 包裹的子串作为「标题」加粗范围，其余不加粗。
                # heading 是「X.Y <title>」整体，希望 h3 中只有 title 部分加粗；
                # 用 strong_runs 抽取原 p 里所有 <strong> 文本片段，然后切分 heading run。
                strong_texts = _collect_strong_texts(p)
                anchor = p
                h3 = _new_heading_from_text_with_partial_bold(3, heading, strong_texts)
                anchor.insert_after(h3)
                if rest:
                    after_p = _new_paragraph_from_text(rest, style=p.get("style"))
                    h3.insert_after(after_p)
                p.decompose()
                continue
            kind = _classify_line(cleaned)
            if kind == "h3":
                # <p><strong>X.Y ...</strong>...</p> → <h3>X.Y ...</h3>
                strong_texts = _collect_strong_texts(p)
                h = _new_heading_from_text_with_partial_bold(3, cleaned, strong_texts)
                p.replace_with(h)
                continue
            if kind == "h2":
                h = _new_heading_from_text(2, cleaned)
                p.replace_with(h)
                continue
            if stripped_bold and cleaned != text:
                p.clear()
                p.string = cleaned
            continue

        # 多行 <p>（含 <br>）：按行分类重组
        lines = _split_text_by_br(p)
        if not lines:
            p.decompose()
            continue
        if len(lines) == 1:
            continue

        anchor = p
        new_nodes: list[tuple[str, object]] = []
        for line_buf, has_inline in lines:
            line_text = "".join(str(x) for x in line_buf).strip()
            if not line_text:
                continue
            stripped_bold, cleaned = _strip_leading_strong_decoration(line_text)
            # 带行内样式（strong/em 等）：保留原 inline 节点链（不丢失标签），单独成段
            if has_inline and not stripped_bold:
                new_nodes.append(("p_inlines", line_buf))
                continue
            kind = _classify_line(cleaned)
            if kind is None:
                # 形如 `1.1 ERP软件：指...` → 拆成 (h3, p)
                split = _split_subitem_with_colon(cleaned)
                if split is not None:
                    heading, rest = split
                    new_nodes.append(("h3", heading))
                    if rest:
                        new_nodes.append(("p_text", rest))
                    continue
                new_nodes.append(("p_text", cleaned))
            else:
                new_nodes.append((kind, cleaned))

        # 用新节点链式替换原 <p>（先全部插入到 anchor 后，最后删除原 <p>）
        for tag_name, content in new_nodes:
            if tag_name == "p_inlines":
                node = _new_paragraph_from_inlines(content, style=p.get("style"))  # type: ignore[arg-type]
            elif tag_name == "p_text":
                node = _new_paragraph_from_text(content, style=p.get("style"))  # type: ignore[arg-type]
            elif tag_name in ("h2", "h3"):
                node = _new_heading_from_text(int(tag_name[1]), content)  # type: ignore[arg-type]
            else:
                # 兜底：当作纯文本段落
                node = _new_paragraph_from_text(str(content), style=p.get("style"))
            anchor.insert_after(node)
            anchor = node
        p.decompose()

    return "".join(str(c) for c in body.children)


# ---------- 路径④：HTML → docx（前端 TipTap WYSIWYG 导出 - 主路径） ----------
# 与前端 RichEditor 的 .docx-prose / .docx-page CSS 严格对齐，确保导出效果 = 页面效果


def _parse_text_align(style: str | None) -> WD_ALIGN_PARAGRAPH:
    """解析行内 text-align；未设置时默认左对齐（与前端 CSS 默认一致）"""
    if not style:
        return WD_ALIGN_PARAGRAPH.LEFT
    s = style.lower()
    if "center" in s:
        return WD_ALIGN_PARAGRAPH.CENTER
    if "right" in s:
        return WD_ALIGN_PARAGRAPH.RIGHT
    if "justify" in s:
        return WD_ALIGN_PARAGRAPH.JUSTIFY
    if "left" in s:
        return WD_ALIGN_PARAGRAPH.LEFT
    return WD_ALIGN_PARAGRAPH.LEFT


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


def _add_html_runs_with_default_bold(
    paragraph, element, *, size: Pt, east_asia: str, default_bold: bool = True
) -> None:
    """递归处理 inline 节点：行内元素仍用 _add_html_runs；纯文本节点默认是否加粗由 default_bold 决定。

    主要用于 h3：让 strong 子串加粗、其余文本不加粗。
    """
    for child in element.children:
        if getattr(child, "name", None) is None:
            text = str(child)
            if text:
                run = paragraph.add_run(text)
                _style_run(run, size=size, ea=east_asia)
                run.bold = default_bold
            continue

        tag = child.name.lower()
        if tag == "br":
            run = paragraph.add_run()
            br = run._element.makeelement(qn("w:br"), {})
            run._element.append(br)
            continue

        # 行内元素：自身是 strong/em 等标签时按标签设 bold，其余文本维持 default_bold
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
    pf.space_after = Pt(8)  # 对齐前端 p { margin: 0 0 8px }

    align = _parse_text_align(p_elem.get("style"))
    p.alignment = align

    # 首行缩进 2 字符：与 _apply_body_format 一致，同时写 firstLineChars + firstLine
    # 居中段落不缩进（前端 h1 / 居中 p 不缩进）
    if align != WD_ALIGN_PARAGRAPH.CENTER:
        pPr = p._p.get_or_add_pPr()
        ind = pPr.find(qn("w:ind"))
        if ind is None:
            ind = pPr.makeelement(qn("w:ind"), {})
            pPr.append(ind)
        ind.set(qn("w:firstLineChars"), "200")
        ind.set(qn("w:firstLine"), str(int(_BODY_FONT_SIZE.pt * 2 * 20)))
    _add_html_runs(p, p_elem, size=_BODY_FONT_SIZE, east_asia=_BODY_FONT_NAME)


def _add_heading_from_element(doc, h_elem, level: int) -> None:
    """<h1>/<h2>/<h3> 节点映射为 docx 段落。

    H1=合同名（居中 22pt 黑体）；H2=第X条（顶格 14pt 黑体）；
    H3=X.Y 子项（左缩进 2 字符 12pt 黑体，体现层级从属）。
    """
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING

    if level == 1:
        size = Pt(22)
        east_asia = _TITLE_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_after = Pt(18)  # 前端 h1 { margin: 0 0 18px }
    elif level == 2:
        size = Pt(14)
        east_asia = _HEADING_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.LEFT
        pf.space_before = Pt(18)  # 前端 h2 { margin: 18px 0 10px }
        pf.space_after = Pt(10)
    else:  # h3：子项标题，缩进 2 字符与正文首行对齐
        size = _BODY_FONT_SIZE
        east_asia = _HEADING_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.LEFT
        pf.space_before = Pt(8)
        pf.space_after = Pt(6)
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(0)  # 整段已缩进，首行不再额外缩

    p.alignment = align
    if level <= 2:
        # 一二级标题无首行缩进（前端 h1/h2 { text-indent: 0 }）
        _remove_first_line_indent(p)

    # h3 内的 <strong> 子节点需要在导出 docx 里只让标题部分加粗，
    # 其余字符不沿用整段加粗样式（默认 heading 整段 bold）。
    if level == 3:
        _add_html_runs_with_default_bold(p, h_elem, size=size, east_asia=east_asia, default_bold=False)
    else:
        run = p.add_run(h_elem.get_text())
        _style_run(run, size=size, bold=True, ea=east_asia)


def _add_list_from_element(doc, list_elem) -> None:
    """<ul>/<ol> 节点映射为多个 docx 段落。

    与前端 .docx-prose ul/ol { padding-left: 2em } 对齐：
    左缩进 2em，标记顶格（悬挂缩进）。
    """
    is_ordered = list_elem.name == "ol"
    idx = 1
    for li in list_elem.find_all("li", recursive=False):
        marker = f"{idx}. " if is_ordered else "•  "
        idx += 1
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        pf.line_spacing = _LINE_SPACING
        pf.space_after = Pt(2)  # 前端 li { margin: 2px 0 }
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(-0.74)  # 悬挂缩进：标记顶格，正文对齐
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

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


def export_html_docx(title: str, html: str, out_name: str) -> io.BytesIO:
    """把编辑器导出的 HTML 转为 docx，版式与前端 A4 页面严格一致。"""
    from docx import Document

    if not html or not html.strip():
        # 空内容时退回 markdown（兼容旧的空调用）
        return export_markdown_docx(title, "", out_name)

    # 先归一化：把 <br> 分隔的多行段落拆开，把 X.Y 子项升级为 h3，把称呼行 / 鉴于 / 第X条
    # 分类成独立段落，避免 docx 只对段落首行缩进而漏掉后续行
    normalized = normalize_html_for_export(html)

    doc = Document()
    _apply_page_setup(doc)

    soup = BeautifulSoup(f"<body>{normalized}</body>", "html.parser")
    body = soup.find("body") or soup

    for elem in _iter_block_elements(body):
        tag = elem.name.lower()
        if tag == "h1":
            _add_heading_from_element(doc, elem, 1)
        elif tag in ("h2", "h3"):
            _add_heading_from_element(doc, elem, 2 if tag == "h2" else 3)
        elif tag == "p":
            _add_paragraph_from_element(doc, elem)
        elif tag in ("ul", "ol"):
            _add_list_from_element(doc, elem)
        elif tag == "table":
            _add_table_from_element(doc, elem)
        elif tag == "blockquote":
            # 引用当作正文段落处理
            _add_paragraph_from_element(doc, elem)

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out


# ---------- 审核报告 ----------


def export_review_report(session: ReviewSession) -> io.BytesIO:
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

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out
