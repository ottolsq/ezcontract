"""审查路由"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import BASE_DIR
from app.schemas.review import DecisionIn
from app.services import review_service
from app.storage import SESSIONS, get_review

router = APIRouter(prefix="/api/review", tags=["review"])


def _url_quote_filename(filename: str) -> str:
    """RFC 5987 编码中文文件名"""
    from urllib.parse import quote

    return f"attachment; filename*=UTF-8''{quote(filename)}"


@router.post("/upload")
async def upload(file: UploadFile):
    session = await review_service.save_upload(file)
    SESSIONS[session.id] = session
    return {
        "review_id": session.id,
        "filename": session.filename,
        "file_type": session.file_type,
        "clause_count": len(session.clauses),
        "clauses": [c.model_dump() for c in session.clauses],
        "preamble_html": session.preamble_html,
        "tail_html": session.tail_html,
    }


@router.post("/sample")
async def upload_sample():
    """载入内置测试合同（前端"载入测试合同"按钮）

    测试合同在镜像构建期生成并嵌入镜像，运行时只读；不落盘用户数据目录。
    """
    import io

    sample_path = BASE_DIR / "sample_contract.docx"
    if not sample_path.exists():
        raise HTTPException(
            404, "测试合同未生成，请先运行 scripts/make_sample_docx.py 或重新构建镜像"
        )

    class _FakeFile(UploadFile):
        def __init__(self, path):
            self.file = io.BytesIO(path.read_bytes())
            self.filename = path.name

    session = await review_service.save_upload(_FakeFile(sample_path))  # type: ignore[arg-type]
    SESSIONS[session.id] = session
    return {
        "review_id": session.id,
        "filename": session.filename,
        "file_type": session.file_type,
        "clause_count": len(session.clauses),
        "clauses": [c.model_dump() for c in session.clauses],
        "preamble_html": session.preamble_html,
        "tail_html": session.tail_html,
    }


@router.post("/{review_id}/start")
async def start(review_id: str):
    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    if session.status == "processing":
        return {"status": "processing"}
    if session.status == "completed":
        return {"status": "completed"}
    review_service.start_review_task(session)
    return {"status": "processing"}


@router.get("/{review_id}/status")
async def status(review_id: str):
    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    return {
        "status": session.status,
        "progress": session.progress,
        "stage": session.stage,
        "error": session.error,
    }


@router.get("/{review_id}/result")
async def result(review_id: str):
    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    if session.status != "completed":
        raise HTTPException(400, f"审查尚未完成（当前状态：{session.status}）")
    return {
        "review_id": session.id,
        "risks": [r.model_dump() for r in session.risks],
        "score": session.score,
        "stats": {
            "high": sum(1 for r in session.risks if r.level == "high"),
            "medium": sum(1 for r in session.risks if r.level == "medium"),
            "low": sum(1 for r in session.risks if r.level == "low"),
        },
        "clauses": [c.model_dump() for c in session.clauses],
        "preamble_html": session.preamble_html,
        "tail_html": session.tail_html,
        "decisions": {k: v.model_dump() for k, v in session.decisions.items()},
        "truncated_salvaged": session.truncated_salvaged,
    }


@router.put("/{review_id}/decisions")
async def save_decisions(review_id: str, body: DecisionIn):
    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    valid_risk_ids = {r.risk_id for r in session.risks}
    decisions = [d for d in body.decisions if d.risk_id in valid_risk_ids]
    n = review_service.apply_decisions(session, decisions)
    return {"ok": True, "processed": n}


@router.post("/{review_id}/export")
async def export_contract(review_id: str):
    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    if session.status != "completed":
        raise HTTPException(400, "审查尚未完成")
    buf = await review_service.export_review_docx(session)
    stem = session.filename.rsplit(".", 1)[0]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _url_quote_filename(f"{stem}_修改版.docx")},
    )


@router.post("/{review_id}/report/export")
async def export_report(review_id: str):
    import asyncio

    from app.services.docx_export import export_review_report

    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    if session.status != "completed":
        raise HTTPException(400, "审查尚未完成")
    buf = await asyncio.to_thread(export_review_report, session)
    buf.seek(0)
    stem = session.filename.rsplit(".", 1)[0]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _url_quote_filename(f"{stem}_审核报告.docx")},
    )

