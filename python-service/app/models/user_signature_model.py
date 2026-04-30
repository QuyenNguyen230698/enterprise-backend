from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class UserSignature(Base):
    __tablename__ = "user_signatures"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, unique=True, index=True)
    signature_type = Column(String(20), nullable=False, default="drawn")
    signature_image_url = Column(String, nullable=True)
    signature_data = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
