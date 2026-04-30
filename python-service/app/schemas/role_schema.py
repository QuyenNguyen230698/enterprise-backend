from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# ─── Permission ───────────────────────────────────────────────────

class PermissionCreate(BaseModel):
    permission_id: Optional[str] = None   # auto-generated if omitted
    name: str
    description: Optional[str] = None
    app_path: Optional[str] = None        # e.g. "/bookings"
    app_icon: Optional[str] = None        # e.g. "bi bi-calendar-check"
    app_group: Optional[str] = None       # "admin" | "email" | "system" | "settings"
    parent_name: Optional[str] = None     # appCode của parent nếu là sub-page


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    app_path: Optional[str] = None
    app_icon: Optional[str] = None
    app_group: Optional[str] = None
    parent_name: Optional[str] = None


class PermissionResponse(BaseModel):
    permission_id: str
    name: str
    description: Optional[str] = None
    app_path: Optional[str] = None
    app_icon: Optional[str] = None
    app_group: Optional[str] = None
    parent_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Role ────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    role_id: Optional[str] = None         # auto-generated if omitted
    name: str
    description: Optional[str] = None
    permissions: List[str] = []           # list of permission_id


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RoleResponse(BaseModel):
    role_id: str
    name: str
    description: Optional[str] = None
    permissions: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleDetailResponse(RoleResponse):
    """Role với danh sách Permission objects đầy đủ."""
    permission_objects: List[PermissionResponse] = []
