from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class EmailConfig(Base):
    """
    Stores per-user SMTP / Gmail configurations.
    Sensitive credentials (password, appPassword) are AES-encrypted at rest.
    """
    __tablename__ = "email_configs"

    id = Column(Integer, primary_key=True, index=True)

    # Owner
    portal_user_id = Column(String, nullable=False, index=True)

    # Display
    name = Column(String(200), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    # Provider: "gmail" | "smtp"
    provider = Column(String(20), nullable=False, default="gmail")

    # Sender identity
    sender_name = Column(String(200), nullable=False)
    sender_email = Column(String(320), nullable=False)
    reply_to = Column(String(320), nullable=True)

    # SMTP fields (provider == "smtp")
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_secure = Column(Boolean, default=False, nullable=True)
    smtp_username = Column(String(320), nullable=True)
    smtp_password_enc = Column(Text, nullable=True)      # AES-encrypted

    # Gmail fields (provider == "gmail")
    gmail_address = Column(String(320), nullable=True)
    gmail_app_password_enc = Column(Text, nullable=True)  # AES-encrypted

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
