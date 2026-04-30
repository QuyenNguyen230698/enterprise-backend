from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AssetHandover(Base):
    """
    Biên bản bàn giao tài sản thiết bị — QF-HRA-12.

    Có thể tạo độc lập (standalone) hoặc liên kết với một OffboardingProcess
    thông qua offboarding_id.  Khi status chuyển sang COMPLETED backend tự
    cập nhật ho2_status = CONFIRMED trên offboarding.  Khi REJECTED thì
    ho2_status = REJECTED với note = 'Chưa bàn giao trang thiết bị đầy đủ'.
    """
    __tablename__ = "asset_handovers"

    id = Column(Integer, primary_key=True, index=True)

    # Tham chiếu mã biên bản, sinh sau khi insert
    ref_code = Column(String(40), nullable=True, unique=True, index=True)

    tenant_id = Column(String(100), nullable=True, index=True)
    created_by = Column(String(100), nullable=True, index=True)

    # Liên kết offboarding (nullable — standalone ok)
    offboarding_id = Column(Integer, nullable=True, index=True)
    offboarding_ref = Column(String(40), nullable=True)

    # Thông tin nhân viên bàn giao
    employee_id = Column(String(100), nullable=True, index=True)
    employee_name = Column(String(200), nullable=False)
    employee_code = Column(String(100), nullable=True)
    department = Column(String(200), nullable=True)
    job_title = Column(String(200), nullable=True)

    # Ngày bàn giao và ngày lập biên bản
    handover_date = Column(String(20), nullable=True)
    created_date = Column(String(20), nullable=True)

    # Danh sách tài sản: [{name, serial, condition, note, employee_note}]
    assets = Column(JSON, nullable=False, default=list)

    general_note = Column(Text, nullable=True)

    # Trạng thái: DRAFT → PENDING_EMPLOYEE_SIGN → PENDING_HR_CONFIRM → COMPLETED / REJECTED
    status = Column(String(30), nullable=False, default="DRAFT", index=True)

    # Chữ ký nhân viên
    employee_signed_at = Column(DateTime(timezone=True), nullable=True)
    employee_signature_url = Column(Text, nullable=True)

    # Chữ ký HR
    hr_signer_id = Column(String(100), nullable=True)
    hr_signer_name = Column(String(200), nullable=True)
    hr_signed_at = Column(DateTime(timezone=True), nullable=True)
    hr_signature_url = Column(Text, nullable=True)

    # Ghi chú khi reject
    reject_note = Column(Text, nullable=True)

    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps = relationship(
        "AssetHandoverStep",
        back_populates="handover",
        order_by="AssetHandoverStep.acted_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_asset_handover_tenant_status", "tenant_id", "status"),
        Index("ix_asset_handover_offboarding", "offboarding_id"),
        Index("ix_asset_handover_employee", "employee_id"),
    )


class AssetHandoverStep(Base):
    """Lịch sử thao tác trên biên bản bàn giao tài sản."""
    __tablename__ = "asset_handover_steps"

    id = Column(Integer, primary_key=True, index=True)
    handover_id = Column(
        Integer,
        ForeignKey("asset_handovers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action = Column(String(50), nullable=False)   # send_to_employee | sign | confirm | reject
    actor_id = Column(String(100), nullable=True)
    actor_name = Column(String(200), nullable=True)
    actor_title = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)
    extra = Column(JSON, nullable=False, default=dict)
    acted_at = Column(DateTime(timezone=True), server_default=func.now())

    handover = relationship("AssetHandover", back_populates="steps")
