from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    customer_id: str | None = None


class Citation(BaseModel):
    title: str | None = None
    url: str | None = None
    path: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]


class SessionCreateRequest(BaseModel):
    customer_id: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: str


class MessageRecord(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime


class SessionDetail(BaseModel):
    session_id: str
    customer_id: str | None = None
    messages: list[MessageRecord]
