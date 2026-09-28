"""docx 导出三条路径：
① DOCX 上传 → 原文档就地替换（保版式）
② PDF 上传 → 全文重建（降级，前端明示）
③ 起草 markdown → docx 轻量转换（无 HTML 时降级）
④ 起草 HTML → docx 高保真映射（前端 TipTap WYSIWYG 导出，主路径）
另含审核报告导出。

Plan B：精确按单位编辑 —— 决策中携带 operation / anchor 信息，
导出时按 (clause_id, sub_item_no, operation) 组成 EditAction，
按文档绝对位置排序后从后往前应用，避免下标漂移。

无状态化：所有导出函数返回 ``io.BytesIO``，不落盘。
"""
from __future__ import annotations

import io
import re
from copy import deepcopy
from dataclasses import dataclass

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from bs4 import BeautifulSoup

from app.schemas.review import ReviewSession

# ---------- 公共样式（公文风：A4 + 仿宋小四 + 1.5 倍行距） ----------

# 正文字体（本机实际安装：仿宋 simfang.ttf，无 仿宋_GB2312）
_BODY_FONT_SIZE = Pt(12)        # 小四
_BODY_FONT_NAME = "仿宋"
# 标题字体（本机实际安装：黑体 simhei.ttf，无 方正小标宋）
_TITLE_FONT_NAME = "黑体"
_HEADING_FONT_NAME = "黑体"
_LINE_SPACING = 1.5


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


def _replace_paragraph_text(paragraph, text: str) -> None:
    """保样式替换段落文本：保留首个 run 的字体属性作为新文本样式，
    清空其余 run/hyperlink 内的所有 w:t，确保旧文本不残留。
    """
    runs = list(paragraph.runs)
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
    else:
        run = paragraph.add_run(text)
        _set_east_asia(run)
    # 兜底：遍历 paragraph 内所有 w:t（包括嵌套在 w:hyperlink / w:fldSimple 等容器内的），
    # 如果有 w:t 不在 paragraph.runs 列表内（python-docx 没识别的容器），强制清空。
    # 这是「前后内容都存在」类 bug 的根因修复。
    body_runs = paragraph._p.findall(qn("w:r"))
    first_run_text_set = False
    for r in body_runs:
        for t in r.findall(qn("w:t")):
            if not first_run_text_set:
                t.text = text
                first_run_text_set = True
                t.set(qn("xml:space"), "preserve")
            else:
                t.text = ""
    # hyperlink 内的 run/w:t：xpath 递归找所有嵌套的 w:t 清空
    for hl in paragraph._p.findall(qn("w:hyperlink")):
        for t in hl.iter(qn("w:t")):
            t.text = ""
    for fs in paragraph._p.findall(qn("w:fldSimple")):
        for t in fs.iter(qn("w:t")):
            t.text = ""


# ---------- 段落级相似度匹配（导出回填用） ----------


def _strip_for_similarity(s: str) -> str:
    """去掉标点和空白，仅保留中英文字符，方便做相似度比对。"""
    import re as _re

    return _re.sub(r"[\s　，,。.；;：:！!？?()（）【】\[\]<>《》""'']", "", s).lower()


def _paragraph_similarity(a: str, b: str) -> float:
    """字符级 Jaccard 相似度。空文本视为 0。"""
    sa = set(_strip_for_similarity(a))
    sb = set(_strip_for_similarity(b))
    if not sa or not sb:
        return 0.0
    inter = sum(1 for c in sa if c in sb)
    return inter / (len(sa) + len(sb) - inter)


# ---------- Plan B：EditAction 调度 ----------

# 单条精确编辑动作（按单位语义：replace / insert_* / delete）。
# sort_key 是文档绝对位置（段落下标；insert_after 取锚点+0.5），调度层先按 sort_key
# 升序收集，再在应用层倒序遍历，避免下标漂移。
@dataclass
class EditAction:
    operation: str  # "replace" | "insert_after" | "insert_before" | "delete"
    # replace / delete 时的目标
    target_clause_id: str = ""
    target_sub_item_no: str = ""
    # insert_* 时的锚点
    anchor_clause_id: str = ""
    anchor_sub_item_no: str = ""
    # 新内容（delete 时可为空）
    new_text: str = ""
    # 仅用于排序（不参与语义）
    sort_key: float = 0.0
    # 仅用于日志
    level: str = "medium"
    risk_id: str = ""


