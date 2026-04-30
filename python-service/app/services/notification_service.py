"""
Notification Service — tạo notification và push real-time qua Socket.io.

Dùng trong các service khác (campaign, meeting, ticket...) để tạo notification:

    from app.services.notification_service import create_notification

    await create_notification(
        db=db,
        tenant_id="tenant_abc",
        user_id="portal_user_123",
        title="Campaign đã gửi",
        message="Campaign 'Summer Sale' đã gửi thành công tới 500 người.",
        type="success",
        link="/campaigns/42",
    )
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_model import Notification


VALID_TYPES = {
    "ticket_new", "ticket_reply", "ticket_status", "ticket_resolved",
    "system", "broadcast", "info", "warning", "success", "error",
}


async def create_notification(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    title: str,
    message: str,
    type: str = "info",
    link: Optional[str] = None,
) -> Notification:
    """Tạo một notification trong DB và trả về object vừa tạo."""
    if type not in VALID_TYPES:
        type = "info"

    n = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def create_broadcast_notification(
    db: AsyncSession,
    tenant_id: str,
    user_ids: list[str],
    title: str,
    message: str,
    type: str = "broadcast",
    link: Optional[str] = None,
) -> list[Notification]:
    """Tạo notification cho nhiều user cùng lúc (broadcast trong tenant)."""
    if type not in VALID_TYPES:
        type = "broadcast"

    notifications = [
        Notification(
            tenant_id=tenant_id,
            user_id=uid,
            title=title,
            message=message,
            type=type,
            link=link,
        )
        for uid in user_ids
    ]
    db.add_all(notifications)
    await db.commit()
    for n in notifications:
        await db.refresh(n)
    return notifications
