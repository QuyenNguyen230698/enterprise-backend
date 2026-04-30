from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger
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

    # Sender — stored as JSON string: { name, email, replyTo, cc, bcc }
    sender = Column(Text, nullable=True)

    # Relations — stored as JSON arrays of IDs (strings)
    email_list_ids = Column(Text, nullable=True)   # JSON: ["1", "2", ...]
    template_id = Column(String, nullable=True)

    # Status: draft | sending | completed | failed
    status = Column(String(20), nullable=False, default="draft")

    # Stats — updated during/after send
    sent_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    resend_count = Column(Integer, default=0)

    # Recipients snapshot — JSON list of { to, sentAt, opened, firstOpenedAt, openCount }
    recipients = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
