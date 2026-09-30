"""站内通知路由（惰性检查在 GET 时执行）"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.schemas.compliance import NotificationReadIn
from app.services import compliance_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_all():
    return await asyncio.to_thread(compliance_service.list_notifications)


@router.post("/read")
async def mark_read(body: NotificationReadIn):
    return await asyncio.to_thread(
        compliance_service.mark_notifications_read, body.ids, body.all
    )
