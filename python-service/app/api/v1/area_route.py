from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.models.area_model import Area, AreaSharedAccess
from app.models.room_model import Room
from app.models.user_model import User
from app.schemas.area_schema import AreaCreate, AreaUpdate, AreaResponse, AreaSharedAccessCreate, AreaSharedAccessResponse
from app.schemas.room_schema import RoomResponse
from typing import List, Optional

router = APIRouter()


async def _resolve_tenant_id(db: AsyncSession, portal_user_id: str) -> str:
    user_result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.tenant_id:
        return f"personal_{portal_user_id}"
    return user.tenant_id


@router.get("/", response_model=List[AreaResponse])
async def list_areas(
    portal_user_id: Optional[str] = Query(None, description="portal_user_id của user đang xem"),
    tenant_id: Optional[str] = Query(None, description="Optional explicit tenant_id filter"),
    db: AsyncSession = Depends(get_db)
):
    resolved_tenant_id = tenant_id
    if not resolved_tenant_id:
        if not portal_user_id:
            raise HTTPException(status_code=400, detail="portal_user_id or tenant_id is required.")
        resolved_tenant_id = await _resolve_tenant_id(db, portal_user_id)
    result = await db.execute(select(Area).where(Area.tenant_id == resolved_tenant_id).order_by(Area.name))
    return result.scalars().all()


@router.post("/", response_model=AreaResponse, status_code=status.HTTP_201_CREATED)
async def create_area(payload: AreaCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Area).where(Area.tenant_id == payload.tenant_id, Area.name == payload.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Area with this name already exists in this tenant.")
    area = Area(**payload.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return area


@router.get("/{area_id}", response_model=AreaResponse)
async def get_area(area_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found.")
    return area


@router.put("/{area_id}", response_model=AreaResponse)
async def update_area(area_id: int, payload: AreaUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(area, key, value)
    await db.commit()
    await db.refresh(area)
    return area


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(area_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found.")
    await db.delete(area)
    await db.commit()


@router.get("/{area_id}/rooms", response_model=List[RoomResponse])
async def list_area_rooms(area_id: int, db: AsyncSession = Depends(get_db)):
    area = await db.execute(select(Area).where(Area.id == area_id))
    if not area.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Area not found.")
    result = await db.execute(select(Room).where(Room.area_id == area_id).order_by(Room.name))
    return result.scalars().all()


# ─── Shared Access ────────────────────────────────────────────────

@router.post("/shared-access", response_model=AreaSharedAccessResponse, status_code=status.HTTP_201_CREATED)
async def create_shared_access(payload: AreaSharedAccessCreate, db: AsyncSession = Depends(get_db)):
    record = AreaSharedAccess(**payload.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
