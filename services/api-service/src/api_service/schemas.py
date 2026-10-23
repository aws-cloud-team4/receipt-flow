"""Request models shared by API routes and receipt workflows."""

from typing import Any

from pydantic import BaseModel, Field


class PatchReceipt(BaseModel):
    fields: dict[str, Any]


class ChangeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    fields: list[str] = Field(default_factory=list, max_length=10)  # what to look at again; "photo" = retake
