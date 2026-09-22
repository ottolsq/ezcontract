"""起草路由"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from app.schemas.draft import ContentIn, DraftGenerateIn, ExportIn, ReviseIn
from app.services import draft_service
from app.storage import SESSIONS, get_draft

router = APIRouter(prefix="/api/draft", tags=["draft"])


@router.post("/generate")
async def generate(req: DraftGenerateIn):
    session = await draft_service.generate_draft(req)
    SESSIONS[session.id] = session
    return session.model_dump()


@router.get("/{draft_id}")
async def get(draft_id: str):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    return session.model_dump()


@router.put("/{draft_id}/content")
async def update_content(draft_id: str, body: ContentIn):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    session.markdown = body.markdown
    return {"ok": True}


@router.post("/{draft_id}/revise")
async def revise(draft_id: str, body: ReviseIn):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    session = await draft_service.revise_draft(session, body.instruction)
    return session.model_dump()


@router.post("/{draft_id}/export")
async def export(draft_id: str, body: ExportIn | None = Body(default=None)):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    import asyncio

    html = body.html if body else None
    path = await asyncio.to_thread(draft_service.export_draft_docx, session, html=html)
    from urllib.parse import quote

    safe_title = session.title.strip()[:30] or "合同草稿"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title + '.docx')}"},
    )
