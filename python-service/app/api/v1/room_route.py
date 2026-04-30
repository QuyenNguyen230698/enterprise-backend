from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from app.db.database import get_db
from app.models.room_model import Room
from app.models.area_model import Area
from app.models.user_model import User
from app.schemas.room_schema import RoomCreate, RoomUpdate, RoomResponse

router = APIRouter()


async def _resolve_tenant_id(db: AsyncSession, portal_user_id: str) -> str:
    user_result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.tenant_id:
        return f"personal_{portal_user_id}"
    return user.tenant_id


@router.get("/", response_model=List[RoomResponse])
async def list_rooms(
    portal_user_id: str = Query(..., description="portal_user_id của user đang xem"),
    area_id: Optional[int] = Query(None, description="Filter by area ID"),
    available: Optional[bool] = Query(None, description="Filter by availability"),
    db: AsyncSession = Depends(get_db)
):
    """List rooms belonging to the user's tenant (filtered via area.tenant_id)."""
    tenant_id = await _resolve_tenant_id(db, portal_user_id)

    query = (
        select(Room)
        .join(Area, Room.area_id == Area.id)
        .where(Area.tenant_id == tenant_id)
    )
    if area_id is not None:
        query = query.where(Room.area_id == area_id)
    if available is not None:
        query = query.where(Room.available == available)
    result = await db.execute(query.order_by(Room.name))
    return result.scalars().all()


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(payload: RoomCreate, db: AsyncSession = Depends(get_db)):
    room = Room(**payload.model_dump())
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    return room


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(room_id: int, payload: RoomUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, key, value)
    await db.commit()
    await db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    await db.delete(room)
    await db.commit()
