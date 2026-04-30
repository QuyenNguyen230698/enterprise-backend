from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, ARRAY, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    capacity = Column(Integer, default=10)
    floor = Column(Integer, nullable=True)
    facilities = Column(ARRAY(String), default=[])
    available = Column(Boolean, default=True)
    teams_account_email = Column(String, nullable=True)  # vd: "room-a01@company.com"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    area = relationship("Area", back_populates="rooms")
    meetings = relationship("Meeting", back_populates="room", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("area_id", "name", name="uq_room_area_name"),
    )
