from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)   # portal_user_id của người nhận

    # Content
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="info")
    # ticket_new | ticket_reply | ticket_status | ticket_resolved
    # system | broadcast | info | warning | success | error

    # State
    is_read = Column(Boolean, default=False, nullable=False)
    link = Column(String(500), nullable=True)   # route điều hướng, vd: /support/123

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
