from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sql_func, update
from pydantic import BaseModel

from app.db.database import get_db
from app.models.notification_model import Notification

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────

class NotificationCreate(BaseModel):
    tenant_id: str
    user_id: str
    title: str
    message: str
    type: Optional[str] = "info"
    link: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────

def _to_response(n: Notification) -> dict:
    return {
        "_id": n.id,
        "tenantId": n.tenant_id,
        "userId": n.user_id,
        "title": n.title,
        "message": n.message,
        "type": n.type,
        "isRead": n.is_read,
        "link": n.link,
        "createdAt": n.created_at.isoformat() if n.created_at else None,
        "updatedAt": n.updated_at.isoformat() if n.updated_at else None,
    }


# ─── Endpoints ────────────────────────────────────────────────────

@router.get("/notifications/unread-count")
async def get_unread_count(
    portal_user_id: str = Query(...),
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Đếm số notification chưa đọc của user."""
    result = await db.execute(
        select(sql_func.count()).select_from(Notification).where(
            Notification.user_id == portal_user_id,
            Notification.tenant_id == tenant_id,
            Notification.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"success": True, "data": {"count": count}}


@router.get("/notifications")
async def list_notifications(
    portal_user_id: str = Query(...),
    tenant_id: str = Query(...),
    unreadOnly: Optional[bool] = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Lấy danh sách notifications với phân trang."""
    stmt = select(Notification).where(
        Notification.user_id == portal_user_id,
        Notification.tenant_id == tenant_id,
    )

    if unreadOnly:
        stmt = stmt.where(Notification.is_read == False)

    stmt = stmt.order_by(Notification.created_at.desc())

    # Count total
    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    notifications = result.scalars().all()

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "success": True,
        "data": [_to_response(n) for n in notifications],
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        },
    }


@router.put("/notifications/read-all")
async def mark_all_read(
    portal_user_id: str = Query(...),
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Đánh dấu tất cả notifications là đã đọc."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == portal_user_id,
            Notification.tenant_id == tenant_id,
            Notification.is_read == False,
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"success": True}


@router.put("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: int,
    portal_user_id: str = Query(...),
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Đánh dấu một notification là đã đọc."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == portal_user_id,
            Notification.tenant_id == tenant_id,
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Không tìm thấy notification")

    n.is_read = True
    await db.commit()
    return {"success": True}


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: int,
    portal_user_id: str = Query(...),
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Xóa một notification."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == portal_user_id,
            Notification.tenant_id == tenant_id,
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Không tìm thấy notification")

    await db.delete(n)
    await db.commit()
    return {"success": True}


@router.post("/notifications", status_code=201)
async def create_notification(
    data: NotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Tạo notification mới (internal use — gọi từ service khác)."""
    n = Notification(
        tenant_id=data.tenant_id,
        user_id=data.user_id,
        title=data.title,
        message=data.message,
        type=data.type,
        link=data.link,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return {"success": True, "data": _to_response(n)}
