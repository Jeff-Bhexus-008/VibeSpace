"""Shared schema helpers: pagination envelopes, ids, simple acknowledgements."""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Cursor pagination: `next_cursor` is opaque and passed back as `?cursor=`."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class IdResponse(BaseModel):
    id: uuid.UUID


class AckResponse(BaseModel):
    ok: bool = True
    message: str | None = None
    # Development convenience only, and only while SMTP is unconfigured:
    # the action link is returned instead of being emailed.
    dev_reset_link: str | None = None
    dev_verify_link: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PageParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None