def _build_edit_plan(session: ReviewSession) -> list[EditAction]:
    """把所有 accepted / modified 决策转换为 EditAction，并赋文档级 sort_key。

    - replace / delete 的 sort_key 取该单位的 start_idx（命中 sub_item_no 时）或所在 clause.start_idx。
    - insert_before 取锚点 sort_key；insert_after 取锚点 + 0.5。
    - 跨条款 insert：anchor_clause_id != risk.clause_id 时，sort_key 仍按锚点 clause 计算，
      这样调度时插入的 paragraph 会落到 anchor clause 段内（导出结果正确）。
    - sort_key 冲突时（同一段同时 insert_after + insert_before），按字典序 stable。
    """
    risk_map = {r.risk_id: r for r in session.risks}
    clause_map = {c.clause_id: c for c in session.clauses}
    actions: list[EditAction] = []
    for d in session.decisions.values():
        if d.type not in ("accepted", "modified"):
            continue
        r = risk_map.get(d.risk_id)
        if r is None:
            continue
        op = (d.operation or r.operation or "replace").strip()
        target_cid = r.clause_id
        target_sub = (d.sub_item_no or r.sub_item_no or "").strip()
        anchor_cid = (d.anchor_clause_id or r.anchor_clause_id or "").strip() or target_cid
        anchor_sub = (d.anchor_sub_item_no or r.anchor_sub_item_no or "").strip()
        new_text = (d.text or "").strip() or (r.suggestion or "").strip()
        if op != "delete" and not new_text:
            continue

        sort_key = 0.0
        if op in ("replace", "delete"):
            clause = clause_map.get(target_cid)
            if clause:
                sort_key = float(_subitem_or_clause_idx(clause, target_sub))
        elif op == "insert_before":
            clause = clause_map.get(anchor_cid)
            if clause:
                sort_key = float(_subitem_or_clause_idx(clause, anchor_sub))
        elif op == "insert_after":
            clause = clause_map.get(anchor_cid)
            if clause:
                sort_key = float(_subitem_or_clause_idx(clause, anchor_sub)) + 0.5

        actions.append(
            EditAction(
                operation=op,
                target_clause_id=target_cid,
                target_sub_item_no=target_sub,
                anchor_clause_id=anchor_cid,
                anchor_sub_item_no=anchor_sub,
                new_text=new_text,
                sort_key=sort_key,
                level=r.level,
                risk_id=r.risk_id,
            )
        )
    # 升序；同 docx 下子项编号字典序作为稳定 tie-breaker，避免顺序漂移
    actions.sort(key=lambda a: (a.sort_key, a.target_sub_item_no, a.anchor_sub_item_no, a.operation))
    return actions


def _subitem_or_clause_idx(clause: Clause, sub_no: str) -> int:
    """优先取 sub_item_no 段落下标；未命中回落到 clause.start_idx。"""
    if sub_no:
        for s in clause.subitems:
            if s.sub_item_no == sub_no:
                return s.start_idx
    return clause.start_idx


# ---------- 路径①：DOCX 就地替换 ----------


def _apply_action_to_doc(doc, action: EditAction, clause_map: dict) -> None:
    """把单个 EditAction 落到 docx 段落。
    replace：替换目标段落文本（保留原样式）。
    insert_*：在锚点段落之后/前插入新段落，复制锚点段落样式。
    delete：删除目标段落（命中子项）或整个 clause 段区（整条款删除）。
    """
    paras = doc.paragraphs

    if action.operation == "replace":
        clause = clause_map.get(action.target_clause_id)
        if not clause:
            return
        idx = _resolve_target_idx(clause, action.target_sub_item_no)
        if idx is None or idx >= len(paras):
            return
        text = action.new_text
        # 若原段落以 X.Y 编号开头而新文本不带，自动补回编号
        orig_match = _SUBITEM_RE.match(paras[idx].text or "")
        if orig_match and not _SUBITEM_RE.match(text):
            text = f"{orig_match.group(0)}{text.lstrip()}"
        _replace_paragraph_text(paras[idx], text)
        return

    if action.operation == "delete":
        clause = clause_map.get(action.target_clause_id)
        if not clause:
            return
        if action.target_sub_item_no:
            idx = _resolve_target_idx(clause, action.target_sub_item_no)
            if idx is None:
                return
            _delete_paragraphs(paras, [idx])
            return
        # 整条款删除：清空 clause 区间内所有段落文本（保留段落本身以保版式）
        # 真正的整条款删除风险由 _postprocess 拦截，几乎不会到这里；保留兜底
        _clear_paragraphs(paras, clause.start_idx, clause.end_idx)
        return

    if action.operation in ("insert_after", "insert_before"):
        clause = clause_map.get(action.anchor_clause_id or action.target_clause_id)
        if not clause:
            return
        anchor_idx = _resolve_target_idx(clause, action.anchor_sub_item_no)
        if anchor_idx is None:
            return
        # 多行新内容（如"第X条 标题\nX.1 ...\nX.2 ..."）拆成多段插入，每段按角色套样式。
        for offset, line in enumerate(_split_insert_text(action.new_text)):
            insert_pos = anchor_idx + offset if action.operation == "insert_after" else anchor_idx - 1 - offset
            # insert_before 顺序反着插（让最终顺序正确）
            if action.operation == "insert_before":
                _insert_paragraph_before_idx(paras, anchor_idx - offset, line)
            else:
                _insert_paragraph_after(paras, insert_pos, line)
        return


