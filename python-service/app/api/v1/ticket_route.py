"""
ticket_route.py — Internal API (node-gateway ↔ python-service)
PostgreSQL là source of truth cho tất cả ticket data.

Endpoint prefix: /api/v1  (mount trong main.py)
Thực tế path: /api/v1/internal/tickets/...
"""
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.ticket_model import Ticket, TicketComment

router = APIRouter()

ROLE_SUPER   = "2000000001"
ROLE_ADMIN   = "2000000002"
ROLE_MEMBER  = "2000000003"
GUEST_TENANT = "__guest__"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _gen_ticket_number(tenant_id: str, seq: int) -> str:
    prefix = "G" if tenant_id == GUEST_TENANT else "T"
    return f"{prefix}-{seq:04d}"


def _gen_guest_display_name() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"Guest_T{suffix}"


def _comment_to_dict(c: TicketComment) -> dict:
    return {
        "id":           c.id,
        "ticketId":     c.ticket_id,
        "userId":       c.user_id,
        "userName":     c.user_name,
        "isAdmin":      c.is_admin,
        "isSuperAdmin": c.is_super_admin,
        "message":      c.message,
        "attachments":  c.attachments or [],
        "createdAt":    c.created_at.isoformat() if c.created_at else None,
    }


def _ticket_to_dict(t: Ticket) -> dict:
    return {
        "id":               t.id,
        "ticketNumber":     t.ticket_number,
        "tenantId":         t.tenant_id,
        "userId":           t.user_id,
        "userEmail":        t.user_email,
        "userName":         t.user_name,
        "guestDisplayName": t.guest_display_name,
        "createdByRole":    t.created_by_role,
        "source":           t.source,
        "subject":          t.subject,
        "description":      t.description,
        "category":         t.category,
        "priority":         t.priority,
        "contactEmail":     t.contact_email,
        "emailNotification": t.email_notification,
        "attachments":      t.attachments or [],
        "status":           t.status,
        "resolution":       t.resolution,
        "resolvedAt":       t.resolved_at.isoformat() if t.resolved_at else None,
        "assignedTo":       t.assigned_to,
        "assignedToName":   t.assigned_to_name,
        "assignedAt":       t.assigned_at.isoformat() if t.assigned_at else None,
        "isLocked":         t.is_locked,
        "comments":         [_comment_to_dict(c) for c in (t.comments or [])],
        "createdAt":        t.created_at.isoformat() if t.created_at else None,
        "updatedAt":        t.updated_at.isoformat() if t.updated_at else None,
    }


async def _next_seq(db: AsyncSession, tenant_id: str) -> int:
    result = await db.execute(
        select(sa_func.count()).select_from(Ticket).where(Ticket.tenant_id == tenant_id)
    )
    return (result.scalar() or 0) + 1


# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    tenant_id:          str
    user_id:            Optional[str]       = None
    user_email:         Optional[str]       = None
    user_name:          Optional[str]       = None
    guest_display_name: Optional[str]       = None
    created_by_role:    Optional[str]       = None
    source:             Optional[str]       = "direct"
    subject:            str
    description:        str
    category:           Optional[str]       = "other"
    priority:           Optional[str]       = "medium"
    contact_email:      Optional[str]       = None
    email_notification: Optional[bool]      = False
    attachments:        Optional[List[Any]] = []
    status:             Optional[str]       = "open"


class CommentCreate(BaseModel):
    user_id:        Optional[str]       = None
    user_name:      Optional[str]       = None
    is_admin:       Optional[bool]      = False
    is_super_admin: Optional[bool]      = False
    message:        str
    attachments:    Optional[List[Any]] = []


class StatusUpdate(BaseModel):
    status:     str
    resolution: Optional[str] = None


class PriorityUpdate(BaseModel):
    priority: str


class ClaimRequest(BaseModel):
    user_id:   str
    user_name: str


class UnlockRequest(BaseModel):
    clear_assigned: Optional[bool] = True


class ResolutionUpdate(BaseModel):
    resolution: str


