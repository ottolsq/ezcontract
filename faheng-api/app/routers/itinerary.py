"""人员行程模块路由"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.schemas.itinerary import (
    ArtistCreateIn,
    ConfirmIn,
    EventCreateIn,
    EventUpdateIn,
    VoiceParseIn,
)
from app.services import itinerary_service

router = APIRouter(prefix="/api/itinerary", tags=["itinerary"])


@router.get("/artists")
async def list_artists():
    return {"artists": await asyncio.to_thread(itinerary_service.list_artists)}


@router.post("/artists")
async def create_artist(body: ArtistCreateIn):
    return await asyncio.to_thread(itinerary_service.create_artist, body)


@router.delete("/artists/{artist_id}")
async def remove_artist(artist_id: str):
    return await asyncio.to_thread(itinerary_service.delete_artist, artist_id)


@router.get("/artists/{artist_id}/events")
async def list_events(artist_id: str, month: str | None = None, date: str | None = None):
    return {"events": await asyncio.to_thread(itinerary_service.list_events, artist_id, month, date)}


@router.post("/events")
async def create_event(body: EventCreateIn):
    return await asyncio.to_thread(itinerary_service.create_event, body)


@router.put("/events/{event_id}")
async def update_event(event_id: str, body: EventUpdateIn):
    # 路由层 event_id 优先级高于 body.id
    updated = body.model_copy(update={"id": event_id})
    return await asyncio.to_thread(itinerary_service.update_event, updated)


@router.delete("/events/{event_id}")
async def remove_event(event_id: str):
    return await asyncio.to_thread(itinerary_service.delete_event, event_id)


@router.post("/parse-voice")
async def parse_voice(body: VoiceParseIn):
    return await itinerary_service.parse_voice(body)


@router.post("/confirm")
async def confirm_events(body: ConfirmIn):
    return await asyncio.to_thread(itinerary_service.confirm_events, body)