def _resolve_target_idx(clause: Clause, sub_no: str) -> int | None:
    """返回目标段落下标：优先 sub_item_no；未命中则返回 clause.start_idx。"""
    if sub_no:
        for s in clause.subitems:
            if s.sub_item_no == sub_no:
                return s.start_idx
    if clause.start_idx < 0:
        return None
    return clause.start_idx


def _delete_paragraphs(paras: list, indices: list[int]) -> None:
    """按 _p 元素从底层 XML 删除段落。indices 必须倒序调用避免下标漂移。"""
    body = paras[0]._element.getparent()
    for idx in sorted(set(indices), reverse=True):
        if 0 <= idx < len(paras):
            body.remove(paras[idx]._element)


def _clear_paragraphs(paras: list, start: int, end: int) -> None:
    """清空段落文本（保段落节点）；整条款删除兜底。"""
    for i in range(start, end + 1):
        if 0 <= i < len(paras):
            _replace_paragraph_text(paras[i], "")


def _split_insert_text(text: str) -> list[str]:
    """把 insert_* 的 new_text 按换行拆成多段；空段过滤掉。

    例如 "第十二条 数据安全与保密\\n12.1 乙方应...\\n12.2 任何..." →
    ["第十二条 数据安全与保密", "12.1 乙方应...", "12.2 任何..."]
    """
    if not text:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _insert_paragraph_before_idx(paras: list, before_idx: int, text: str) -> None:
    """在 before_idx 之前插入新段落（复制 before_idx 原段落样式）。

    是 `_insert_paragraph_after` 的反向版本：先克隆 before_idx 原段落，
    但所有修改（清空旧 run、按角色套样式、写新 run）与 after 版一致，
    然后用 `addprevious` 锚定到原段落之前。
    """
    from copy import deepcopy as _deepcopy

    if not paras:
        return
    if before_idx < 0:
        before_idx = 0
    if before_idx >= len(paras):
        # 越界：退化为追加到最后一段之后
        _insert_paragraph_after(paras, len(paras) - 1, text)
        return

    target = paras[before_idx]
    anchor_el = target._element

    new_p = _deepcopy(anchor_el)
    for r in new_p.findall(qn("w:r")):
        for t in r.findall(qn("w:t")):
            t.text = ""
        new_p.remove(r)
    # hyperlink / fldSimple 嵌套的 w:t：用递归 iter 清空（qn 不支持复合路径）
    for hl in new_p.findall(qn("w:hyperlink")):
        for t in hl.iter(qn("w:t")):
            t.text = ""
    for fs in new_p.findall(qn("w:fldSimple")):
        for t in fs.iter(qn("w:t")):
            t.text = ""

    stripped = (text or "").lstrip()
    if _SUBITEM_RE.match(stripped):
        ea_font = _HEADING_FONT_NAME
        run_size = _BODY_FONT_SIZE
        run_bold = False
        _remove_first_line_indent_from(new_p)
        pPr = new_p.find(qn("w:pPr"))
        if pPr is not None:
            jc = pPr.find(qn("w:jc"))
            if jc is None:
                jc = pPr.makeelement(qn("w:jc"), {})
                pPr.append(jc)
            jc.set(qn("w:val"), "left")
    elif re.match(r"^[\s　]*第[一二三四五六七八九十百零〇\d]+条", stripped):
        ea_font = _HEADING_FONT_NAME
        run_size = Pt(14)
        run_bold = True
        _remove_first_line_indent_from(new_p)
        pPr = new_p.find(qn("w:pPr"))
        if pPr is not None:
            jc = pPr.find(qn("w:jc"))
            if jc is None:
                jc = pPr.makeelement(qn("w:jc"), {})
                pPr.append(jc)
            jc.set(qn("w:val"), "left")
    else:
        ea_font = _BODY_FONT_NAME
        run_size = _BODY_FONT_SIZE
        run_bold = False

    run = new_p.makeelement(qn("w:r"), {})
    rpr = run.makeelement(qn("w:rPr"), {})
    rfonts = rpr.makeelement(
        qn("w:rFonts"),
        {
            qn("w:ascii"): "Times New Roman",
            qn("w:hAnsi"): "Times New Roman",
            qn("w:eastAsia"): ea_font,
        },
    )
    rpr.append(rfonts)
    if run_bold:
        rpr.append(rpr.makeelement(qn("w:b"), {}))
    if run_size is not None and run_size != _BODY_FONT_SIZE:
        rpr.append(rpr.makeelement(qn("w:sz"), {qn("w:val"): str(int(run_size.pt * 2))}))
    run.append(rpr)
    t_el = run.makeelement(qn("w:t"), {})
    t_el.text = text or ""
    t_el.set(qn("xml:space"), "preserve")
    run.append(t_el)
    new_p.append(run)

    anchor_el.addprevious(new_p)


