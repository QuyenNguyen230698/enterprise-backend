from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ─── Tenant ──────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── TenantAdmin ─────────────────────────────────────────────────────

class TenantAdminCreate(BaseModel):
    tenant_id: str
    portal_user_id: str
    is_super_admin: bool = False
    is_active: bool = True


class TenantAdminUpdate(BaseModel):
    is_super_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class TenantAdminResponse(TenantAdminCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Tenant with its admins ───────────────────────────────────────────

class TenantDetailResponse(TenantResponse):
    admins: List[TenantAdminResponse] = []
