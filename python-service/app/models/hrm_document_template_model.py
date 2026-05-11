from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class HrmDocumentTemplate(Base):
    __tablename__ = "hrm_document_templates"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), nullable=True, index=True)

    name = Column(String(300), nullable=False)
    code = Column(String(50), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False, default="CUSTOM")
    title_vn = Column(String(300), nullable=True)
    title_en = Column(String(300), nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)

    content_blocks = Column(JSON, nullable=False, default=list)
    signers = Column(JSON, nullable=False, default=list)
    workflow_steps = Column(JSON, nullable=False, default=list)

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
