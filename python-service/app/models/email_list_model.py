from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class EmailList(Base):
    __tablename__ = "email_lists"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    portal_user_id = Column(String, nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subscribers = relationship("Subscriber", back_populates="email_list", cascade="all, delete-orphan")


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)

    list_id = Column(Integer, ForeignKey("email_lists.id", ondelete="CASCADE"), nullable=False, index=True)

    email = Column(String(320), nullable=False)
    name = Column(String(200), nullable=True)
    # Extra fields stored as JSON string: { phone, company, ... }
    custom_fields = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    email_list = relationship("EmailList", back_populates="subscribers")