def _insert_paragraph_after(paras: list, after_idx: int, text: str) -> None:
    """在 after_idx 之后插入新段落，复制其后一个原段落样式（一般继承 anchor 段落）。

    新增样式规则（与前端 .docx-prose / 起草导出路径严格对齐）：
    - 段落角色 = 子项 X.Y（文本以 X.Y 开头）→ 黑体 + 12pt 顶格左对齐，无首行缩进；
    - 段落角色 = 条款标题 第X条（文本以「第X条」开头）→ 黑体 + 14pt 顶格左对齐，无首行缩进；
    - 其他 → 正文样式（仿宋 + 12pt + 首行缩进 2 字符 + 1.5 倍行距）。

    实现：deepcopy 锚点 _element（继承 pPr：行距/对齐/缩进），
    清空所有 w:r/w:hyperlink/w:fldSimple 内的 w:t（含原有残留），
    按新文本角色写入 run，run 显式带 rPr + rFonts（新字体为黑体或仿宋）。
    """
    from copy import deepcopy as _deepcopy

    # 决定目标段落（用于 insert_after 取 after_idx 之后的下一段作为 anchor_el）
    if after_idx < 0:
        target = paras[0]
    elif after_idx >= len(paras) - 1:
        target = paras[after_idx]  # 追加到末尾：用最后一段作 anchor_el
    else:
        target = paras[after_idx + 1]
    anchor_el = target._element

    new_p = _deepcopy(anchor_el)
    # 清空所有原有的 run/hyperlink/fldSimple 内的 w:t（避免 deepcopy 把旧内容带过去）
    for r in new_p.findall(qn("w:r")):
        for t in r.findall(qn("w:t")):
            t.text = ""
        # 旧 run 完全清空后 remove 掉（避免在最后 run 之前累积残留 w:r）
        new_p.remove(r)
    # hyperlink / fldSimple 嵌套的 w:t：用递归 iter 清空（qn 不支持复合路径）
    for hl in new_p.findall(qn("w:hyperlink")):
        for t in hl.iter(qn("w:t")):
            t.text = ""
    for fs in new_p.findall(qn("w:fldSimple")):
        for t in fs.iter(qn("w:t")):
            t.text = ""

    # 按新文本角色决定 run 样式
    stripped = (text or "").lstrip()
    if _SUBITEM_RE.match(stripped):  # X.Y 子项：黑体 + 12pt + 无首行缩进
        ea_font = _HEADING_FONT_NAME
        run_size = _BODY_FONT_SIZE
        run_bold = False
        _remove_first_line_indent_from(new_p)
        # 左对齐、顶格
        pPr = new_p.find(qn("w:pPr"))
        if pPr is not None:
            jc = pPr.find(qn("w:jc"))
            if jc is None:
                jc = pPr.makeelement(qn("w:jc"), {})
                pPr.append(jc)
            jc.set(qn("w:val"), "left")
    elif re.match(r"^[\s　]*第[一二三四五六七八九十百零〇\d]+条", stripped):
        # 第X条：黑体 + 14pt + 无首行缩进 + 顶格左对齐
        ea_font = _HEADING_FONT_NAME
        run_size = Pt(14)
        run_bold = True
        _remove_first_line_indent_from(new_p)
        pPr = new_p.find(qn("w:pPr"))
        if pPr is not None:
            jc = pPr.find(qn("w:jc"))
            if jc is None:
                jc = pPr.makeelement(qn("w:jc"), {})
                pPr.append(jc)
            jc.set(qn("w:val"), "left")
    else:
        # 普通正文：仿宋 + 12pt + 首行缩进 2 字符 + 1.5 倍行距
        ea_font = _BODY_FONT_NAME
        run_size = _BODY_FONT_SIZE
        run_bold = False

    # 写新 run：rPr 内显式 rFonts（西文 Times New Roman + 中文 ea_font）
    run = new_p.makeelement(qn("w:r"), {})
    rpr = run.makeelement(qn("w:rPr"), {})
    rfonts = rpr.makeelement(
        qn("w:rFonts"),
        {
            qn("w:ascii"): "Times New Roman",
            qn("w:hAnsi"): "Times New Roman",
            qn("w:eastAsia"): ea_font,
        },
    )
    rpr.append(rfonts)
    if run_bold:
        rpr.append(rpr.makeelement(qn("w:b"), {}))
    if run_size is not None and run_size != _BODY_FONT_SIZE:
        # 半磅为单位
        rpr.append(rpr.makeelement(qn("w:sz"), {qn("w:val"): str(int(run_size.pt * 2))}))
    run.append(rpr)
    t_el = run.makeelement(qn("w:t"), {})
    t_el.text = text or ""
    t_el.set(qn("xml:space"), "preserve")
    run.append(t_el)
    new_p.append(run)

    # 插入位置：after_idx 之后
    if after_idx >= len(paras) - 1:
        anchor_el.addnext(new_p)
    else:
        anchor_el.addprevious(new_p)