# ─── Tạo ticket ───────────────────────────────────────────────────────────────
@router.post("/internal/tickets", status_code=201)
async def create_ticket(data: TicketCreate, db: AsyncSession = Depends(get_db)):
    seq   = await _next_seq(db, data.tenant_id)
    t_num = _gen_ticket_number(data.tenant_id, seq)

    guest_name = data.guest_display_name
    if data.source == "contact_form" and not guest_name:
        guest_name = _gen_guest_display_name()

    ticket = Ticket(
        ticket_number      = t_num,
        tenant_id          = data.tenant_id,
        user_id            = data.user_id,
        user_email         = data.user_email,
        user_name          = data.user_name,
        guest_display_name = guest_name,
        created_by_role    = data.created_by_role,
        source             = data.source or "direct",
        subject            = data.subject,
        description        = data.description,
        category           = data.category or "other",
        priority           = data.priority or "medium",
        contact_email      = data.contact_email,
        email_notification = data.email_notification or False,
        attachments        = data.attachments or [],
        status             = data.status or "open",
        is_locked          = False,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Danh sách ticket ─────────────────────────────────────────────────────────
@router.get("/internal/tickets")
async def list_tickets(
    tenant_id:    Optional[str] = None,
    user_id:      Optional[str] = None,
    role:         Optional[str] = None,
    all_tenants:  bool = False,
    contact_only: bool = False,
    status:       Optional[str] = None,
    category:     Optional[str] = None,
    priority:     Optional[str] = None,
    search:       Optional[str] = None,
    sort:         str = "-created_at",
    page:         int = Query(1, ge=1),
    limit:        int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ticket)

    if contact_only:
        stmt = stmt.where(Ticket.tenant_id == GUEST_TENANT)
    elif all_tenants:
        pass  # superAdmin thấy tất cả tenant kể cả __guest__
    elif tenant_id:
        stmt = stmt.where(Ticket.tenant_id == tenant_id)

    # Scope theo role
    if role == ROLE_ADMIN and tenant_id and not all_tenants and not contact_only:
        stmt = stmt.where(
            or_(
                Ticket.user_id == user_id,
                and_(Ticket.tenant_id == tenant_id, Ticket.created_by_role == ROLE_MEMBER),
            )
        )
    elif role == ROLE_MEMBER and user_id:
        stmt = stmt.where(Ticket.user_id == user_id)

    if status and status != "all":
        stmt = stmt.where(Ticket.status == status)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            or_(Ticket.subject.ilike(q), Ticket.description.ilike(q), Ticket.ticket_number.ilike(q))
        )

    count_stmt = select(sa_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    if sort == "created_at":
        stmt = stmt.order_by(Ticket.created_at.asc())
    elif sort == "-priority":
        prio_order = case(
            {"urgent": 4, "high": 3, "medium": 2, "low": 1},
            value=Ticket.priority,
            else_=0,
        )
        stmt = stmt.order_by(prio_order.desc(), Ticket.created_at.desc())
    else:
        stmt = stmt.order_by(Ticket.created_at.desc())

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    tickets = (await db.execute(stmt)).scalars().all()

    return {
        "success": True,
        "data": [_ticket_to_dict(t) for t in tickets],
        "pagination": {
            "page": page, "limit": limit,
            "total": total, "pages": max(1, -(-total // limit)),
        },
    }


# ─── Stats ────────────────────────────────────────────────────────────────────
@router.get("/internal/tickets/stats")
async def ticket_stats(
    tenant_id:    Optional[str] = None,
    user_id:      Optional[str] = None,
    role:         Optional[str] = None,
    all_tenants:  bool = False,
    contact_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ticket.status, sa_func.count().label("cnt"))

    if contact_only:
        stmt = stmt.where(Ticket.tenant_id == GUEST_TENANT)
    elif all_tenants:
        pass  # superAdmin thấy tất cả kể cả __guest__
    elif tenant_id:
        stmt = stmt.where(Ticket.tenant_id == tenant_id)

    if role == ROLE_ADMIN and tenant_id and not all_tenants and not contact_only:
        stmt = stmt.where(
            or_(
                Ticket.user_id == user_id,
                and_(Ticket.tenant_id == tenant_id, Ticket.created_by_role == ROLE_MEMBER),
            )
        )
    elif role == ROLE_MEMBER and user_id:
        stmt = stmt.where(Ticket.user_id == user_id)

    stmt = stmt.group_by(Ticket.status)
    rows = (await db.execute(stmt)).all()

    stats = {"open": 0, "in_progress": 0, "waiting": 0, "resolved": 0, "closed": 0, "total": 0}
    for s, cnt in rows:
        if s in stats:
            stats[s] = cnt
        stats["total"] += cnt
    return {"success": True, "data": stats}


# ─── Chi tiết ticket ──────────────────────────────────────────────────────────
@router.get("/internal/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Claim ticket — chỉ người đầu tiên thành công ────────────────────────────
@router.put("/internal/tickets/{ticket_id}/claim")
async def claim_ticket(ticket_id: int, body: ClaimRequest, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Ticket đã đóng")
    if ticket.is_locked:
        raise HTTPException(status_code=423, detail="Ticket đang bị khóa, chỉ superAdmin mới can thiệp được")

    if ticket.assigned_to and ticket.assigned_to != body.user_id:
        raise HTTPException(
            status_code=409,
            detail=f"Ticket đã được {ticket.assigned_to_name} nhận xử lý",
        )
    if ticket.assigned_to == body.user_id:
        return {"success": True, "data": _ticket_to_dict(ticket), "alreadyOwner": True}

    ticket.assigned_to      = body.user_id
    ticket.assigned_to_name = body.user_name
    ticket.assigned_at      = datetime.now(timezone.utc)
    if ticket.status == "open":
        ticket.status = "in_progress"

    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Unlock ticket — chỉ superAdmin gọi ──────────────────────────────────────
@router.put("/internal/tickets/{ticket_id}/unlock")
async def unlock_ticket(ticket_id: int, body: UnlockRequest, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")

    if body.clear_assigned:
        ticket.assigned_to      = None
        ticket.assigned_to_name = None
        ticket.assigned_at      = None
        if ticket.status == "in_progress":
            ticket.status = "open"

    ticket.is_locked = False
    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Lock ticket — chỉ superAdmin gọi ────────────────────────────────────────
@router.put("/internal/tickets/{ticket_id}/lock")
async def lock_ticket(ticket_id: int, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    ticket.is_locked = True
    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Cập nhật status ──────────────────────────────────────────────────────────
@router.put("/internal/tickets/{ticket_id}/status")
async def update_status(ticket_id: int, body: StatusUpdate, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    if body.status not in {"open", "in_progress", "waiting", "resolved", "closed"}:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")

    ticket.status = body.status
    if body.resolution is not None:
        ticket.resolution = body.resolution
        ticket.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Cập nhật priority ────────────────────────────────────────────────────────
@router.put("/internal/tickets/{ticket_id}/priority")
async def update_priority(ticket_id: int, body: PriorityUpdate, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    if body.priority not in {"low", "medium", "high", "urgent"}:
        raise HTTPException(status_code=400, detail="Mức độ không hợp lệ")

    ticket.priority = body.priority
    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Lưu resolution ───────────────────────────────────────────────────────────
@router.put("/internal/tickets/{ticket_id}/resolution")
async def save_resolution(ticket_id: int, body: ResolutionUpdate, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    ticket.resolution = body.resolution
    await db.commit()
    await db.refresh(ticket)
    return {"success": True, "data": _ticket_to_dict(ticket)}


# ─── Thêm comment ─────────────────────────────────────────────────────────────
@router.post("/internal/tickets/{ticket_id}/comments", status_code=201)
async def add_comment(ticket_id: int, body: CommentCreate, db: AsyncSession = Depends(get_db)):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket không tồn tại")
    if ticket.status == "closed":
        raise HTTPException(status_code=400, detail="Ticket đã đóng")

    comment = TicketComment(
        ticket_id      = ticket_id,
        user_id        = body.user_id,
        user_name      = body.user_name,
        is_admin       = body.is_admin or False,
        is_super_admin = body.is_super_admin or False,
        message        = body.message,
        attachments    = body.attachments or [],
    )
    db.add(comment)

    if (body.is_admin or body.is_super_admin) and ticket.status == "open":
        ticket.status = "in_progress"

    await db.commit()
    await db.refresh(comment)
    return {"success": True, "data": _comment_to_dict(comment)}


# ─── Xóa comment ──────────────────────────────────────────────────────────────
@router.delete("/internal/tickets/{ticket_id}/comments/{comment_id}")
async def delete_comment(ticket_id: int, comment_id: int, db: AsyncSession = Depends(get_db)):
    comment = (
        await db.execute(
            select(TicketComment).where(
                TicketComment.id == comment_id,
                TicketComment.ticket_id == ticket_id,
            )
        )
    ).scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment không tồn tại")
    await db.delete(comment)
    await db.commit()
    return {"success": True}


# ─── Danh sách comments ───────────────────────────────────────────────────────
@router.get("/internal/tickets/{ticket_id}/comments")
async def list_comments(ticket_id: int, db: AsyncSession = Depends(get_db)):
    comments = (
        await db.execute(
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at)
        )
    ).scalars().all()
    return {"success": True, "data": [_comment_to_dict(c) for c in comments]}
