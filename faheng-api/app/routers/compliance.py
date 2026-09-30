"""履约模块路由（薄 HTTP 层；DB 调用一律 asyncio.to_thread 包装）"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, UploadFile

from app.config import BASE_DIR
from app.schemas.compliance import MilestoneDueDateIn, MilestoneStatusIn
from app.services import compliance_service

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.post("/upload")
async def upload(file: UploadFile):
    summary = await compliance_service.save_upload(file)
    return summary


@router.post("/sample")
async def upload_sample():
    """载入内置测试合同（前端「载入测试合同」按钮，口径同 review/sample）"""
    from fastapi import HTTPException

    sample_path = BASE_DIR.parent / "exmple" / "房屋租赁合同 (1).docx"
    if not sample_path.exists():
        raise HTTPException(404, "测试合同不存在，请把 exmple/房屋租赁合同 (1).docx 放入项目根目录")

    import io

    class _FakeFile(UploadFile):
        def __init__(self, path):
            self.file = io.BytesIO(path.read_bytes())
            self.filename = path.name

    return await compliance_service.save_upload(_FakeFile(sample_path))  # type: ignore[arg-type]


@router.get("/contracts")
async def contracts():
    return {"contracts": await asyncio.to_thread(compliance_service.list_contracts)}


@router.post("/{contract_id}/extract")
async def extract(contract_id: str):
    status = compliance_service.start_extract(contract_id)
    return {"status": status}


@router.get("/{contract_id}/status")
async def status(contract_id: str):
    return await asyncio.to_thread(compliance_service.get_contract_status, contract_id)


@router.get("/{contract_id}")
async def detail(contract_id: str):
    return await asyncio.to_thread(compliance_service.get_contract_detail, contract_id)


@router.delete("/{contract_id}")
async def remove(contract_id: str):
    return await asyncio.to_thread(compliance_service.delete_contract, contract_id)


@router.post("/milestones/{milestone_id}/status")
async def set_status(milestone_id: str, body: MilestoneStatusIn):
    return await asyncio.to_thread(
        compliance_service.set_milestone_status, milestone_id, body.status
    )


@router.put("/milestones/{milestone_id}/due-date")
async def set_due_date(milestone_id: str, body: MilestoneDueDateIn):
    return await asyncio.to_thread(
        compliance_service.set_milestone_due_date, milestone_id, body.due_date
    )