def _remove_first_line_indent_from(p_el) -> None:
    """去掉段落的 w:ind / w:firstLineChars / w:firstLine（无首行缩进）"""
    pPr = p_el.find(qn("w:pPr"))
    if pPr is None:
        return
    ind = pPr.find(qn("w:ind"))
    if ind is not None:
        pPr.remove(ind)


def _replace_clause_span(doc, session: ReviewSession) -> None:
    """把决策后的精确编辑指令写回 docx 原件（按 EditAction 排序，倒序应用）。

    取代旧的"按 Jaccard 兜底替换整段"实现：
    - replace 命中子项编号时按段落下标精确替换；
    - insert_* 在锚点段落后/前插入；
    - delete 删除目标段落（命中子项时精确，命中整条款时清空区间）；
    sort_key 已按文档绝对位置升序，应用层倒序避免下标漂移。
    """
    clause_map = {c.clause_id: c for c in session.clauses}
    actions = _build_edit_plan(session)
    for action in reversed(actions):
        _apply_action_to_doc(doc, action, clause_map)


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
    actions = _build_edit_plan(session)
    # 每个 EditAction 仅归属一个 bucket：
    # - insert_*：归到 anchor_clause_id 桶（效果就是"在 anchor 处插入"）
    # - replace / delete：归到 target_clause_id 桶
    # 这样跨条款 insert 不会出现两次。
    by_clause: dict[str, list[EditAction]] = {}
    for a in actions:
        bucket = a.anchor_clause_id if a.operation in ("insert_after", "insert_before") else a.target_clause_id
        if not bucket:
            continue
        by_clause.setdefault(bucket, []).append(a)
    for actions_in_c in by_clause.values():
        actions_in_c.sort(key=lambda a: a.sort_key, reverse=True)  # 倒序应用

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

    # 条款：基于 c.text 拆分多行，并按 EditAction 倒序应用 replace / delete / insert
    for c in session.clauses:
        clause_actions = by_clause.get(c.clause_id, [])
        lines = c.text.splitlines()
        out_lines: list[str] = list(lines)
        anchors = _build_subitem_line_index(out_lines)
        for act in clause_actions:
            if act.operation == "delete" and act.target_sub_item_no:
                idx = anchors.get(act.target_sub_item_no)
                if idx is not None and 0 <= idx < len(out_lines):
                    out_lines.pop(idx)
                    anchors = _build_subitem_line_index(out_lines)
                continue
            if act.operation == "replace":
                if act.target_sub_item_no and act.target_sub_item_no in anchors:
                    idx = anchors[act.target_sub_item_no]
                else:
                    idx = 0  # 整条款级替换：仅替换首段
                replacement_lines = [ln.strip() for ln in act.new_text.splitlines() if ln.strip()]
                if not replacement_lines:
                    continue
                out_lines[idx:idx + 1] = replacement_lines
                anchors = _build_subitem_line_index(out_lines)
                continue
            if act.operation == "insert_after":
                idx = anchors.get(act.anchor_sub_item_no)
                insert_at = (idx + 1) if idx is not None else len(out_lines)
                insert_lines = [ln.strip() for ln in act.new_text.splitlines() if ln.strip()]
                out_lines[insert_at:insert_at] = insert_lines
                anchors = _build_subitem_line_index(out_lines)
                continue
            if act.operation == "insert_before":
                idx = anchors.get(act.anchor_sub_item_no)
                insert_at = idx if idx is not None else 0
                insert_lines = [ln.strip() for ln in act.new_text.splitlines() if ln.strip()]
                out_lines[insert_at:insert_at] = insert_lines
                anchors = _build_subitem_line_index(out_lines)
                continue

        for line in out_lines:
            if not line.strip():
                continue
            p = doc.add_paragraph()
            run = p.add_run(line)
            _set_east_asia(run)

    # tail
    for line in session.tail_lines:
        p = doc.add_paragraph()
        run = p.add_run(line)
        _set_east_asia(run)
    return doc


