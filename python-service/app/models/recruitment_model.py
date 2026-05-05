from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class RecruitmentJob(Base):
    __tablename__ = "recruitment_jobs"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, index=True)

    title = Column(String(300), nullable=False)
    department = Column(String(200), nullable=True)
    # email alias HR publish cho ứng viên (vd: tuyendung@company.com)
    email_alias = Column(String(320), nullable=True)
    description = Column(Text, nullable=True)

    # open | closed
    status = Column(String(20), nullable=False, default="open")

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CandidateEmail(Base):
    __tablename__ = "candidate_emails"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, index=True)

    job_id = Column(Integer, nullable=True, index=True)

    # Email metadata
    message_id = Column(String(500), nullable=True, unique=True)   # RFC Message-ID header
    from_email = Column(String(320), nullable=False, index=True)
    from_name = Column(String(300), nullable=True)
    subject = Column(String(1000), nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

    # new | reviewing | shortlisted | rejected | replied
    status = Column(String(30), nullable=False, default="new")
    is_read = Column(Boolean, default=False, nullable=False)

    # JSON list of { filename, url } for attached files
    attachments = Column(Text, nullable=True)

    # Group related emails in same conversation
    thread_id = Column(String(500), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RecruitmentReply(Base):
    __tablename__ = "recruitment_replies"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, index=True)

    # Khi reply cho 1 ứng viên cụ thể
    candidate_email_id = Column(Integer, nullable=True, index=True)

    # UUID nhóm các reply cùng 1 bulk batch
    bulk_id = Column(String(100), nullable=True, index=True)

    sent_by = Column(String, nullable=True)
    email_config_id = Column(Integer, nullable=True)
    template_id = Column(Integer, nullable=True)

    to_email = Column(String(320), nullable=False)
    to_name = Column(String(300), nullable=True)
    subject = Column(String(1000), nullable=False)
    body_html = Column(Text, nullable=False)

    # pending | sent | failed
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RecruitmentAutoRule(Base):
    __tablename__ = "recruitment_auto_rules"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, index=True)

    # NULL = áp dụng cho mọi job của user
    job_id = Column(Integer, nullable=True, index=True)

    name = Column(String(300), nullable=False)

    # on_receive — trigger khi nhận email mới vào inbox
    trigger = Column(String(50), nullable=False, default="on_receive")

    # Template dùng để auto-reply (ưu tiên hơn body_html nếu cả hai có)
    template_id = Column(Integer, nullable=True)
    email_config_id = Column(Integer, nullable=True)

    # None → subject tự động: "Re: <subject gốc>" hoặc "Fwd: <subject gốc>"
    reply_subject = Column(String(1000), nullable=True)
    body_html = Column(Text, nullable=True)

    # reply | forward — kiểu gửi, ảnh hưởng subject prefix và có quote nội dung gốc không
    reply_type = Column(String(20), nullable=False, default="reply")

    from_name = Column(String(300), nullable=True)

    # 0 = gửi ngay, >0 = delay N phút
    delay_minutes = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
