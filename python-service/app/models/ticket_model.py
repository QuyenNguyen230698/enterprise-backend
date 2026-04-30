from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)

    # Định danh
    ticket_number = Column(String(20), nullable=False, index=True)

    # Phân quyền / phân loại
    tenant_id       = Column(String(100), nullable=False, index=True)
    user_id         = Column(String(100), nullable=True,  index=True)
    user_email      = Column(String(200), nullable=True)
    user_name       = Column(String(200), nullable=True)
    created_by_role = Column(String(50),  nullable=True)   # guest | 2000000001-3
    source          = Column(String(50),  nullable=False, default="direct")  # direct | contact_form

    # Guest display name — chỉ dùng khi source=contact_form
    # Format: Guest_T{6 ký tự ngẫu nhiên}, VD: Guest_T7KX2M
    guest_display_name = Column(String(100), nullable=True)

    # Nội dung
    subject            = Column(String(500), nullable=False)
    description        = Column(Text,        nullable=False)
    category           = Column(String(50),  nullable=False, default="other")
    priority           = Column(String(20),  nullable=False, default="medium")
    contact_email      = Column(String(200), nullable=True)
    email_notification = Column(Boolean,     default=False)
    attachments        = Column(JSON,        nullable=False, default=list)

    # Trạng thái
    status      = Column(String(30), nullable=False, default="open", index=True)
    resolution  = Column(Text,       nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Người nhận xử lý — khóa cạnh tranh:
    #   người đầu tiên claim = giữ quyền xử lý xuyên suốt đến khi đóng.
    #   Người sau không thể claim; chỉ superAdmin mới override (unlock rồi claim lại).
    assigned_to      = Column(String(100), nullable=True, index=True)
    assigned_to_name = Column(String(200), nullable=True)
    assigned_at      = Column(DateTime(timezone=True), nullable=True)

    # Khi is_locked=True: chỉ superAdmin can thiệp được (override assigned_to)
    is_locked = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    comments = relationship(
        "TicketComment",
        back_populates="ticket",
        order_by="TicketComment.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_tenant_user",   "tenant_id", "user_id"),
    )


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id        = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    user_id        = Column(String(100), nullable=True)
    user_name      = Column(String(200), nullable=True)
    is_admin       = Column(Boolean, default=False)
    is_super_admin = Column(Boolean, default=False)
    message        = Column(Text, nullable=False)
    attachments    = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="comments")
