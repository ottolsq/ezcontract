"""起草路由"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.draft import ContentIn, DraftGenerateIn, ExportIn, ReviseIn
from app.services import draft_service
from app.storage import SESSIONS, get_draft

router = APIRouter(prefix="/api/draft", tags=["draft"])


def _run_generation_task(session_id: str, req: DraftGenerateIn):
    """后台执行生成任务；若 session 已被取消/移除则不再写回。"""

    async def _task():
        session = get_draft(session_id)
        if session is None:
            return
        session = await draft_service.generate_draft(session, req)
        # 任务完成后仅当 session 仍存在时才写回，避免取消后污染状态
        if get_draft(session_id) is not None:
            SESSIONS[session.id] = session

    return _task


def _run_revision_task(session_id: str, instruction: str):
    """后台执行修订任务；若 session 已被取消/移除则不再写回。"""

    async def _task():
        session = get_draft(session_id)
        if session is None:
            return
        session = await draft_service.revise_draft(session, instruction)
        if get_draft(session_id) is not None:
            SESSIONS[session.id] = session

    return _task


@router.post("/generate")
async def generate(req: DraftGenerateIn):
    session = draft_service.create_generating_session(req)
    SESSIONS[session.id] = session
    # 与审查模块对齐：立即返回 processing，后台异步执行
    asyncio.get_running_loop().create_task(_run_generation_task(session.id, req)())
    return session.model_dump()


@router.get("/{draft_id}")
async def get(draft_id: str):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    return session.model_dump()


@router.get("/{draft_id}/status")
async def status(draft_id: str):
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    return {
        "status": session.status,
        "progress": session.progress,
        "stage": session.stage,
        "error": session.error,
    }


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
    # 与生成对齐：先置为 processing，再后台执行
    session.status = "processing"
    session.progress = 10
    session.stage = "正在提交修订请求"
    SESSIONS[session.id] = session
    asyncio.get_running_loop().create_task(
        _run_revision_task(session.id, body.instruction)()
    )
    return session.model_dump()


@router.post("/{draft_id}/cancel")
async def cancel(draft_id: str):
    """取消正在生成/修订的草稿任务（前端主动放弃）。"""
    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")
    SESSIONS.pop(session.id, None)
    return {"ok": True}


@router.post("/{draft_id}/export")
async def export(draft_id: str, body: ExportIn | None = Body(default=None)):
    import asyncio
    from urllib.parse import quote

    session = get_draft(draft_id)
    if session is None:
        raise HTTPException(404, "草稿不存在")

    html = body.html if body else None
    buf, out_name = await asyncio.to_thread(
        draft_service.export_draft_docx, session, html=html
    )
    safe_title = session.title.strip()[:30] or "合同草稿"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title + '.docx')}"
        },
    )
