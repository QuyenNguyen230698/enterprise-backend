from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func

from app.db.base import Base


class DocumentApprovalLog(Base):
    __tablename__ = "document_approval_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=True, index=True)
    document_type = Column(String(50), nullable=False, index=True)  # e.g. OFFBOARDING
    document_id = Column(String(64), nullable=False, index=True)
    document_ref = Column(String(120), nullable=True, index=True)
    source_module = Column(String(80), nullable=False, default="sign-hub")
    step_number = Column(Integer, nullable=True)
    action = Column(String(40), nullable=False, index=True)
    status_after = Column(String(40), nullable=True, index=True)
    actor_id = Column(String, nullable=True, index=True)
    actor_name = Column(String, nullable=True)
    actor_title = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    extra = Column(JSON, nullable=True)
    acted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