def _build_subitem_line_index(lines: list[str]) -> dict[str, int]:
    """返回 X.Y 子项编号 → 行号 索引（用于 PDF 重建路径下的 sub_item_no 锚点）。"""
    index: dict[str, int] = {}
    sub_re = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)?)[\s　:：、]")
    for i, ln in enumerate(lines):
        m = sub_re.match(ln)
        if m and m.group(1) not in index:
            index[m.group(1)] = i
    return index


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
# 匹配 h4 数字子项 `（1）（2）…`，允许全角数字
_H4_NUMBERED_RE = re.compile(r"^[\s　]*（[0-9０-９]+）")
# 匹配 h4 字母子项 `（a）（b）…`
_H4_LETTERED_RE = re.compile(r"^[\s　]*（[a-zA-Z]）")
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


def _is_h4_numbered(text: str) -> bool:
    return bool(_H4_NUMBERED_RE.match(text))


def _is_h4_lettered(text: str) -> bool:
    return bool(_H4_LETTERED_RE.match(text))


def _classify_line(text: str) -> str | None:
    """分类一行文本：'h2' / 'h3' / 'h4' / 'p' / None。None 表示无特殊处理（仍作 p）。"""
    if _is_clause_title_line(text):
        return "h2"
    if _is_subitem_line(text):
        return "h3"
    if _is_h4_numbered(text) or _is_h4_lettered(text):
        return "h4"
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
            if kind in ("h3", "h4"):
                # <p><strong>X.Y ...</strong>...</p> → <h3>X.Y ...</h3>
                strong_texts = _collect_strong_texts(p)
                h = _new_heading_from_text_with_partial_bold(int(kind[1]), cleaned, strong_texts)
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
            elif tag_name in ("h2", "h3", "h4"):
                node = _new_heading_from_text(int(tag_name[1]), content)  # type: ignore[arg-type]
            else:
                # 兜底：当作纯文本段落
                node = _new_paragraph_from_text(str(content), style=p.get("style"))
            anchor.insert_after(node)
            anchor = node
        p.decompose()

    # 后处理：父 h3 下的子 h3 若编号与父冲突（6.1 / 6.1 → 6.1.1 / 6.1.2），自动归一化。
    _normalize_conflicting_numbers(body)

    return "".join(str(c) for c in body.children)


# 匹配 h3 文本开头的子项编号：1.1 / 1.2.3 / 10.4.5 等
_H3_NUMBER_RE = re.compile(r"^[\s　]*(\d+(?:\.\d+)+)[\s　]+")


