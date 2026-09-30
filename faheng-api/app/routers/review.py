"""审查路由"""
from __future__ import annotations

import io as _io

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import BASE_DIR
from app.parser.clause_splitter import split_clauses
from app.parser.docx_parser import extract_docx_paragraphs
from app.schemas.review import DecisionIn
from app.services import review_service
from app.storage import SESSIONS, get_review

router = APIRouter(prefix="/api/review", tags=["review"])


def _url_quote_filename(filename: str) -> str:
    """RFC 5987 编码中文文件名"""
    from urllib.parse import quote

    return f"attachment; filename*=UTF-8''{quote(filename)}"


@router.post("/parse")
async def parse_only(file: UploadFile):
    """诊断接口：只做"上传 → 拆条款"两步，不入库、不审查。

    用于排查格式/正则/拆分问题。返回 docx 段落 + 拆出的 clauses / preamble / tail。
    PDF 暂不支持（PDF 走 OCR 链路，与 docx 解析不同）。
    """
    raw = await file.read()
    if not raw[:4] == b"PK\x03\x04":
        raise HTTPException(400, "目前诊断接口只支持 docx（PDF 走 OCR，请改用 /upload）")

    paragraphs = extract_docx_paragraphs(_io.BytesIO(raw))
    clauses, preamble, tail = split_clauses(paragraphs)

    def _para_summary(idx: int, p) -> dict:
        # ParagraphInfo 实际只有 text/html 两字段；样式信息在 html 内联属性里
        # （font-family / font-weight / font-size 等），前端需要时自行解析。
        return {"idx": idx, "text": p.text, "html": p.html}

    pre_idx_map = {id(p): i for i, p in enumerate(paragraphs)}
    return {
        "filename": file.filename,
        "paragraph_total": len(paragraphs),
        "preamble": [_para_summary(pre_idx_map[id(p)], p) for p in preamble],
        "clauses": [
            {
                **clause.model_dump(),
                # 列出条款原始段落（含 idx / html），便于诊断正则匹配与样式
                "paragraphs": [
                    _para_summary(i, paragraphs[i])
                    for i in range(clause.start_idx, clause.end_idx + 1)
                ],
            }
            for clause in clauses
        ],
        "tail": [_para_summary(pre_idx_map[id(p)], p) for p in tail],
        "warnings": [],
    }


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

    # 真实合同样本：项目根目录下的 exmple/房屋租赁合同 (1).docx
    sample_path = BASE_DIR.parent / "exmple" / "房屋租赁合同 (1).docx"
    if not sample_path.exists():
        raise HTTPException(
            404, "测试合同未生成，请把 exmple/房屋租赁合同 (1).docx 放入项目根目录后重试"
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
async def export_contract(review_id: str, track_changes: bool = False):
    """导出最终合同；默认走干净版（直接给用户修改后正确的合同，无修订标记）。

    ?track_changes=true 显式打开评审记录模式（带 w:ins/w:del 修订痕迹）。
    响应头 X-Skipped-Actions 携带未落地的编辑动作原因（JSON 数组），
    前端据此提示"某条建议未能定位到子项"。
    """
    import json as _json

    session = get_review(review_id)
    if session is None:
        raise HTTPException(404, "审查任务不存在")
    if session.status != "completed":
        raise HTTPException(400, "审查尚未完成")
    buf, skipped = await review_service.export_review_docx(
        session, track_changes=track_changes
    )
    stem = session.filename.rsplit(".", 1)[0]
    suffix = "_修订版" if track_changes else "_修改版"
    headers = {
        "Content-Disposition": _url_quote_filename(f"{stem}{suffix}.docx"),
    }
    if skipped:
        # 中文原因含非 ASCII，HTTP 头只允许 ASCII → RFC 2047 百分号编码，前端 decodeURIComponent
        from urllib.parse import quote as _quote

        headers["X-Skipped-Actions"] = _quote(";".join(skipped))
        headers["X-Skipped-Count"] = str(len(skipped))
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
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

