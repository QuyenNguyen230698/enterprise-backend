from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Enum, Text
from sqlalchemy.sql import func
from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    portal_user_id = Column(String, nullable=False, index=True)

    # Basic info
    name = Column(String(200), nullable=False)
    subject = Column(String(500), nullable=False)
    preheader = Column(String(500), nullable=True)

    # Sender info (NOT NULL in DB)
    sender_name = Column(String(200), nullable=False)
    sender_email = Column(String(320), nullable=False)

    # Sender — stored as JSON string: { name, email, replyTo, cc, bcc }
    sender = Column(Text, nullable=True)

    # Relations 
    email_list_ids = Column(JSON, nullable=True)   # JSON: ["1", "2", ...]
    template_id = Column(String, nullable=True)

    # Status
    status = Column(Enum("draft", "scheduled", "sending", "paused", "completed", "cancelled", name="campaignstatus"), nullable=False, default="draft")

    # Stats 
    sent_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    resend_count = Column(Integer, default=0)

    # Recipients snapshot 
    recipients = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