def _normalize_conflicting_numbers(body) -> None:
    """把父 h3 下与父编号冲突的子 h3 自动归一化。

    示例（错误 → 正确）：
        <h3>6.1 甲方权利与义务</h3>
        <h3>6.1 权利</h3>     →  <h3>6.1.1 权利</h3>
        <h3>6.2 义务</h3>     →  <h3>6.1.2 义务</h3>

    规则：
    - 维护当前父编号前缀（如 6.1）。每当新 h3 的编号段在父前缀之后仍存在「同号」
      或「重号」情况（首段相同 / 出现在已用过的同级），都视为冲突。
    - 父编号用一段标识（``\\d+(?:\\.\\d+)+``），子编号必须以父编号为前缀且至少多一段。
    - 子编号在父作用域下按出现顺序递增，不假设 LLM 给的序号一定连续。
    - 没有冲突或不在父作用域内的 h3 保持原样。
    """
    parent_prefix: str | None = None
    child_counter = 0

    for h in list(body.find_all("h3", recursive=False)):
        full_text = h.get_text()
        m = _H3_NUMBER_RE.match(full_text)
        if not m:
            # 没有 X.Y 编号的 h3：清空父作用域，让后续 h3 重新建立父级
            parent_prefix = None
            child_counter = 0
            continue

        number = m.group(1)  # 例如 "6.1" 或 "6.1.1"
        rest = full_text[m.end():]

        if parent_prefix is None:
            # 第一次进入（或父作用域已重置）：若是 X.Y（恰好两段），作父；否则按父处理（清空状态）
            segments = number.split(".")
            if len(segments) == 2:
                parent_prefix = number
                child_counter = 0
            else:
                # 已经是 X.Y.Z，没有可作为父的两段号：清状态，下一个 h3 再尝试
                parent_prefix = None
                child_counter = 0
            continue

        # 已有父作用域：判断是否冲突
        if number == parent_prefix:
            # 同号冲突：6.1 重复出现 → 升级为下一级子项
            child_counter += 1
            new_number = f"{parent_prefix}.{child_counter}"
            _rewrite_h3_number(h, new_number, rest)
            continue
        if number.startswith(parent_prefix + "."):
            # 已经是 X.Y.Z（合理嵌套）：保留原样，但更新计数器
            tail = number[len(parent_prefix) + 1:]
            try:
                last = int(tail.split(".")[-1])
                child_counter = max(child_counter, last)
            except ValueError:
                pass
            continue
        # 与父无关：例如在 6.1 父作用域内突然出现 7.x → 重置父作用域
        segments = number.split(".")
        if len(segments) == 2:
            parent_prefix = number
            child_counter = 0
        else:
            parent_prefix = None
            child_counter = 0


def _rewrite_h3_number(h, new_number: str, rest: str) -> None:
    """用 new_number 替换 h3 文本开头的 old_number，保留原 strong 加粗范围。"""
    new_text = f"{new_number} {rest}".strip()
    if h.find(["strong", "b"]) is not None:
        # 重建 h3，把 strong 子串范围搬到新文本
        bold_substrings = _collect_strong_texts(h)
        h.clear()
        rebuilt = _new_heading_from_text_with_partial_bold(3, new_text, bold_substrings)
        for child in list(rebuilt.children):
            h.append(child)
    else:
        h.clear()
        h.string = new_text


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


