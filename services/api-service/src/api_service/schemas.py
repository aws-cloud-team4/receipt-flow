"""Request models shared by API routes and receipt workflows."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints


class PatchReceipt(BaseModel):
    fields: dict[str, Any]


class CheckNote(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ChangeRequest(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    fields: list[str] = Field(default_factory=list, max_length=10)  # what to look at again; "photo" = retake
