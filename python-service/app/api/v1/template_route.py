import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sql_func
from pydantic import BaseModel

from app.db.database import get_db
from app.models.template_model import Template

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    json_data: Optional[dict] = None
    html_snapshot: Optional[str] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    json_data: Optional[dict] = None
    html_snapshot: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────

def _to_response(t: Template) -> dict:
    json_data = None
    if t.json_data:
        try:
            json_data = json.loads(t.json_data)
        except Exception:
            json_data = None
    return {
        "_id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "jsonData": json_data,
        "htmlSnapshot": t.html_snapshot,
        "createdAt": t.created_at.isoformat() if t.created_at else None,
        "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
    }


# ─── Endpoints ────────────────────────────────────────────────────

@router.get("/templates/my-templates")
async def list_my_templates(
    portal_user_id: str = Query(...),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sortBy: Optional[str] = Query("createdAt"),
    sortOrder: Optional[str] = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Lấy danh sách templates của user với phân trang, tìm kiếm và lọc."""
    stmt = select(Template).where(
        Template.portal_user_id == portal_user_id,
        Template.is_active == True,
    )

    if search:
        stmt = stmt.where(Template.name.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Template.category == category)

    # Sort
    sort_col = {
        "createdAt": Template.created_at,
        "updatedAt": Template.updated_at,
        "name": Template.name,
    }.get(sortBy, Template.created_at)

    if sortOrder == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # Count total
    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Paginate
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    templates = result.scalars().all()

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "success": True,
        "data": [_to_response(t) for t in templates],
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        },
    }


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lấy một template theo ID."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.portal_user_id == portal_user_id,
            Template.is_active == True,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Không tìm thấy template")
    return {"success": True, "data": _to_response(t)}


@router.post("/templates", status_code=201)
async def create_template(
    data: TemplateCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Tạo template mới."""
    if not data.name:
        raise HTTPException(status_code=422, detail="Tên template là bắt buộc")

    t = Template(
        portal_user_id=portal_user_id,
        name=data.name,
        description=data.description,
        category=data.category,
        json_data=json.dumps(data.json_data) if data.json_data else None,
        html_snapshot=data.html_snapshot,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"success": True, "data": _to_response(t)}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Cập nhật template."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.portal_user_id == portal_user_id,
            Template.is_active == True,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Không tìm thấy template")

    if data.name is not None:
        t.name = data.name
    if data.description is not None:
        t.description = data.description
    if data.category is not None:
        t.category = data.category
    if data.json_data is not None:
        t.json_data = json.dumps(data.json_data)
    if data.html_snapshot is not None:
        t.html_snapshot = data.html_snapshot

    await db.commit()
    await db.refresh(t)
    return {"success": True, "data": _to_response(t)}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete template."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.portal_user_id == portal_user_id,
            Template.is_active == True,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Không tìm thấy template")

    t.is_active = False
    await db.commit()
    return {"success": True}


@router.post("/templates/{template_id}/duplicate", status_code=201)
async def duplicate_template(
    template_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Nhân bản template."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.portal_user_id == portal_user_id,
            Template.is_active == True,
        )
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Không tìm thấy template")

    copy = Template(
        portal_user_id=portal_user_id,
        name=f"Copy of {original.name}",
        description=original.description,
        category=original.category,
        json_data=original.json_data,
        html_snapshot=original.html_snapshot,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return {"success": True, "data": _to_response(copy)}


@router.post("/templates/{template_id}/use")
async def increment_usage(
    template_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Đánh dấu template đã được sử dụng (no-op hiện tại, giữ để tương thích)."""
    return {"success": True}
