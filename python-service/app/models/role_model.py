from sqlalchemy import Column, String, DateTime, ARRAY
from sqlalchemy.sql import func
from app.db.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    permission_id = Column(String(10), primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)          # e.g. "bookings", "editor"
    description = Column(String, nullable=True)
    app_path     = Column(String, nullable=True)                # e.g. "/bookings", "/settings/email-config"
    app_icon     = Column(String, nullable=True)                # e.g. "bi bi-calendar-check"
    app_group    = Column(String, nullable=True)                # e.g. "admin" | "email" | "system" | "settings"
    parent_name  = Column(String, nullable=True)                # parent appCode nếu là sub-page, null nếu top-level
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(String(10), primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)          # e.g. "superAdmin", "admin"
    description = Column(String, nullable=True)
    # Array of permission_id strings — e.g. ["1234567890", "2345678901"]
    permissions = Column(ARRAY(String), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
