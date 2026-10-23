"""Opaque keyset-pagination cursors shared by every list endpoint."""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime, timezone


class InvalidCursorError(ValueError):
    pass


def encode_cursor(created_at: datetime | None, row_id: uuid.UUID) -> str:
    stamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    raw = json.dumps({"t": stamp, "i": str(row_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return datetime.fromisoformat(payload["t"]), uuid.UUID(payload["i"])
    except (ValueError, KeyError, binascii.Error, json.JSONDecodeError) as exc:
        raise InvalidCursorError("Malformed pagination cursor.") from exc


def clamp_limit(limit: int, *, default: int = 20, maximum: int = 100) -> int:
    return max(1, min(limit or default, maximum))