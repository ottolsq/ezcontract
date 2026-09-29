"""Track Changes 导出：skill OOXML DOM + 修订痕迹 + 批注（fixPlan.md）

设计（fixPlan.md §二/§三）：
- 解包 session.upload_bytes 到临时目录（原样解包，不做 pretty-print）；
- 桥接 import skill 的 ContractReviewer / pack_document；
- 锚点不做文本搜索：docx_parser 用 python-docx `doc.paragraphs`
  （= w:body 直接子级 w:p），这里取同样的直接子级列表做下标映射；
- replace 走 difflib 最小 diff（equal 段 run 原样保留）；
- 新段落 = deepcopy 角色模板段 w:pPr + 新 run（deepcopy 模板 w:rPr），
  绝不克隆整个 w:p（避免重复 paraId / bookmark / commentRange）；
- 每条 accepted/modified 动作挂一条批注（换行替换为「；」）；
- 全程 try/except，任何失败由上层 export_final_docx 降级到就地替换。

Python 3.10 语法（venv 3.10.12）。
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import settings
from app.schemas.review import Clause, ReviewSession
from app.services.docx_export import EditAction, _build_edit_plan, _split_insert_text

logger = logging.getLogger(__name__)

# ---------- skill 桥接（submodule 不能作为包名 import，目录名带点） ----------

_SKILL_SCRIPTS_DIR = settings.SKILL_DIR / "scripts"


def _bridge_import():
    """把 skill 的 scripts/ 目录挂进 sys.path 后导入核心类。

    与 skill 自身 apply_review_plan.py 的做法一致
    （sys.path.insert(skill_root) + from scripts.docx.reviewer import ...）。
    """
    import sys

    for p in (str(_SKILL_SCRIPTS_DIR), str(settings.SKILL_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from scripts.docx.document import Document
    from scripts.docx.pack import pack_document
    from scripts.docx.reviewer import ContractReviewer

    return Document, ContractReviewer, pack_document


# ---------- 字体兜底常量（与 docx_export 风格一致） ----------

_BODY_FONT_NAME = "仿宋"
_HEADING_FONT_NAME = "黑体"
_BODY_FONT_SIZE_HALF = "24"  # 12pt → OOXML half-point


def _ensure_rfonts(rpr_el, ea_font: str = _BODY_FONT_NAME, *, bold: bool = False, sz_half: str | None = None) -> None:
    """rPr 节点若无 w:rFonts 或无 eastAsia 声明，按 ea_font 兜底补充。

    只补充缺失属性，已存在的 ascii/hAnsi/eastAsia 不动 → 与原文档样式兼容。
    `bold=True` 时若 rPr 缺少 w:b 则补加粗；`sz_half` 若指定则补 w:sz。
    """
    if rpr_el is None:
        return
    # minidom 没有 getElementsByTagNameNS；用本地 tagName 直接匹配
    rfonts = None
    has_b = False
    has_sz = False
    for child in rpr_el.childNodes:
        if child.nodeType != child.ELEMENT_NODE:
            continue
        if child.tagName == "w:rFonts":
            rfonts = child
        elif child.tagName == "w:b":
            has_b = True
        elif child.tagName == "w:sz":
            has_sz = True
    if rfonts is None:
        rfonts = rpr_el.ownerDocument.createElement("w:rFonts")
        # 插到 rPr 最前（OOXML 规范 w:rFonts 必须是 rPr 第一个子元素）
        if rpr_el.firstChild is not None:
            rpr_el.insertBefore(rfonts, rpr_el.firstChild)
        else:
            rpr_el.appendChild(rfonts)
    if not rfonts.getAttribute("w:ascii"):
        rfonts.setAttribute("w:ascii", "Times New Roman")
    if not rfonts.getAttribute("w:hAnsi"):
        rfonts.setAttribute("w:hAnsi", "Times New Roman")
    if not rfonts.getAttribute("w:eastAsia"):
        rfonts.setAttribute("w:eastAsia", ea_font)
    # 加粗：只在模板未给出 b 声明时按角色补，避免覆盖用户自定义的取消加粗
    if bold and not has_b:
        b_el = rpr_el.ownerDocument.createElement("w:b")
        rpr_el.appendChild(b_el)
        bcs_el = rpr_el.ownerDocument.createElement("w:bCs")
        rpr_el.appendChild(bcs_el)
    # 字号（half-point；缺时按角色补，避免 Word 默认）
    if sz_half and not has_sz:
        sz_el = rpr_el.ownerDocument.createElement("w:sz")
        sz_el.setAttribute("w:val", sz_half)
        rpr_el.appendChild(sz_el)
        szcs_el = rpr_el.ownerDocument.createElement("w:szCs")
        szcs_el.setAttribute("w:val", sz_half)
        rpr_el.appendChild(szcs_el)


def _role_font(text: str) -> str:
    """按段落角色决定中文字体：clause_title/subitem → 黑体；body → 仿宋。"""
    role = _role_of(text or "")
    return _HEADING_FONT_NAME if role in ("clause_title", "subitem") else _BODY_FONT_NAME


def _role_rpr_props(text: str) -> tuple[bool, str]:
    """按段落角色返回 (bold, sz_half)：clause_title → 加粗 28(14pt)；subitem → 加粗 24(12pt)；body → 普通 24(12pt)。"""
    role = _role_of(text or "")
    if role == "clause_title":
        return True, "28"
    if role == "subitem":
        return True, "24"
    return False, "24"


# ---------- 角色识别（与 docx_export 现有规则一致） ----------

_CLAUSE_TITLE_LINE_RE = re.compile(r"^[\s　]*第[一二三四五六七八九十百零〇\d]+条")
# 支持 X.Y / X.Y.Z / X.Y(Z) / X.Y（Z） 形式（含括号层级）
_SUBITEM_LINE_RE = re.compile(
    r"^\s*\d+\.\d+(?:\.\d+)?(?:\([0-9０-９]+\)|（[0-9０-９]+）)?[\s　:：、]"
)


def _role_of(text: str) -> str:
    """段落角色：clause_title（第X条）/ subitem（X.Y）/ body。"""
    stripped = (text or "").lstrip()
    if _CLAUSE_TITLE_LINE_RE.match(stripped):
        return "clause_title"
    if _SUBITEM_LINE_RE.match(stripped):
        return "subitem"
    return "body"


# ---------- XML 构造工具 ----------


def _node_text(p_el) -> str:
    """minidom 节点 → 纯文本：递归 w:t/w:br，遇 w:br 输出 \\n。

    实际 OOXML 里段落文本通常嵌在 p > pPr > r > t；只扫直接子级会丢掉所有内容。
    递归实现同时在 w:br 位置输出 \\n，让 difflib 与 new_text 的换行边界对齐。
    """
    parts: list[str] = []
    for child in p_el.childNodes:
        if child.nodeType == child.TEXT_NODE:
            if child.data:
                parts.append(child.data)
        elif child.nodeType == child.ELEMENT_NODE:
            name = child.tagName
            if name == "w:t":
                for sub in child.childNodes:
                    if sub.nodeType == sub.TEXT_NODE and sub.data:
                        parts.append(sub.data)
            elif name == "w:br":
                parts.append("\n")
            else:
                parts.append(_node_text(child))
    return "".join(parts)


def _first_text_run(p_el):
    """w:p 内第一个有文本的 w:r（deepcopy 其 w:rPr 作为新 run 样式模板）。"""
    for r in p_el.getElementsByTagName("w:r"):
        for t in r.getElementsByTagName("w:t"):
            if _node_text(r):
                return r
    return None


def _escape(text: str) -> str:
    import html

    return html.escape(text, quote=False)


def _pick_template_paragraph(body_ps: list, action: EditAction, session: ReviewSession, clause_map: dict):
    """按新文本角色选择样式模板段（fixPlan.md §三.2）。

    - 第X条 行 → 同文档已有条款标题段（找锚点之后的下一个条款标题段，找不到往前找）；
    - X.Y 子项行 → 锚点段（子项或正文都行，取锚点更贴近语境）；
    - 正文 → 锚点段。
    完全无模板时返回 None（调用方回落到现有字体常量兜底）。
    """
    role = _role_of(action.new_text.splitlines()[0] if action.new_text else "")
    if role != "clause_title":
        # 子项 / 正文：直接用锚点段
        return None  # 由调用方用锚点段
    # 条款标题：扫全文档找已有的 第X条 标题段
    for p in body_ps:
        if _CLAUSE_TITLE_LINE_RE.match((_node_text(p) or "").lstrip()):
            return p
    return None


def _build_new_paragraph_xml(template_p, text: str, reviewer) -> str:
    """构造新段落 XML：deepcopy 模板 w:pPr + 新 run（deepcopy 模板 run w:rPr）。

    - 只拷贝结构性 pPr（缩进/行距/对齐/编号/样式引用），run 全部新建，
      不克隆整个 w:p（避免重复 w14:paraId / bookmark / commentRange）；
    - 模板 run 的 w:rPr 原样继承后，若缺 w:rFonts 或 w:eastAsia，则按角色补字体
      （clause_title/subitem → 黑体；body → 仿宋），避免 Word 用默认字体渲染；
    - 模板 run 的 w:rPr 缺 w:b/w:sz 时按角色补加粗/字号，避免与上下文不一致；
    - 无模板或模板无 rPr 时按角色直接拼一个 rPr 输出（兜底）。
    """
    role = _role_of(text or "")
    role_bold, role_sz = _role_rpr_props(text or "")
    ea_font = _HEADING_FONT_NAME if role in ("clause_title", "subitem") else _BODY_FONT_NAME

    ppr_xml = ""
    rpr_xml = ""
    if template_p is not None:
        ppr = None
        for child in template_p.childNodes:
            if child.nodeType == child.ELEMENT_NODE and child.nodeName == "w:pPr":
                ppr = child
                break
        if ppr is not None:
            cloned = deepcopy(ppr)
            # 清掉模板 pPr 里可能带的结构性引用（批注标记/修订标记），保留排版属性
            for marker in list(cloned.getElementsByTagName("w:rPr")):
                for tag in ("w:ins", "w:del"):
                    for m in list(marker.getElementsByTagName(tag)):
                        marker.removeChild(m)
            ppr_xml = cloned.toxml()
        tpl_run = _first_text_run(template_p)
        if tpl_run is not None:
            for child in tpl_run.childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.nodeName == "w:rPr":
                    cloned_rpr = deepcopy(child)
                    for tag in ("w:ins", "w:del"):
                        for m in list(cloned_rpr.getElementsByTagName(tag)):
                            cloned_rpr.removeChild(m)
                    _ensure_rfonts(cloned_rpr, ea_font, bold=role_bold, sz_half=role_sz)
                    rpr_xml = cloned_rpr.toxml()
                    break
    if not rpr_xml:
        # 无模板或模板无 rPr：按角色拼一个兜底 rPr（中西文字体 + 12pt）
        rpr_xml = (
            f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
            f'w:hAnsi="Times New Roman" w:eastAsia="{ea_font}"/>'
            f'<w:sz w:val="{role_sz}"/></w:rPr>'
        )
        if role_bold:
            rpr_xml = (
                f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
                f'w:hAnsi="Times New Roman" w:eastAsia="{ea_font}"/>'
                f'<w:b/><w:bCs/><w:sz w:val="{role_sz}"/><w:szCs w:val="{role_sz}"/></w:rPr>'
            )
    return f"<w:p>{ppr_xml}<w:r>{rpr_xml}<w:t>{_escape(text)}</w:t></w:r></w:p>"


# ---------- 批注文案 ----------


def _comment_text_for(action: EditAction, session: ReviewSession) -> str:
    """批注文案已废弃 —— 用户要求直接在文档里改，不再挂评论气泡。

    保留空字符串签名以兼容调用方；若以后恢复批注，可在此处重新拼文案。
    """
    return ""


# ---------- 三类操作 ----------


def _run_with_br(rpr_xml: str, lines: list[str], *, deleted: bool) -> str:
    """把多行文本包成单个 w:r（行间用 <w:br/>）。

    - deleted=True 时文本用 <w:delText>（OOXML 要求 w:del 内必须用 delText）；
    - 末段空文本段直接跳过；
    - 转义逐段做，避免 \\n 被一并 escape。
    """
    text_tag = "w:delText" if deleted else "w:t"
    parts: list[str] = []
    for i, line in enumerate(lines):
        if not line:
            # 空行也要占位：用 <w:br/> 维持行数，避免相邻文本粘连
            if i + 1 < len(lines):
                parts.append(f"<w:r>{rpr_xml}<w:br/></w:r>")
            continue
        if i > 0:
            parts.append(f"<w:r>{rpr_xml}<w:br/></w:r>")
        # 行首/末有空白时必须保留（OOXML 默认 trim）
        preserve = ' xml:space="preserve"' if line[:1].isspace() or line[-1:].isspace() else ""
        parts.append(f"<w:r>{rpr_xml}<{text_tag}{preserve}>{_escape(line)}</{text_tag}></w:r>")
    # 末尾若所有 lines 都为空（不该出现但兜底），输出一个空 w:r 满足 OOXML 结构
    return "".join(parts)


def _apply_replace(reviewer, action: EditAction, target_p, comment: str, clause_map: dict[str, Clause] | None = None) -> bool:
    """子项级/单段 replace：difflib 最小 diff，equal 段 run 原样保留。

    段落内若含 <w:br/>（多行子项排版），old_text/new_text 中的换行在
    `_node_text()` / difflib 中均以 \\n 表示；本函数按 \\n 拆分到多个 w:r
    行间用 <w:br/> 分隔，确保 Word 打开后行数/版式与原段落一致。

    空 body（equal 段空 + insert 段空）时仍要保留占位 w:r，否则 Word 把
    w:ins/w:del 视为空内容并可能导致 docx 校验失败。
    """
    doc_editor = reviewer.doc["word/document.xml"]
    old_text = _node_text(target_p)
    new_text = action.new_text
    # 自动补回原段落编号前缀：子项级用 clause_map 查 display_no（保留原文括号样式），
    # 整条款用 _SUBITEM_LINE_RE 从 old_text 抓 X.Y 基编号。
    display_prefix = ""
    if clause_map is not None:
        clause = clause_map.get(action.target_clause_id)
        if clause and action.target_sub_item_no:
            for s in clause.subitems:
                if s.sub_item_no == action.target_sub_item_no or s.internal_no == action.target_sub_item_no:
                    display_prefix = s.display_no
                    break
    if not display_prefix:
        m = _SUBITEM_LINE_RE.match(old_text or "")
        if m:
            display_prefix = m.group(0).rstrip()
    if display_prefix and not new_text.lstrip().startswith(display_prefix):
        new_text = f"{display_prefix}{new_text.lstrip()}"

    try:
        if _has_tracked_changes(target_p):
            return False
        # 同段多子项：仅替换 line_in_paragraph 指定的那一行（其余行原样保留）
        per_line_match = _resolve_line_in_paragraph(target_p, action, clause_map)
        if per_line_match is not None:
            # 整行替换语义：旧行整段被 w:del 包住、新行整段被 w:ins 包住，
            # 避免 difflib 字符级 diff 把"余额应退还乙方"切成两半。
            line_idx, _total_lines, old_lines = per_line_match
            pre_lines = old_lines[:line_idx]
            post_lines = old_lines[line_idx + 1 :]
            segments: list[tuple[str, str]] = []
            if pre_lines:
                segments.append(("equal", "\n".join(pre_lines) + "\n"))
            segments.append(("delete", old_lines[line_idx]))
            segments.append(("insert", new_text))
            if post_lines:
                segments.append(("equal", "\n".join(post_lines)))
        else:
            segments = reviewer._build_revision_segments(old_text, new_text)
        template_run = _first_text_run(target_p)
        ppr = _direct_child(target_p, "w:pPr")
        ppr_xml = ppr.toxml() if ppr is not None else ""
        # 兜底字体（按目标段落的角色：标题/子项 → 黑体，正文 → 仿宋）
        role_ea_font = _role_font(_node_text(target_p) or action.new_text)
        body_xml = []
        any_segment_emitted = False
        for kind, text in segments:
            # 按行拆分：每行独立判断角色（clause_title/subitem/body），
            # 这样新插入的子项编号、嵌套条目、标题、正文各自套用正确的字体/加粗/字号，
            # 不会因为第一行是子项编号就把整段正文也套用加粗黑体。
            lines = text.split("\n")
            base_rpr_xml = _run_rpr_xml(template_run)
            rpr_per_line: list[str] = []
            for line in lines:
                line_bold, line_sz = _role_rpr_props(line)
                line_ea_font = _HEADING_FONT_NAME if _role_of(line) in ("clause_title", "subitem") else _BODY_FONT_NAME
                if not base_rpr_xml:
                    # 无模板：按角色拼一个完整 rPr（含 w:rFonts / w:b / w:sz）
                    rpr_xml = (
                        f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
                        f'w:hAnsi="Times New Roman" w:eastAsia="{line_ea_font}"/>'
                        f'<w:sz w:val="{line_sz}"/></w:rPr>'
                    )
                    if line_bold:
                        rpr_xml = (
                            f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
                            f'w:hAnsi="Times New Roman" w:eastAsia="{line_ea_font}"/>'
                            f'<w:b/><w:bCs/><w:sz w:val="{line_sz}"/><w:szCs w:val="{line_sz}"/></w:rPr>'
                        )
                else:
                    # 模板已有 rPr：按角色覆盖 eastAsia、补缺失的 w:b / w:sz
                    rpr_xml = _apply_role_attrs(base_rpr_xml, line_ea_font, line_bold, line_sz)
                rpr_per_line.append(rpr_xml)
            run_xml = _run_with_br_per_line(rpr_per_line, lines, deleted=(kind == "delete"))
            if not run_xml:
                # 完全空段（如 equal 段被压平）仍要保留一个空 w:r 维持结构
                fallback_rpr = rpr_per_line[0] if rpr_per_line else (
                    f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
                    f'w:hAnsi="Times New Roman" w:eastAsia="{role_ea_font}"/>'
                    f'<w:sz w:val="{_BODY_FONT_SIZE_HALF}"/></w:rPr>'
                )
                run_xml = f"<w:r>{fallback_rpr}<w:t></w:t></w:r>"
            any_segment_emitted = any_segment_emitted or bool(run_xml)
            if kind == "equal":
                body_xml.append(run_xml)
            elif kind == "delete":
                # OOXML 规范：<w:del> 内文本必须用 <w:delText>，否则 Word 不视为删除内容
                body_xml.append(f"<w:del>{run_xml}</w:del>")
            elif kind == "insert":
                body_xml.append(f"<w:ins>{run_xml}</w:ins>")
        if not any_segment_emitted:
            # 极少见：所有段全被 difflib 压平为空，至少保留一个空 run 不让段落塌掉
            rpr_xml = _run_rpr_xml(template_run) or (
                f'<w:rPr><w:rFonts w:ascii="Times New Roman" '
                f'w:hAnsi="Times New Roman" w:eastAsia="{role_ea_font}"/>'
                f'<w:sz w:val="{_BODY_FONT_SIZE_HALF}"/></w:rPr>'
            )
            body_xml.append(f"<w:r>{rpr_xml}<w:t></w:t></w:r>")
        replacement = f"<w:p>{ppr_xml}{''.join(body_xml)}</w:p>"
        nodes = doc_editor.replace_node(target_p, replacement)
        anchor = _find_first_change_node(nodes)
        if comment and anchor is not None:
            reviewer.add_comment(anchor, comment)
        return True
    except ValueError as exc:
        logger.warning("track replace 单条失败（跳过）: %s", exc)
        return False


def _apply_role_attrs(rpr_xml: str, ea_font: str, bold: bool, sz_half: str) -> str:
    """给已有 rPr XML 按角色补/改 eastAsia、w:b、w:sz（字符串层面，避免 minidom 重建）"""
    # 1) 改/补 w:eastAsia
    import re as _re

    if "<w:rFonts" in rpr_xml:
        # 已存在 w:rFonts：仅替换/补 eastAsia 属性
        def _patch_rfonts(m: "_re.Match[str]") -> str:
            tag = m.group(0)
            if "w:eastAsia=" in tag:
                return _re.sub(r'w:eastAsia="[^"]*"', f'w:eastAsia="{ea_font}"', tag)
            # 在标签末尾插入 eastAsia
            return tag[:-1] + f' w:eastAsia="{ea_font}"' + tag[-1]

        rpr_xml = _re.sub(r"<w:rFonts[^/>]*/>", _patch_rfonts, rpr_xml)
    else:
        # 没有 w:rFonts：插入
        rfonts_xml = (
            f'<w:rFonts w:ascii="Times New Roman" '
            f'w:hAnsi="Times New Roman" w:eastAsia="{ea_font}"/>'
        )
        rpr_xml = rpr_xml.replace("<w:rPr>", f"<w:rPr>{rfonts_xml}", 1)
    # 2) 加粗：补 w:b / w:bCs（模板未给时）
    if bold:
        if "<w:b/>" not in rpr_xml and "<w:b " not in rpr_xml:
            rpr_xml = rpr_xml.replace("</w:rPr>", "<w:b/><w:bCs/></w:rPr>", 1)
    # 3) 字号：补 w:sz / w:szCs（half-point）
    if sz_half:
        if "<w:sz " not in rpr_xml:
            rpr_xml = rpr_xml.replace(
                "</w:rPr>", f'<w:sz w:val="{sz_half}"/></w:rPr>', 1
            )
        if "<w:szCs " not in rpr_xml:
            rpr_xml = rpr_xml.replace(
                "</w:rPr>", f'<w:szCs w:val="{sz_half}"/></w:rPr>', 1
            )
    return rpr_xml


def _run_with_br_per_line(rpr_per_line: list[str], lines: list[str], *, deleted: bool) -> str:
    """_run_with_br 的 per-line 版本：每行使用自己的 rPr（与 _role_rpr_props 对齐）。

    `deleted=True` 时用 <w:delText>（OOXML 要求 w:del 内的删除文本必须用 delText）；
    插入段（deleted=False）即便在 <w:ins> 里也用普通 <w:t> 即可，OOXML 标准支持。
    """
    text_tag = "w:delText" if deleted else "w:t"
    parts: list[str] = []
    for i, line in enumerate(lines):
        rpr_xml = rpr_per_line[i] if i < len(rpr_per_line) else (rpr_per_line[0] if rpr_per_line else "")
        if not line:
            if i + 1 < len(lines):
                parts.append(f"<w:r>{rpr_xml}<w:br/></w:r>")
            continue
        if i > 0:
            parts.append(f"<w:r>{rpr_xml}<w:br/></w:r>")
        preserve = ' xml:space="preserve"' if line[:1].isspace() or line[-1:].isspace() else ""
        parts.append(f"<w:r>{rpr_xml}<{text_tag}{preserve}>{_escape(line)}</{text_tag}></w:r>")
    return "".join(parts)


def _resolve_line_in_paragraph(target_p, action: EditAction, clause_map):
    """同段多子项：返回 (line_idx, total_lines, old_lines) 或 None。

    若 action.target_clause_id + target_sub_item_no 对应 SubItem 的 start_idx 命中 target_p，
    且 line_in_paragraph > 0 或 该段行数 > 1，则按行级 diff；否则返回 None（整段）。
    """
    if clause_map is None or not action.target_sub_item_no:
        return None
    clause = clause_map.get(action.target_clause_id)
    if not clause:
        return None
    target_idx = None
    target_lip = None
    for s in clause.subitems:
        if s.sub_item_no == action.target_sub_item_no or s.internal_no == action.target_sub_item_no:
            target_idx = s.start_idx
            target_lip = s.line_in_paragraph
            break
    if target_idx is None:
        return None
    # 段索引比对：target_p 在 body_ps 中的位置
    body_ps = _body_paragraphs(reviewer.doc["word/document.xml"]) if False else None
    # 简化：直接看段落 old_text 是否含 \n
    old_text = _node_text(target_p)
    if "\n" not in old_text:
        return None
    old_lines = old_text.split("\n")
    if target_lip >= len(old_lines):
        return None
    return target_lip, len(old_lines), old_lines


def _has_tracked_changes(p_el) -> bool:
    return bool(
        p_el.getElementsByTagName("w:ins") or p_el.getElementsByTagName("w:del")
    )


def _direct_child(node, tag_name):
    for child in node.childNodes:
        if child.nodeType == child.ELEMENT_NODE and child.nodeName == tag_name:
            return child
    return None


def _run_rpr_xml(run_node) -> str:
    """取 run 的 rPr XML 字符串；若缺字体声明则按 anchor_p 角色补字体。"""
    if run_node is None:
        return ""
    rpr = _direct_child(run_node, "w:rPr")
    if rpr is None:
        return ""
    return rpr.toxml()


def _find_first_change_node(nodes):
    """复刻 skill reviewer._find_first_change_node：BFS 找首个 w:ins/w:del。"""
    queue = list(nodes)
    while queue:
        node = queue.pop(0)
        name = getattr(node, "tagName", None)
        if name in {"w:ins", "w:del"}:
            return node
        for child in getattr(node, "childNodes", []):
            if getattr(child, "nodeType", None) == child.ELEMENT_NODE:
                queue.append(child)
    return nodes[0] if nodes else None


def _apply_delete(reviewer, action: EditAction, target_p, processed: set, comment: str) -> bool:
    """delete：目标段落 suggest_deletion；已处理段落跳过（防重标记）。"""
    if id(target_p) in processed:
        return True
    try:
        reviewer.suggest_deletion(target_p)
        processed.add(id(target_p))
        if comment:
            reviewer.add_comment(target_p, comment)
        return True
    except ValueError as exc:
        logger.warning("track delete 单条失败（跳过）: %s", exc)
        return False


def _apply_insert(
    reviewer,
    action: EditAction,
    anchor_p,
    body_ps: list,
    clause_map: dict,
    session: ReviewSession,
    comment: str,
    *,
    before: bool,
) -> bool:
    """insert_after / insert_before：多行拆段，每段按角色选模板，suggest_paragraph 包 w:ins。"""
    from scripts.docx.document import DocxXMLEditor

    doc_editor = reviewer.doc["word/document.xml"]
    lines = _split_insert_text(action.new_text)
    if not lines:
        return False

    # 一次性解析全部插入段落（正序构造，倒序/正序插入由 before 决定）
    title_template = _pick_template_paragraph(body_ps, action, session, clause_map)
    xmls = []
    for line in lines:
        template = title_template if _role_of(line) == "clause_title" else anchor_p
        xmls.append(_build_new_paragraph_xml(template, line, reviewer))

    try:
        inserted_first = None
        if before:
            # 正序逐段 insert_before：每段都插在锚点前 → 最终顺序正确
            for xml in xmls:
                wrapped = DocxXMLEditor.suggest_paragraph(xml)
                nodes = doc_editor.insert_before(anchor_p, wrapped)
                if inserted_first is None:
                    inserted_first = nodes[0] if nodes else None
        else:
            # 倒序逐段 insert_after：最后插的在前 → 最终顺序正确
            for xml in reversed(xmls):
                wrapped = DocxXMLEditor.suggest_paragraph(xml)
                nodes = doc_editor.insert_after(anchor_p, wrapped)
                inserted_first = nodes[0] if nodes else None
        if comment and inserted_first is not None:
            reviewer.add_comment(inserted_first, comment)
        return True
    except ValueError as exc:
        logger.warning("track insert 单条失败（跳过）: %s", exc)
        return False


# ---------- 主流程 ----------


def _body_paragraphs(doc_editor) -> list:
    """w:body 直接子级 w:p 列表 —— 与 python-docx doc.paragraphs 坐标系一致。"""
    body = doc_editor.dom.getElementsByTagName("w:body")[0]
    return [
        c
        for c in body.childNodes
        if c.nodeType == c.ELEMENT_NODE and c.nodeName == "w:p"
    ]


def _resolve_target(
    action: EditAction,
    clause_map: dict[str, Clause],
    body_ps: list,
):
    """EditAction → (目标/锚点段落下标, None) 或 (None, 错误消息)。

    下标越界时降级 find_text(contains=条款首行前12字)；再不行返回错误。
    """
    from app.services.docx_export import _resolve_target_idx

    if action.operation in ("replace", "delete"):
        clause = clause_map.get(action.target_clause_id)
        if not clause:
            return None, f"clause {action.target_clause_id} 不存在"
        idx = _resolve_target_idx(clause, action.target_sub_item_no)
        if idx is not None and 0 <= idx < len(body_ps):
            target_p = body_ps[idx]
            target_text = _node_text(target_p) or ""
            # 二次防御：若 idx 命中的是条款标题段（说明 sub_item_no 仍未定位成功），
            # 主动尝试段内扫描基编号（如 3.1(3) → 找 3.1 开头的 body 段）。
            if (
                action.target_sub_item_no
                and _is_clause_title(target_text)
                and idx == clause.start_idx
            ):
                from app.services.docx_export import _find_subitem_idx_by_text

                paras_text = [_node_text(p) or "" for p in body_ps]
                scanned = _find_subitem_idx_by_text(clause, action.target_sub_item, paras_text)
                if scanned is not None and scanned < len(body_ps):
                    idx = scanned
            # 三次防御：sub_item_no 为空时禁止替换标题段；但允许 sub_item_no 存在
            # 时落到 body 段（即使 idx 碰巧等于 start_idx 的语义下，若目标段就是
            # 该子项的"单段"实现，应让二次防御接管而非整体跳过）。
            # 进一步：即使 sub_item_no 为空，只要 clause 区间长度 > 1（说明有 body 段），
            # 也不应落到 start_idx 标题上 —— 应跳到 clause.start_idx+1（第一条 body）。
            if idx is not None:
                cur_text = _node_text(body_ps[idx]) or ""
                if (
                    not action.target_sub_item_no
                    and idx == clause.start_idx
                    and _is_clause_title(cur_text)
                    and clause.end_idx > clause.start_idx
                ):
                    # 整条款 replace：跳到首条 body 段（避免删除标题）
                    idx = clause.start_idx + 1
                    cur_text = _node_text(body_ps[idx]) or ""
                    # 极端情况：start_idx+1 仍是标题（罕见）→ 跳过
                    if _is_clause_title(cur_text):
                        return None, f"clause {clause.clause_id} body 段均为标题，跳过"
            return idx, None
        return _fallback_find(body_ps, clause, action)
    # insert_*
    clause = clause_map.get(action.anchor_clause_id or action.target_clause_id)
    if not clause:
        return None, f"anchor clause {action.anchor_clause_id} 不存在"
    idx = _resolve_target_idx(clause, action.anchor_sub_item_no)
    if idx is not None and 0 <= idx < len(body_ps):
        return idx, None
    return _fallback_find(body_ps, clause, action)


def _is_clause_title(text: str) -> bool:
    return bool(_CLAUSE_TITLE_LINE_RE.match((text or "").lstrip()))


def _fallback_find(body_ps: list, clause: Clause, action: EditAction):
    """下标越界兜底：用条款首行前 12 字在 body_ps 里找唯一包含段。"""
    first_line = (clause.text or "").strip().splitlines()[0] if clause.text else ""
    probe = first_line[:12].strip()
    if len(probe) < 4:
        return None, f"clause {clause.clause_id} 下标越界且文本探测失败"
    hits = [i for i, p in enumerate(body_ps) if probe in (_node_text(p) or "")]
    if len(hits) == 1:
        return hits[0], None
    return None, f"clause {clause.clause_id} 下标越界，文本探测命中 {len(hits)} 段"


def export_docx_with_track_changes(session: ReviewSession) -> io.BytesIO:
    """DOCX 上传路径：解包 → 应用 Track Changes + 批注 → 打包 → BytesIO。

    任何未预期异常向上抛，由 export_final_docx 捕获后降级到就地替换。
    """
    Document, ContractReviewer, pack_document = _bridge_import()

    with TemporaryDirectory(prefix="faheng_track_") as tmp:
        tmp_dir = Path(tmp)
        unpacked = tmp_dir / "unpacked"
        unpacked.mkdir()
        # 原样解包（不做 skill 的 pretty-print/ascii 转码，避免编码扰动）
        with zipfile.ZipFile(io.BytesIO(session.upload_bytes)) as zf:
            zf.extractall(unpacked)

        reviewer = ContractReviewer(
            unpacked, author="合同审查助手", initials="审"
        )
        doc_editor = reviewer.doc["word/document.xml"]
        body_ps = _body_paragraphs(doc_editor)
        clause_map = {c.clause_id: c for c in session.clauses}
        actions = _build_edit_plan(session)

        # 先一次性解析全部锚点（节点引用稳定），再倒序应用（与现路径一致）
        resolved: list[tuple[EditAction, int | None, str | None]] = []
        for action in actions:
            idx, err = _resolve_target(action, clause_map, body_ps)
            if err:
                logger.warning("track 导出跳过动作 %s: %s", action.operation, err)
            resolved.append((action, idx, err))

        processed_deleted: set[int] = set()
        for action, idx, err in reversed(resolved):
            if err or idx is None:
                continue
            comment = _comment_text_for(action, session)
            if action.operation == "replace":
                _apply_replace(reviewer, action, body_ps[idx], comment, clause_map)
            elif action.operation == "delete":
                _apply_delete(reviewer, action, body_ps[idx], processed_deleted, comment)
            else:
                _apply_insert(
                    reviewer,
                    action,
                    body_ps[idx],
                    body_ps,
                    clause_map,
                    session,
                    comment,
                    before=(action.operation == "insert_before"),
                )

        reviewer.save(validate=True)
        out_docx = tmp_dir / "out.docx"
        pack_document(unpacked, out_docx)

        # 冒烟校验：python-docx（Word 级解析器）能打开才返回
        from docx import Document as PyDocx

        buf = io.BytesIO(out_docx.read_bytes())
        PyDocx(buf)
        buf.seek(0)
        return buf
