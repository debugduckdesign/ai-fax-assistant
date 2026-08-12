from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class CaseStatus(StrEnum):
    EXTRACTING = "extracting"
    AWAITING_CALL = "awaiting_call"
    CALLING = "calling"
    COMPLETE = "complete"
    NEEDS_HUMAN = "needs_human"
    ERROR = "error"


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class FieldValue(BaseModel):
    value: str | None = None
    confidence: float = 0.0
    source: str = "ocr"


class ExtractionResult(BaseModel):
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    call_recommended: bool = False
    call_to: str | None = None
    call_reason: str | None = None


class CallInfo(BaseModel):
    to: str | None = None
    conversation_id: str | None = None
    status: str | None = None
    transcript: str | None = None
    reason: str | None = None


class CaseRecord(BaseModel):
    id: str
    status: CaseStatus = CaseStatus.EXTRACTING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    scan_filename: str
    scan_content_type: str | None = None
    created_by_user_id: str | None = None
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    call_recommended: bool = False
    call: CallInfo = Field(default_factory=CallInfo)
    error: str | None = None
    case_md: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now()


class CaseSummary(BaseModel):
    id: str
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    scan_filename: str
    call_recommended: bool
    missing_required: list[str]
    call_to: str | None = None
    created_by_user_id: str | None = None


class RequirementsUpdate(BaseModel):
    content: str


class RequirementsResponse(BaseModel):
    content: str
    path: str


class PlaceCallResponse(BaseModel):
    case_id: str
    conversation_id: str | None
    status: CaseStatus
    message: str


class UserPublic(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    created_at: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.OPERATOR


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = None


class CallEvent(BaseModel):
    id: str
    case_id: str
    user_id: str | None = None
    username: str | None = None
    conversation_id: str | None = None
    to_number: str | None = None
    status: str
    reason: str | None = None
    transcript_excerpt: str | None = None
    created_at: str
    updated_at: str
