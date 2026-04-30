from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    portal_user_id = Column(String, nullable=False, index=True)

    # Meta
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)   # marketing | transactional | newsletter | promotional | announcement

    # Content
    json_data = Column(Text, nullable=True)        # JSON string: { elements, globalSettings, metadata }
    html_snapshot = Column(Text, nullable=True)    # Pre-rendered HTML for quick preview

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
