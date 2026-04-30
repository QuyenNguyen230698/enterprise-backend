from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class TenantAdmin(Base):
    """
    Maps portal users to tenants.
    is_super_admin=True  → portal_super_admin (quản lý toàn bộ hệ thống)
    is_super_admin=False → tenant_admin (quản lý 1 doanh nghiệp)
    """
    __tablename__ = "tenant_admins"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    portal_user_id = Column(String, nullable=False, index=True)
    is_super_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "portal_user_id", name="uq_tenant_admin"),
    )
