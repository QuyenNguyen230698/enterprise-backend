from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    hr_code = Column(String, nullable=True)
    e_code = Column(String, unique=True, nullable=True, index=True)
    department = Column(String, nullable=True)
    dept_code = Column(String, nullable=True)
    title = Column(String, nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    phone = Column(String, nullable=True)
    site = Column(String, nullable=True)
    site_id = Column(Integer, nullable=True)
    site_country = Column(String, nullable=True)
    admin_meeting_room = Column(Boolean, default=False)
    google_id = Column(String, unique=True, nullable=True, index=True)
    google_token = Column(String, nullable=True)
    tenant_id = Column(String, nullable=True, index=True)
    # Lưu role_id từ bảng roles (default = role_id của "member" = "2000000003")
    role = Column(String, default="2000000003")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    @property
    def is_tenant_admin(self) -> bool:
        return bool(self.admin_meeting_room)

    @is_tenant_admin.setter
    def is_tenant_admin(self, value: bool) -> None:
        self.admin_meeting_room = bool(value)
