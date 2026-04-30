from pydantic import BaseModel, EmailStr
from typing import Optional, Union
from datetime import datetime


class UserCreate(BaseModel):
    portal_user_id: Optional[str] = None
    email: EmailStr
    name: Optional[str] = None
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    hr_code: Optional[str] = None
    e_code: Optional[str] = None
    department: Optional[str] = None
    dept_code: Optional[str] = None
    title: Optional[str] = None
    joined_at: Optional[Union[datetime, str]] = None
    phone: Optional[str] = None
    site: Optional[str] = None
    site_id: Optional[int] = None
    site_country: Optional[str] = None
    admin_meeting_room: bool = False
    is_tenant_admin: bool = False
    google_id: Optional[str] = None
    google_token: Optional[str] = None
    tenant_id: Optional[str] = None
    # Keep optional; backend route decides role_id default for creation flow.
    role: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "portal_user_id": "888",
                "email": "john.doe@company.com",
                "full_name": "John Doe - IT Developer",
                "department": "IT",
                "title": "Application Developer",
                "site": "Head Office"
            }
        }


class UserUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    hr_code: Optional[str] = None
    e_code: Optional[str] = None
    department: Optional[str] = None
    dept_code: Optional[str] = None
    title: Optional[str] = None
    joined_at: Optional[Union[datetime, str]] = None
    phone: Optional[str] = None
    site: Optional[str] = None
    site_id: Optional[int] = None
    site_country: Optional[str] = None
    admin_meeting_room: Optional[bool] = None
    is_tenant_admin: bool = False
    google_id: Optional[str] = None
    google_token: Optional[str] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    last_login_at: Optional[datetime] = None


class UserResponse(UserCreate):
    id: int
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
