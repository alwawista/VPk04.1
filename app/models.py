from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Channel(StrEnum):
    email = "email"
    form = "form"
    chat = "chat"


class Category(StrEnum):
    billing = "billing"
    support = "support"
    complaint = "complaint"
    other = "other"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class TicketIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(..., min_length=1, max_length=2000)
    channel: Channel
    client_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:@-]+$")

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class TriageResult(BaseModel):
    category: Category = Category.other
    draft_reply: str = Field(..., min_length=1, max_length=2000)
    confidence: Confidence = Confidence.low
    escalate: bool = True


class TriageResponse(BaseModel):
    """Контракт POST /triage — поля ответа по заданию."""

    category: Category
    draft_reply: str
    confidence: Confidence
    escalate: bool


class HealthResponse(BaseModel):
    status: str
    storage: str
    limiter: str
    llm_provider: str
    warnings: list[str]
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StoredTicket(BaseModel):
    id: int
    created_at: str
    client_id: str
    channel: Channel
    text: str
    category: Category | None = None
    confidence: Confidence | None = None
    escalate: bool | None = None
    draft_reply: str | None = None
    error: str | None = None
