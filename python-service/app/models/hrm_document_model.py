from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class HrmDocument(Base):
    """
    Biên bản vận hành — Document Instance tạo từ HrmDocumentTemplate.
    Mỗi row là một biên bản cụ thể do user điền và nộp lên.
    """
    __tablename__ = "hrm_documents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), nullable=True, index=True)

    # Thông tin từ template
    template_id = Column(Integer, nullable=True, index=True)
    name = Column(String(300), nullable=False)
    code = Column(String(50), nullable=True, index=True)
    doc_type = Column(String(50), nullable=False, default="CUSTOM")
    title_vn = Column(String(300), nullable=True)
    title_en = Column(String(300), nullable=True)

    # Nội dung điền bởi user (snapshot từ template blocks đã được fill)
    content_blocks = Column(JSON, nullable=False, default=list)

    # Cấu hình workflow (snapshot từ template)
    signers = Column(JSON, nullable=False, default=list)
    workflow_steps = Column(JSON, nullable=False, default=list)

    # Trạng thái: DRAFT | PENDING_STEP_2..7 | COMPLETED | REJECTED
    status = Column(String(40), nullable=False, default="DRAFT", index=True)

    # Approval logs: list of {stepNumber, action, actorId, actorName, note, signatureUrl, actionAt, signerRoleKey}
    approval_logs = Column(JSON, nullable=False, default=list)

    # Người tạo
    submitted_by = Column(String(100), nullable=True, index=True)   # portal_user_id
    submitted_by_name = Column(String(200), nullable=True)
    submitted_by_title = Column(String(200), nullable=True)
    submitted_by_dept = Column(String(200), nullable=True)

    # Ghi chú khi tạo
    note = Column(Text, nullable=True)

    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
