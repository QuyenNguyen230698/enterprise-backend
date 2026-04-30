import csv
import io
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sql_func, delete
from pydantic import BaseModel, EmailStr

from app.db.database import get_db
from app.models.email_list_model import EmailList, Subscriber

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────

class EmailListCreate(BaseModel):
    name: str
    description: Optional[str] = None


class EmailListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SubscriberCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    custom_fields: Optional[dict] = None


class SubscriberUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    custom_fields: Optional[dict] = None


class BulkSubscriber(BaseModel):
    email: str
    name: Optional[str] = None


class BulkImportRequest(BaseModel):
    subscribers: List[BulkSubscriber]


class BulkDeleteRequest(BaseModel):
    ids: List[int]


# ─── Helpers ──────────────────────────────────────────────────────

def _list_to_response(el: EmailList, subscriber_count: int = 0) -> dict:
    return {
        "_id": el.id,
        "name": el.name,
        "description": el.description,
        "subscriberCount": subscriber_count,
        "createdAt": el.created_at.isoformat() if el.created_at else None,
        "updatedAt": el.updated_at.isoformat() if el.updated_at else None,
    }


def _subscriber_to_response(s: Subscriber) -> dict:
    custom = None
    if s.custom_fields:
        try:
            custom = json.loads(s.custom_fields)
        except Exception:
            custom = None
    return {
        "_id": s.id,
        "email": s.email,
        "name": s.name,
        "customFields": custom,
        "createdAt": s.created_at.isoformat() if s.created_at else None,
        "updatedAt": s.updated_at.isoformat() if s.updated_at else None,
    }


async def _get_list_or_404(list_id: int, portal_user_id: str, db: AsyncSession) -> EmailList:
    result = await db.execute(
        select(EmailList).where(
            EmailList.id == list_id,
            EmailList.portal_user_id == portal_user_id,
            EmailList.is_active == True,
        )
    )
    el = result.scalar_one_or_none()
    if not el:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh sách email")
    return el


# ─── Email List Endpoints ──────────────────────────────────────────

@router.get("/email-lists")
async def list_email_lists(
    portal_user_id: str = Query(...),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách email lists của user với số lượng subscriber."""
    stmt = select(EmailList).where(
        EmailList.portal_user_id == portal_user_id,
        EmailList.is_active == True,
    )
    if search:
        stmt = stmt.where(EmailList.name.ilike(f"%{search}%"))

    stmt = stmt.order_by(EmailList.created_at.desc())

    # Count total
    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    lists = result.scalars().all()

    # Get subscriber counts in one query
    list_ids = [el.id for el in lists]
    counts = {}
    if list_ids:
        count_result = await db.execute(
            select(Subscriber.list_id, sql_func.count(Subscriber.id))
            .where(Subscriber.list_id.in_(list_ids), Subscriber.is_active == True)
            .group_by(Subscriber.list_id)
        )
        counts = {row[0]: row[1] for row in count_result.all()}

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "success": True,
        "data": [_list_to_response(el, counts.get(el.id, 0)) for el in lists],
        "pagination": {"total": total, "page": page, "limit": limit, "totalPages": total_pages},
    }


@router.post("/email-lists", status_code=201)
async def create_email_list(
    data: EmailListCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not data.name:
        raise HTTPException(status_code=422, detail="Tên danh sách là bắt buộc")
    el = EmailList(portal_user_id=portal_user_id, name=data.name, description=data.description)
    db.add(el)
    await db.commit()
    await db.refresh(el)
    return {"success": True, "data": _list_to_response(el, 0)}


@router.put("/email-lists/{list_id}")
async def update_email_list(
    list_id: int,
    data: EmailListUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    el = await _get_list_or_404(list_id, portal_user_id, db)
    if data.name is not None:
        el.name = data.name
    if data.description is not None:
        el.description = data.description
    await db.commit()
    await db.refresh(el)
    return {"success": True, "data": _list_to_response(el)}


@router.delete("/email-lists/{list_id}")
async def delete_email_list(
    list_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    el = await _get_list_or_404(list_id, portal_user_id, db)
    el.is_active = False
    await db.commit()
    return {"success": True}


@router.get("/email-lists/{list_id}/export")
async def export_email_list(
    list_id: int,
    portal_user_id: str = Query(...),
    format: str = Query("csv"),
    db: AsyncSession = Depends(get_db),
):
    """Export danh sách subscribers ra file CSV."""
    el = await _get_list_or_404(list_id, portal_user_id, db)

    result = await db.execute(
        select(Subscriber).where(
            Subscriber.list_id == list_id,
            Subscriber.is_active == True,
        ).order_by(Subscriber.created_at.asc())
    )
    subscribers = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "name", "created_at"])
    for s in subscribers:
        writer.writerow([s.email, s.name or "", s.created_at.isoformat() if s.created_at else ""])

    output.seek(0)
    filename = f"email-list-{list_id}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Subscriber Endpoints ─────────────────────────────────────────

@router.get("/email-lists/{list_id}")
async def get_email_list(
    list_id: int,
    portal_user_id: str = Query(...),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Chi tiết list + danh sách subscribers có phân trang."""
    el = await _get_list_or_404(list_id, portal_user_id, db)

    stmt = select(Subscriber).where(
        Subscriber.list_id == list_id,
        Subscriber.is_active == True,
    )
    if search:
        stmt = stmt.where(
            (Subscriber.email.ilike(f"%{search}%")) | (Subscriber.name.ilike(f"%{search}%"))
        )
    stmt = stmt.order_by(Subscriber.created_at.desc())

    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    subs = result.scalars().all()

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "success": True,
        "data": {
            **_list_to_response(el, total),
            "subscribers": [_subscriber_to_response(s) for s in subs],
        },
        "pagination": {"total": total, "page": page, "limit": limit, "totalPages": total_pages},
    }


