from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models import DocStatus, Role, Visibility


class TokenUser(BaseModel):
    id: UUID
    email: str
    role: Role
    must_change_password: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class ExternalStartRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class CreateInternalUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=12)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=12)


class UserOut(BaseModel):
    id: UUID
    email: str
    role: Role
    is_active: bool
    query_count: int
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    visibility: Visibility
    visibility_override: bool
    status: DocStatus
    progress_step: str
    progress_pct: int
    error: Optional[str] = None
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class VisibilityOverride(BaseModel):
    visibility: Visibility


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class Citation(BaseModel):
    document_id: UUID
    title: str
    page: Optional[int] = None
    sheet: Optional[str] = None
    snippet: str
    content_kind: str = "text"


class ChatResponse(BaseModel):
    answer: str
    refused: bool = False
    citations: list[Citation] = []


class MeResponse(BaseModel):
    user: UserOut
    csrf: str
    site: Literal["chat", "admin"]
