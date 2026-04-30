import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class OffboardingProcess(Base):
    __tablename__ = "offboarding_processes"

    id = Column(Integer, primary_key=True, index=True)
    application_ref = Column(String(30), nullable=False, unique=True, index=True)

    # Employee info
    tenant_id = Column(String(100), nullable=True, index=True)
    employee_id = Column(String(100), nullable=False, index=True)
    employee_name = Column(String(200), nullable=False)
    employee_code = Column(String(100), nullable=True)
    department = Column(String(200), nullable=True)
    dept_code = Column(String(100), nullable=True)
    job_title = Column(String(200), nullable=True)
    joining_date = Column(String(20), nullable=True)

    # Resignation details
    resignation_date = Column(String(20), nullable=False)
    last_working_day = Column(String(20), nullable=True)
    contract_type = Column(String(20), nullable=False, default="DEFINITE")
    reason_for_resignation = Column(Text, nullable=False, default="")
    commitment_accepted = Column(Boolean, nullable=False, default=False)

    # Process state
    status = Column(String(30), nullable=False, default="PENDING_MANAGER", index=True)
    payment_date = Column(String(20), nullable=True)

    # Handover checklist (ho1/ho2/ho3 stored as JSON object)
    handover = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    steps = relationship(
        "OffboardingStep",
        back_populates="process",
        order_by="OffboardingStep.acted_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_offboarding_tenant_status", "tenant_id", "status"),
        Index("ix_offboarding_employee", "employee_id"),
    )


class OffboardingStep(Base):
    __tablename__ = "offboarding_steps"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(Integer, ForeignKey("offboarding_processes.id", ondelete="CASCADE"), nullable=False, index=True)

    step_number = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)
    actor_id = Column(String(100), nullable=True)
    actor_name = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)
    extra = Column(JSON, nullable=False, default=dict)
    acted_at = Column(DateTime(timezone=True), server_default=func.now())

    process = relationship("OffboardingProcess", back_populates="steps")
