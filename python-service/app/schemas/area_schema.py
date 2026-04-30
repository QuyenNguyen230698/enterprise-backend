from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AreaCreate(BaseModel):
    tenant_id: str
    name: str
    city: Optional[str] = None
    address: Optional[str] = None
    active: bool = True
    it_support_emails: Optional[str] = None
    requires_hr_approval: bool = False
    hr_admin_emails: Optional[str] = None
    hr_admin_cc_emails: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Head Office HCM",
                "city": "Ho Chi Minh",
                "address": "123 Nguyen Hue, D1",
                "active": True,
                "requires_hr_approval": False,
                "it_support_emails": "quyen.nc.dev@gmail.com"
            }
        }


class AreaUpdate(AreaCreate):
    tenant_id: Optional[str] = None
    name: Optional[str] = None


class AreaResponse(AreaCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AreaSharedAccessCreate(BaseModel):
    owner_area_id: int
    guest_area_id: int


class AreaSharedAccessResponse(AreaSharedAccessCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
