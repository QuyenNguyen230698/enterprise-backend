from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class SignatureOtp(Base):
    __tablename__ = "signature_otp_verifications"

    id = Column(Integer, primary_key=True, index=True)
    portal_user_id = Column(String, nullable=False, index=True)
    otp_hash = Column(String(64), nullable=False)          # SHA-256(otp_code)
    attempts = Column(Integer, default=0, nullable=False)  # max 5
    verified = Column(Boolean, default=False, nullable=False)
    verify_token = Column(String(64), nullable=True)       # HMAC token issued after verify
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
