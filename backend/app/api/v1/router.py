"""Versioned API router: every module mounted under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    battle_voting,
    challenges,
    creators,
    discovery,
    health,
    media,
    media_stream,
    messaging,
    moderation,
    social,
    users,
    videos,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(media.router)
api_router.include_router(media_stream.router)
api_router.include_router(videos.router)
api_router.include_router(social.router)
api_router.include_router(discovery.router)
api_router.include_router(challenges.router)
api_router.include_router(battle_voting.router)
api_router.include_router(creators.router)
api_router.include_router(messaging.router)
api_router.include_router(moderation.router)
api_router.include_router(admin.router)