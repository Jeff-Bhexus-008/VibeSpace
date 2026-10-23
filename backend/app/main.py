"""VibeSpace API entry point.

Run locally:  uvicorn app.main:app --reload
Render start: uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.v1.endpoints import ws
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.media_processing import ffmpeg_available
from app.services.realtime import hub

logger = logging.getLogger("vibespace")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    logger.info(
        "starting VibeSpace API",
        extra={
            "version": __version__,
            "environment": settings.environment,
            "storage_configured": settings.storage_configured,
            "email_configured": settings.email_delivery_configured,
            "ffmpeg_available": ffmpeg_available(),
        },
    )
    if not settings.storage_configured:
        logger.warning("object storage is not configured — uploads will return a clear setup error")
    if settings.video_processing_enabled and not ffmpeg_available():
        logger.warning("FFmpeg is missing — start the worker on a host where ffmpeg/ffprobe are installed")

    try:
        await hub.start()
    except Exception as exc:  # pragma: no cover - cache outage
        logger.warning("real-time fan-out disabled: %s", exc)

    yield

    await hub.stop()


app = FastAPI(
    title="VibeSpace API",
    version=__version__,
    description=(
        "Social entertainment and video-sharing platform API: accounts, feed, battles, "
        "voting, LearnSpace, messaging, moderation and creator analytics."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
if settings.trusted_host_list and settings.trusted_host_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # cookies carry the session
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": "VibeSpace API",
        "version": __version__,
        "docs": "/docs",
        "api": "/api/v1",
        "health": "/health",
    }


@app.get("/health", include_in_schema=False)
def root_health() -> dict:
    return {"status": "ok", "version": __version__}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=settings.debug)