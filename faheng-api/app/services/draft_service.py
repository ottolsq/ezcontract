"""起草服务：生成 / 修订 / 内容保存 / 导出"""
from __future__ import annotations

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
        session.markdown = _clean_markdown(out.markdown)
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
        session.markdown = fallback.markdown

    from app.schemas.draft import HistoryItem

    session.history.append(HistoryItem(instruction=instruction, result_title=session.title))
    return session


def export_draft_docx(session: DraftSession, *, html: str | None = None) -> "Path":
    safe_title = session.title.strip() or "合同草稿"
    out_name = f"{session.id}_{safe_title[:30]}.docx"
    if html and html.strip():
        return export_html_docx(session.title, html, out_name)
    return export_markdown_docx(session.title, session.markdown, out_name)
