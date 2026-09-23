"""起草服务：生成 / 修订 / 内容保存 / 导出"""
from __future__ import annotations

import io
import re
import uuid

from fastapi import HTTPException

from app.config import settings
from app.llm.client import LLMFormatError, chat_json, chat_text
from app.llm.prompts import build_draft_prompt, build_revise_prompt
from app.schemas.draft import DraftGenerateIn, DraftLLMOut, DraftSession
from app.services.docx_export import export_html_docx, export_markdown_docx


def new_draft_id() -> str:
    return uuid.uuid4().hex[:12]


def _fallback_markdown(raw: str) -> DraftLLMOut | None:
    """JSON 解析失败但内容像合同 markdown 时整体兜底"""
    if not raw:
        return None
    cleaned = raw.replace("```markdown", "").replace("```", "").strip()
    if cleaned.startswith("# ") and "第" in cleaned and "条" in cleaned:
        title = cleaned.splitlines()[0].lstrip("# ").strip()
        return DraftLLMOut(title=title or "未命名合同", markdown=cleaned)
    return None


async def generate_draft(req: DraftGenerateIn) -> DraftSession:
    if not req.keywords.strip():
        raise HTTPException(400, "关键词不能为空")

    messages = build_draft_prompt(req)
    session: DraftSession | None = None
    try:
        out = await chat_json(
            messages,
            schema=DraftLLMOut,
            temperature=settings.DRAFT_TEMPERATURE,
            max_tokens=settings.DRAFT_MAX_TOKENS,
            salvage=False,
        )
        session = DraftSession(
            id=new_draft_id(), title=out.title, markdown=out.markdown, keywords=req.keywords
        )
    except LLMFormatError:
        # 兜底：直接要一次裸 markdown
        raw = await chat_text(
            messages[:-1]
            + [
                {
                    "role": "user",
                    "content": messages[-1]["content"]
                    + "\n\n如果无法输出 JSON，直接输出 Markdown 合同全文，不要任何解释。",
                }
            ],
            temperature=settings.DRAFT_TEMPERATURE,
            max_tokens=settings.DRAFT_MAX_TOKENS,
        )
        fallback = _fallback_markdown(raw)
        if fallback is None:
            raise HTTPException(502, "合同生成失败，请稍后重试")
        session = DraftSession(
            id=new_draft_id(),
            title=fallback.title,
            markdown=fallback.markdown,
            keywords=req.keywords,
        )

    session.markdown = _clean_markdown(session.markdown)
    session.markdown = normalize_party_intro_lines(session.markdown)
    return session


def _clean_markdown(md: str) -> str:
    """去掉可能的围栏，统一行尾"""
    md = md.strip()
    if md.startswith("```"):
        lines = md.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        md = "\n".join(lines)
    return md


# 与 docx_export._PARTY_LINE_RE 同形（保证前后端对「当事人行」识别一致）：
# 甲方 / 乙方 / 丙方 / 丁方 / 出租方 / 承租方 / 采购方 / 供应方 / 卖方 / 买方 / 委托方 / 受托方
# 可选括号角色 + 冒号（半角 / 全角）
_PARTY_LEAD_RE = re.compile(
    r"^\s*(?:甲方|乙方|丙方|丁方|出租方|承租方|采购方|供应方|卖方|买方|委托方|受托方)"
    r"(?:[（(][^)）]+[)）])?"
    r"\s*[:：]"
)
# 抬头 / 鉴于是引言段特征：段落同时包含甲乙两方关键字（甲方 / 乙方 / 双方 / 两方）
_INTRO_KEYWORDS = ("甲方", "乙方", "双方", "两方")
# 签署栏标题（h2 标题关键词）：含「签署」二字即可，无需条号
_SIGN_HEADER_RE = re.compile(r"^\s*(?:##)?\s*第[一二三四五六七八九十百零0-9]+条?\s*签署栏\s*$|^\s*(?:##\s*)?签署栏\s*$")


def _looks_like_intro_paragraph(text: str) -> bool:
    """抬头 / 鉴于是引言段特征：含「甲方」「乙方」「双方」「两方」中的至少两个。

    单一关键字风险高（如正文里出现「甲方应在...」是正常段落），双关键字保证只命中
    同时介绍两方身份的引言 / 鉴于段落。
    """
    hits = sum(1 for kw in _INTRO_KEYWORDS if kw in text)
    return hits >= 2


