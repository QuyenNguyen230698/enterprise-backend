import enum
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, ARRAY, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class MeetingType(str, enum.Enum):
    internal = "internal"
    external = "external"


class MeetingStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class InviteRole(str, enum.Enum):
    organizer = "organizer"
    attendee = "attendee"
    cc = "cc"


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    enqueued = "enqueued"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    type = Column(SAEnum(MeetingType), default=MeetingType.internal)
    status = Column(SAEnum(MeetingStatus), default=MeetingStatus.scheduled)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    date = Column(String, nullable=False, index=True)       # YYYY-MM-DD
    start_time = Column(String, nullable=False)             # HH:mm
    end_time = Column(String, nullable=False)               # HH:mm
    duration = Column(String, nullable=True)
    notes = Column(String, default="")
    need_it_support = Column(Boolean, default=False)
    cc_emails = Column(String, default="")
    hr_approved_by = Column(String, nullable=True)
    hr_approval_status = Column(String, default="pending")
    it_support_status = Column(String, default="pending")

    # Portal user refs
    organizer_id = Column(String, nullable=False, index=True)
    created_by = Column(String, nullable=False)
    attendee_ids = Column(ARRAY(String), default=[])
    attendee_count = Column(Integer, default=1)

    # Zoom integration
    zoom_meeting_id = Column(String, nullable=True)
    zoom_join_url = Column(String, nullable=True)
    zoom_password = Column(String, nullable=True)
    zoom_host_key = Column(String, nullable=True)
    zoom_account_id = Column(Integer, nullable=True)

    # Teams integration
    teams_join_url = Column(String, nullable=True)
    teams_meeting_id = Column(String, nullable=True)
    teams_passcode = Column(String, nullable=True)
    teams_organizer_url = Column(String, nullable=True)

    # Recurring support
    rrule = Column(String, nullable=True)
    recurring_parent_id = Column(Integer, nullable=True)
    recurrence_id = Column(String, nullable=True)

    # tenant_id: real tenant (e.g. "tenant_gtc_001") or personal ("personal_{portal_user_id}")
    tenant_id = Column(String, nullable=False, index=True)

    sequence = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    area = relationship("Area", back_populates="meetings")
    room = relationship("Room", back_populates="meetings")
    invites = relationship("MeetingInvite", back_populates="meeting", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_meetings_date_start", "date", "start_time"),
        Index("ix_meetings_status", "status"),
        Index("ix_meetings_room_id", "room_id"),
        Index("ix_meetings_area_id", "area_id"),
    )


class MeetingInvite(Base):
    __tablename__ = "meeting_invites"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    role = Column(SAEnum(InviteRole), default=InviteRole.attendee)
    status = Column(SAEnum(InviteStatus), default=InviteStatus.pending)
    token = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    meeting = relationship("Meeting", back_populates="invites")
