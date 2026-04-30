from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class RoomCreate(BaseModel):
    area_id: int
    name: str
    capacity: int = 10
    floor: Optional[int] = None
    facilities: List[str] = []
    available: bool = True
    teams_account_email: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "area_id": 1,
                "name": "Executive Suite A",
                "capacity": 15,
                "floor": 3,
                "facilities": ["Projector", "Whiteboard", "Teams Display"],
                "available": True
            }
        }


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    floor: Optional[int] = None
    facilities: Optional[List[str]] = None
    available: Optional[bool] = None
    teams_account_email: Optional[str] = None


class RoomResponse(RoomCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
