from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class JobHandover(Base):
    """
    Biên bản bàn giao công việc — QF-HRA-17.

    Luồng: DRAFT → PENDING_EMPLOYEE_SIGN → PENDING_HR_CONFIRM → COMPLETED / REJECTED
    """
    __tablename__ = "job_handovers"

    id = Column(Integer, primary_key=True, index=True)
    ref_code = Column(String(40), nullable=True, unique=True, index=True)

    tenant_id = Column(String(100), nullable=True, index=True)
    created_by = Column(String(100), nullable=True, index=True)

    employee_id = Column(String(100), nullable=True, index=True)
    employee_name = Column(String(200), nullable=False)
    employee_code = Column(String(100), nullable=True)
    department = Column(String(200), nullable=True)
    job_title = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)

    last_working_day = Column(String(20), nullable=True)
    created_date = Column(String(20), nullable=True)

    reason_resign = Column(String(5), nullable=False, default="false")
    reason_transfer = Column(String(5), nullable=False, default="false")
    reason_other = Column(String(5), nullable=False, default="false")

    # content: {jobRows, docRows, accessRows}
    content = Column(JSON, nullable=False, default=dict)

    status = Column(String(30), nullable=False, default="DRAFT", index=True)

    employee_signed_at = Column(DateTime(timezone=True), nullable=True)
    employee_signature_url = Column(Text, nullable=True)

    hr_signer_id = Column(String(100), nullable=True)
    hr_signer_name = Column(String(200), nullable=True)
    hr_signed_at = Column(DateTime(timezone=True), nullable=True)
    hr_signature_url = Column(Text, nullable=True)

    reject_note = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps = relationship(
        "JobHandoverStep",
        back_populates="handover",
        order_by="JobHandoverStep.acted_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_job_handover_tenant_status", "tenant_id", "status"),
        Index("ix_job_handover_employee", "employee_id"),
        Index("ix_job_handover_created_by", "created_by"),
    )


class JobHandoverStep(Base):
    __tablename__ = "job_handover_steps"

    id = Column(Integer, primary_key=True, index=True)
    handover_id = Column(
        Integer,
        ForeignKey("job_handovers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(50), nullable=False)
    actor_id = Column(String(100), nullable=True)
    actor_name = Column(String(200), nullable=True)
    actor_title = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)
    extra = Column(JSON, nullable=False, default=dict)
    acted_at = Column(DateTime(timezone=True), server_default=func.now())

    handover = relationship("JobHandover", back_populates="steps")
