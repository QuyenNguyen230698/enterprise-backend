from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from app.models.meeting_model import MeetingType, MeetingStatus, InviteRole, InviteStatus


# ─── MeetingInvite Schemas ────────────────────────────────────────

class MeetingInviteCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: InviteRole = InviteRole.attendee

    class Config:
        json_schema_extra = {
            "example": {"email": "user@company.com", "name": "User Name", "role": "attendee"}
        }


class MeetingInviteRespond(BaseModel):
    token: str
    action: InviteStatus  # accepted | declined


class MeetingInviteResponse(MeetingInviteCreate):
    id: int
    meeting_id: int
    status: InviteStatus
    action: Optional[str] = None  # "accepted" | "declined" | None
    token: str
    responded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @property
    def _action(self) -> Optional[str]:
        if self.status in (InviteStatus.accepted, InviteStatus.declined):
            return self.status.value
        return None

    def model_post_init(self, __context) -> None:
        if self.status in (InviteStatus.accepted, InviteStatus.declined):
            object.__setattr__(self, "action", self.status.value)

    class Config:
        from_attributes = True


# ─── Meeting Schemas ──────────────────────────────────────────────

class MeetingCreate(BaseModel):
    title: str
    type: MeetingType = MeetingType.internal
    area_id: int
    room_id: int
    date: str                   # YYYY-MM-DD
    start_time: str             # HH:mm
    end_time: str               # HH:mm
    duration: Optional[str] = None
    notes: Optional[str] = ""
    need_it_support: bool = False
    cc_emails: Optional[str] = ""
    organizer_id: str
    created_by: str
    attendee_ids: List[str] = []
    attendee_count: int = 1
    rrule: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Q2 Strategy Alignment",
                "type": "internal",
                "area_id": 1,
                "room_id": 1,
                "date": "2026-04-10",
                "start_time": "09:00",
                "end_time": "10:30",
                "organizer_id": "888",
                "created_by": "888",
                "attendee_ids": ["100", "101"]
            }
        }


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[MeetingStatus] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[str] = None
    notes: Optional[str] = None
    need_it_support: Optional[bool] = None
    room_id: Optional[int] = None
    attendee_ids: Optional[List[str]] = None
    attendee_count: Optional[int] = None
    hr_approval_status: Optional[str] = None


class MeetingResponse(MeetingCreate):
    id: int
    tenant_id: str
    status: MeetingStatus = MeetingStatus.scheduled
    hr_approval_status: Optional[str] = "pending"
    it_support_status: Optional[str] = "pending"
    zoom_join_url: Optional[str] = None
    zoom_password: Optional[str] = None
    teams_join_url: Optional[str] = None
    teams_passcode: Optional[str] = None
    invites: List[MeetingInviteResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
