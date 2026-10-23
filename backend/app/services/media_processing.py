"""FFmpeg integration: probing, thumbnails and rendition transcodes.

Runs inside the Celery worker (never inside a request), so uploads stay fast and
a crashed transcode can be retried without losing the original file.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger("vibespace.video")

RENDITION_HEIGHTS = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
RENDITION_BITRATES = {"1080p": "5000k", "720p": "2800k", "480p": "1400k", "360p": "800k"}


@dataclass
class VideoMetadata:
    duration_seconds: float | None
    width: int | None
    height: int | None
    frame_rate: float | None
    has_audio: bool
    video_codec: str | None
    bit_rate: int | None


def ffmpeg_available() -> bool:
    return bool(shutil.which(settings.ffmpeg_binary)) and bool(shutil.which(settings.ffprobe_binary))


def require_ffmpeg() -> None:
    if not ffmpeg_available():
        raise AppError(
            "FFmpeg is not installed in this environment, so video processing cannot run.",
            details={"expected_binaries": [settings.ffmpeg_binary, settings.ffprobe_binary]},
        )


def _run(command: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    logger.info("running media command: %s", command[0])
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)


def probe(path: Path) -> VideoMetadata:
    require_ffmpeg()
    result = _run(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=120,
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    if video is None:
        raise AppError("That file has no video stream, so it cannot be published as a video.")

    frame_rate = None
    if video.get("avg_frame_rate") and video["avg_frame_rate"] not in {"0/0", None}:
        numerator, _, denominator = str(video["avg_frame_rate"]).partition("/")
        try:
            frame_rate = float(numerator) / float(denominator or 1)
        except (ValueError, ZeroDivisionError):
            frame_rate = None

    duration = payload.get("format", {}).get("duration") or video.get("duration")
    bit_rate = payload.get("format", {}).get("bit_rate")
    return VideoMetadata(
        duration_seconds=float(duration) if duration else None,
        width=int(video["width"]) if video.get("width") else None,
        height=int(video["height"]) if video.get("height") else None,
        frame_rate=round(frame_rate, 2) if frame_rate else None,
        has_audio=audio is not None,
        video_codec=video.get("codec_name"),
        bit_rate=int(bit_rate) if bit_rate else None,
    )


def generate_thumbnail(source: Path, destination: Path, at_seconds: float | None = None) -> Path:
    require_ffmpeg()
    seek = at_seconds if at_seconds is not None else 1.0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(
            [
                settings.ffmpeg_binary,
                "-y",
                "-ss",
                f"{seek:.2f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=720:-2",
                str(destination),
            ],
            timeout=300,
        )
    except subprocess.CalledProcessError:
        # Very short clips can fail at the 1s mark — retry from the first frame.
        _run(
            [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=720:-2",
                str(destination),
            ],
            timeout=300,
        )
    return destination


def transcode_rendition(source: Path, destination: Path, label: str) -> Path:
    require_ffmpeg()
    height = RENDITION_HEIGHTS.get(label)
    if height is None:
        raise AppError(f"Unsupported rendition '{label}'.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(source),
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            RENDITION_BITRATES.get(label, "1400k"),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return destination


def renditions_to_build(source_height: int | None) -> list[str]:
    """Never upscale: an SD source only gets renditions below its own height."""
    configured = settings.rendition_list or ["720p"]
    if not source_height:
        return configured
    return [label for label in configured if RENDITION_HEIGHTS.get(label, 0) <= source_height] or []