def _add_paragraph_from_element(doc, p_elem, *, is_blockquote: bool = False) -> None:
    """<p> 节点映射为 docx 段落：保留对齐、首行缩进、行间距；行内样式递归处理

    缩进规则（与前端 .docx-prose 严格对齐）：
    - 居中 / blockquote：无首行缩进；
    - 普通 <p>：首行缩进 2 字符；
    - 紧跟 h3 的 <p>：继承 h3 的左缩进 + 取消首行缩进（前端 .docx-prose h3 + p）。
    """
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.line_spacing = _LINE_SPACING
    pf.space_after = Pt(8)  # 对齐前端 p { margin: 0 0 8px }

    # 直接传入 <blockquote> 节点时（罕见兜底），先用 _iter_block_elements 拆出内部 p
    # 这里更常见的是来自 _iter_block_elements 的 ("block_quote", <p>) 元组。
    if (p_elem.name or "").lower() == "blockquote":
        is_blockquote = True

    align = _parse_text_align(p_elem.get("style"))
    p.alignment = align

    # 紧跟 h3/h4 的 <p>：取消首行缩进，与标题一起顶格显示
    prev_sibling = p_elem.find_previous_sibling()
    follows_heading = (
        prev_sibling is not None
        and getattr(prev_sibling, "name", None)
        and prev_sibling.name.lower() in ("h3", "h4")
    )
    if follows_heading and not is_blockquote and align != WD_ALIGN_PARAGRAPH.CENTER:
        pf.left_indent = Cm(0)
        pf.first_line_indent = Cm(0)
        # 行内 run 仍走通用样式（仿宋 + 12pt）
        _add_html_runs(p, p_elem, size=_BODY_FONT_SIZE, east_asia=_BODY_FONT_NAME)
        return

    # 首行缩进 2 字符：与 _apply_body_format 一致，同时写 firstLineChars + firstLine
    # 居中段落不缩进（前端 h1 / 居中 p 不缩进）；
    # blockquote 也不缩进——前端 RichEditor 已对 blockquote 取消首行缩进，
    # 这里保持一致（合同抬头 / 鉴于是引言 / 签署栏等被规范化层转成的引用块不缩进）。
    if align != WD_ALIGN_PARAGRAPH.CENTER and not is_blockquote:
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
    H3 的层级缩进与父 H3 嵌套：H3 自身一级左缩进；若父级也是 H3，再叠加一级。
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
    else:  # h3 / h4：子项标题，顶格左对齐
        size = _BODY_FONT_SIZE
        east_asia = _HEADING_FONT_NAME
        align = WD_ALIGN_PARAGRAPH.LEFT
        pf.space_before = Pt(8 if level == 3 else 6)
        pf.space_after = Pt(6)
        pf.left_indent = Cm(0)
        pf.first_line_indent = Cm(0)  # 顶格对齐，首行不再额外缩

    p.alignment = align
    if level <= 2:
        # 一二级标题无首行缩进（前端 h1/h2 { text-indent: 0 }）
        _remove_first_line_indent(p)

    # h3/h4 内的 <strong> 子节点需要在导出 docx 里只让标题部分加粗，
    # 其余字符不沿用整段加粗样式（默认 heading 整段 bold）。
    if level >= 3:
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
    """遍历 root 的直接子节点中的块级元素（h1/h2/h3/p/ul/ol/table）

    `<blockquote>` 内嵌的 `<p>` 也按独立段落产出（让签字/盖章等行各自成段），
    并用 `block_quote` 元数据标记，让 `_add_paragraph_from_element` 抑制首行缩进。
    """
    for child in root.children:
        if getattr(child, "name", None) is None:
            continue
        tag = child.name.lower()
        if tag in ("h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "blockquote", "div"):
            if tag == "div":
                yield from _iter_block_elements(child)
            elif tag == "blockquote":
                # 拆出 blockquote 内层所有 <p> 子节点，按独立段落产出
                inner_paras = [
                    c for c in child.children
                    if getattr(c, "name", None) and c.name.lower() == "p"
                ]
                if not inner_paras:
                    # blockquote 内没有 <p>：整个节点当作正文段落（罕见兜底）
                    yield ("block_quote", child)
                    continue
                for inner_p in inner_paras:
                    yield ("block_quote", inner_p)
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
        # _iter_block_elements 对 blockquote 拆出的内部 <p> 会用元组 ("block_quote", <p>) 返回
        is_blockquote = False
        if isinstance(elem, tuple) and len(elem) == 2 and elem[0] == "block_quote":
            is_blockquote = True
            elem = elem[1]
        tag = elem.name.lower()
        if tag == "h1":
            _add_heading_from_element(doc, elem, 1)
        elif tag in ("h2", "h3", "h4"):
            _add_heading_from_element(doc, elem, int(tag[1]))
        elif tag == "p":
            _add_paragraph_from_element(doc, elem, is_blockquote=is_blockquote)
        elif tag in ("ul", "ol"):
            _add_list_from_element(doc, elem)
        elif tag == "table":
            _add_table_from_element(doc, elem)
        elif tag == "blockquote":
            # blockquote 内没 <p> 的兜底分支
            _add_paragraph_from_element(doc, elem, is_blockquote=True)

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
        f"审查结果：共 {len(session.risks)} 项风险",
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