def normalize_party_intro_lines(md: str) -> str:
    """把合同开头 / 鉴于引言 / 签署栏下的当事人称呼行和引言段转为引用块。

    输出 markdown 在 tiptap-markdown 渲染时成为 `<blockquote>`，
    前端 CSS 对 `<blockquote>` 取消首行缩进（与 docx 导出路径一致），
    从而彻底解决：
      1) 合同开头 `甲方（采购方）：【甲方名称】` 等当事人称呼行被误加首行缩进；
      2) `## 鉴于条款` / `## 鉴于` h2 后紧跟的甲乙方引言段被误加首行缩进；
      3) `## 签署栏` h2 后甲方 / 乙方签字盖章行被误加首行缩进。

    仅识别已知形态 + 不破坏既有 markdown 结构；处理后 LLM 修订时仍按同一规范化层再跑一遍，
    前端所见与导出 docx 永远一致。
    """
    if not md or not md.strip():
        return md

    lines = md.splitlines()
    out: list[str] = []
    in_signature_block = False  # 是否处于「签署栏」h2 之后
    prev_was_sign_header = False  # 上一行是签署栏 h2 / 显式标题

    i = 0
    n = len(lines)
    # 找到第一个非空段落索引（合同正文的真正起首，可能是标题或当事人行）
    first_text_idx = next(
        (idx for idx, ln in enumerate(lines) if ln.strip()), 0
    )

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # 1) 签署栏 h2 标题：标记进入签名块区域
        if stripped.startswith("## "):
            out.append(raw)
            in_signature_block = bool(_SIGN_HEADER_RE.match(stripped))
            i += 1
            continue
        # 空行不重置 in_signature_block（让 h2 与当事人行之间的空行保留区域状态）
        if not stripped:
            out.append(raw)
            i += 1
            continue
        # 其他 markdown 行（标题 / 围栏 / 列表 / 已 blockquote）原样保留并退出签名区域
        if (
            stripped.startswith("# ")
            or stripped.startswith("### ")
            or stripped.startswith("- ")
            or stripped.startswith("* ")
            or stripped.startswith("> ")
            or stripped.startswith("```")
        ):
            in_signature_block = False
            out.append(raw)
            i += 1
            continue

        # 2) 合同开头第一段（first_text_idx 起首的非空行）：当事人称呼行直接升级为引用块
        if i == first_text_idx and _PARTY_LEAD_RE.match(stripped):
            # 已在 blockquote 内则不再包裹
            if not raw.lstrip().startswith("> "):
                prefix = "".join(ch if ch in (" ", "\t") else "" for ch in raw[: len(raw) - len(raw.lstrip())])
                out.append(f"{prefix}> {stripped}")
                i += 1
                continue

        # 3) 鉴于条款 / 鉴于 / 鉴于是引言后的首段：含双关键字、职能提升为引用块
        if prev_was_sign_header is False and _looks_like_intro_paragraph(stripped):
            # 跳过已在 bucket 内的行
            if not raw.lstrip().startswith("> "):
                prefix = "".join(ch if ch in (" ", "\t") else "" for ch in raw[: len(raw) - len(raw.lstrip())])
                out.append(f"{prefix}> {stripped}")
                i += 1
                continue

        # 4) 签署栏 h2 后的一段或多段：含甲方 / 乙方的称呼 / 签章行职能提升为引用块
        #   以「甲方 / 乙方 / 丙方 + 可选括号角色 + 冒号」开头或包含「（签字）」「（盖章）」
        if in_signature_block:
            is_sign_line = (
                _PARTY_LEAD_RE.match(stripped) is not None
                or "（签字）" in stripped
                or "（盖章）" in stripped
                or "签字：" in stripped
                or "盖章：" in stripped
                or "日期：" in stripped
            )
            if is_sign_line and not raw.lstrip().startswith("> "):
                prefix = "".join(ch if ch in (" ", "\t") else "" for ch in raw[: len(raw) - len(raw.lstrip())])
                out.append(f"{prefix}> {stripped}")
                i += 1
                continue
            # 非签章行（如「甲方与乙方就本合同...」）也属于签署栏尾段：含双关键字则升引用块
            if _looks_like_intro_paragraph(stripped) and not raw.lstrip().startswith("> "):
                prefix = "".join(ch if ch in (" ", "\t") else "" for ch in raw[: len(raw) - len(raw.lstrip())])
                out.append(f"{prefix}> {stripped}")
                i += 1
                continue
            # 离开签署栏区域（出现非签章、非引言的段落）
            in_signature_block = False

        out.append(raw)
        prev_was_sign_header = False
        i += 1

    return "\n".join(out)


async def revise_draft(session: DraftSession, instruction: str) -> DraftSession:
    """每次"当前全文 + 指令"整篇重生成（不用多轮历史，避免上下文污染）"""
    if not instruction.strip():
        raise HTTPException(400, "修改要求不能为空")
    messages = build_revise_prompt(session.markdown, instruction)
    try:
        out = await chat_json(
            messages,
            schema=DraftLLMOut,
            temperature=settings.DRAFT_TEMPERATURE,
            max_tokens=settings.DRAFT_MAX_TOKENS,
            salvage=False,
        )
        session.title = out.title or session.title
        session.markdown = normalize_party_intro_lines(_clean_markdown(out.markdown))
    except LLMFormatError:
        raw = await chat_text(
            messages[:-1]
            + [
                {
                    "role": "user",
                    "content": messages[-1]["content"]
                    + "\n\n如果无法输出 JSON，直接输出修改后的完整 Markdown 合同全文。",
                }
            ],
            temperature=settings.DRAFT_TEMPERATURE,
            max_tokens=settings.DRAFT_MAX_TOKENS,
        )
        fallback = _fallback_markdown(raw)
        if fallback is None:
            raise HTTPException(502, "修订失败，请调整措辞后重试")
        session.title = fallback.title
        session.markdown = normalize_party_intro_lines(_clean_markdown(fallback.markdown))

    from app.schemas.draft import HistoryItem

    session.history.append(HistoryItem(instruction=instruction, result_title=session.title))
    return session


def export_draft_docx(session: DraftSession, *, html: str | None = None) -> tuple[io.BytesIO, str]:
    """返回 (字节流, 下载文件名)——字节全程内存，不落盘"""
    safe_title = session.title.strip() or "合同草稿"
    out_name = f"{session.id}_{safe_title[:30]}.docx"
    if html and html.strip():
        buf = export_html_docx(session.title, html, out_name)
    else:
        buf = export_markdown_docx(session.title, session.markdown, out_name)
    buf.seek(0)
    return buf, out_name