@router.post("/email-lists/{list_id}/subscribers", status_code=201)
async def add_subscriber(
    list_id: int,
    data: SubscriberCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await _get_list_or_404(list_id, portal_user_id, db)

    # Check duplicate
    existing = await db.execute(
        select(Subscriber).where(
            Subscriber.list_id == list_id,
            Subscriber.email == data.email,
            Subscriber.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Email đã tồn tại trong danh sách này")

    s = Subscriber(
        list_id=list_id,
        email=data.email,
        name=data.name,
        custom_fields=json.dumps(data.custom_fields) if data.custom_fields else None,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return {"success": True, "data": _subscriber_to_response(s)}


@router.put("/email-lists/{list_id}/subscribers/{sub_id}")
async def update_subscriber(
    list_id: int,
    sub_id: int,
    data: SubscriberUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await _get_list_or_404(list_id, portal_user_id, db)

    result = await db.execute(
        select(Subscriber).where(
            Subscriber.id == sub_id,
            Subscriber.list_id == list_id,
            Subscriber.is_active == True,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Không tìm thấy subscriber")

    if data.email is not None:
        s.email = data.email
    if data.name is not None:
        s.name = data.name
    if data.custom_fields is not None:
        s.custom_fields = json.dumps(data.custom_fields)

    await db.commit()
    await db.refresh(s)
    return {"success": True, "data": _subscriber_to_response(s)}


@router.delete("/email-lists/{list_id}/subscribers/{sub_id}")
async def delete_subscriber(
    list_id: int,
    sub_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await _get_list_or_404(list_id, portal_user_id, db)

    result = await db.execute(
        select(Subscriber).where(
            Subscriber.id == sub_id,
            Subscriber.list_id == list_id,
            Subscriber.is_active == True,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Không tìm thấy subscriber")

    s.is_active = False
    await db.commit()
    return {"success": True}


@router.post("/email-lists/{list_id}/subscribers/bulk-delete")
async def bulk_delete_subscribers(
    list_id: int,
    data: BulkDeleteRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await _get_list_or_404(list_id, portal_user_id, db)

    result = await db.execute(
        select(Subscriber).where(
            Subscriber.id.in_(data.ids),
            Subscriber.list_id == list_id,
            Subscriber.is_active == True,
        )
    )
    subs = result.scalars().all()
    for s in subs:
        s.is_active = False
    await db.commit()
    return {"success": True, "data": {"deleted": len(subs)}}


@router.post("/email-lists/{list_id}/subscribers/bulk", status_code=201)
async def bulk_import_subscribers(
    list_id: int,
    data: BulkImportRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Import nhiều subscribers cùng lúc, bỏ qua duplicate."""
    await _get_list_or_404(list_id, portal_user_id, db)

    # Get existing emails
    existing_result = await db.execute(
        select(Subscriber.email).where(
            Subscriber.list_id == list_id,
            Subscriber.is_active == True,
        )
    )
    existing_emails = {row[0].lower() for row in existing_result.all()}

    added = 0
    duplicates = 0
    for item in data.subscribers:
        if not item.email:
            continue
        if item.email.lower() in existing_emails:
            duplicates += 1
            continue
        db.add(Subscriber(list_id=list_id, email=item.email, name=item.name))
        existing_emails.add(item.email.lower())
        added += 1

    await db.commit()
    return {"success": True, "data": {"added": added, "duplicates": duplicates}}


@router.post("/email-lists/{list_id}/import", status_code=201)
async def import_subscribers(
    list_id: int,
    data: BulkImportRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Alias của bulk import — dùng cho FE import CSV."""
    return await bulk_import_subscribers(list_id, data, portal_user_id, db)


@router.get("/email-lists/{list_id}/cloudinary-config")
async def get_upload_config(
    list_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Trả về config upload ảnh (placeholder — tích hợp Cloudinary sau nếu cần)."""
    await _get_list_or_404(list_id, portal_user_id, db)
    return {"success": True, "data": {"uploadUrl": None, "provider": "cloudflare"}}
