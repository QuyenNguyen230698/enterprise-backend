from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Area(Base):
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    it_support_emails = Column(String, nullable=True)       # comma-separated
    requires_hr_approval = Column(Boolean, default=False)
    hr_admin_emails = Column(String, nullable=True)
    hr_admin_cc_emails = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    rooms = relationship("Room", back_populates="area", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="area", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_area_tenant_name"),
        Index("ix_areas_tenant_id", "tenant_id"),
    )


class AreaSharedAccess(Base):
    __tablename__ = "area_shared_access"

    id = Column(Integer, primary_key=True, index=True)
    owner_area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    guest_area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("owner_area_id", "guest_area_id", name="uq_area_shared_access"),
    )
