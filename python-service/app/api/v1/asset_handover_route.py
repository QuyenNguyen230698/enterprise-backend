"""
asset_handover_route.py — Biên bản bàn giao tài sản thiết bị (QF-HRA-12)

Endpoint prefix: /api/v1/asset-handover  (mount trong main.py)

Luồng trạng thái:
  DRAFT
    → PENDING_EMPLOYEE_SIGN   (action: send_to_employee — HR)
    → PENDING_HR_CONFIRM      (action: sign — Employee)
    → COMPLETED               (action: confirm — HR)  → tự cập nhật HO-2 offboarding
    → REJECTED                (action: reject — HR bất kỳ bước)  → tự cập nhật HO-2 offboarding
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, JSON, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.asset_handover_model import AssetHandover, AssetHandoverStep
from app.models.offboarding_model import OffboardingProcess
from app.models.user_model import User
from app.models.user_signature_model import UserSignature

router = APIRouter()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ref_code(handover_id: int) -> str:
    y = datetime.now(timezone.utc).year
    return f"QF-HRA-12-{y}-{int(handover_id):05d}"


def _step_to_dict(s: AssetHandoverStep) -> dict:
    return {
        "id": s.id,
        "action": s.action,
        "actor_id": s.actor_id,
        "actor_name": s.actor_name,
        "actor_title": s.actor_title,
        "note": s.note,
        "acted_at": s.acted_at.isoformat() if s.acted_at else None,
    }


def _handover_to_dict(h: AssetHandover) -> dict:
    return {
        "id": h.id,
        "ref_code": h.ref_code,
        "tenant_id": h.tenant_id,
        "created_by": h.created_by,
        "offboarding_id": h.offboarding_id,
        "offboarding_ref": h.offboarding_ref,
        "employee_id": h.employee_id,
        "employee_name": h.employee_name,
        "employee_code": h.employee_code,
        "department": h.department,
        "job_title": h.job_title,
        "handover_date": h.handover_date,
        "created_date": h.created_date,
        "assets": h.assets or [],
        "general_note": h.general_note,
        "status": h.status,
        "employee_signed_at": h.employee_signed_at.isoformat() if h.employee_signed_at else None,
        "employee_signature_url": h.employee_signature_url,
        "hr_signer_id": h.hr_signer_id,
        "hr_signer_name": h.hr_signer_name,
        "hr_signed_at": h.hr_signed_at.isoformat() if h.hr_signed_at else None,
        "hr_signature_url": h.hr_signature_url,
        "reject_note": h.reject_note,
        "completed_at": h.completed_at.isoformat() if h.completed_at else None,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
        "steps": [_step_to_dict(s) for s in (h.steps or [])],
    }


async def _resolve_actor(actor_id: Optional[str], db: AsyncSession):
    """Trả về (name, title) từ users table hoặc (None, None)."""
    if not actor_id:
        return None, None
    user = (
        await db.execute(
            select(User.name, User.title)
            .where(User.portal_user_id == str(actor_id))
            .limit(1)
        )
    ).first()
    if user:
        return (user[0] or "").strip() or None, (user[1] or "").strip() or None
    return None, None


async def _get_signature_url(actor_id: Optional[str], db: AsyncSession) -> Optional[str]:
    """Lấy signature image url của actor từ user_signatures."""
    if not actor_id:
        return None
    row = (
        await db.execute(
            select(UserSignature.signature_image_url, UserSignature.signature_data)
            .where(cast(UserSignature.portal_user_id, String) == str(actor_id))
            .limit(1)
        )
    ).first()
    if row:
        return row[0] or row[1] or None
    return None


async def _sync_offboarding_ho2(
    handover: AssetHandover,
    new_status: str,  # "COMPLETED" | "REJECTED"
    actor_name: Optional[str],
    db: AsyncSession,
) -> None:
    """
    Khi asset handover hoàn tất hoặc bị từ chối, tự động cập nhật
    ho2_status trên OffboardingProcess tương ứng.
    """
    if not handover.offboarding_id:
        return
    result = await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == handover.offboarding_id)
    )
    process = result.scalar_one_or_none()
    if not process:
        return

    h = dict(process.handover or {})
    now_iso = _now().isoformat()

    if new_status == "COMPLETED":
        h["ho2_status"] = "CONFIRMED"
        h["ho2_confirmed_name"] = actor_name or "HR Staff"
        h["ho2_date"] = now_iso
        h["ho2_notes"] = f"Xác nhận qua biên bản {handover.ref_code or handover.id}"
    elif new_status == "REJECTED":
        h["ho2_status"] = "REJECTED"
        h["ho2_rejected_name"] = actor_name or "HR Staff"
        h["ho2_rejected_date"] = now_iso
        h["ho2_reject_reason"] = "Chưa bàn giao trang thiết bị đầy đủ"

    process.handover = h
    # Gắn id biên bản vào handover JSON để frontend link được
    h["ho2_asset_handover_id"] = handover.id
    h["ho2_asset_handover_status"] = new_status
    process.handover = h
    db.add(process)


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────

class AssetItem(BaseModel):
    name: str
    serial: Optional[str] = None
    condition: Optional[str] = "GOOD"   # GOOD | DAMAGED | LOST
    note: Optional[str] = None
    employee_note: Optional[str] = None


class CreateHandoverRequest(BaseModel):
    tenant_id: Optional[str] = None
    created_by: Optional[str] = None
    offboarding_id: Optional[int] = None
    employee_id: Optional[str] = None
    employee_name: str
    employee_code: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    handover_date: Optional[str] = None
    created_date: Optional[str] = None
    general_note: Optional[str] = None
    assets: Optional[List[AssetItem]] = []


class UpdateAssetsRequest(BaseModel):
    assets: List[AssetItem]


class TakeActionRequest(BaseModel):
    action: str          # send_to_employee | sign | confirm | reject
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_handovers(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    created_by: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetHandover)
    if tenant_id:
        stmt = stmt.where(AssetHandover.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(AssetHandover.status == status)
    if employee_id:
        stmt = stmt.where(AssetHandover.employee_id == str(employee_id))
    if created_by:
        stmt = stmt.where(AssetHandover.created_by == str(created_by))

    total = (await db.execute(select(sa_func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (
        await db.execute(
            stmt.order_by(AssetHandover.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {"data": {"items": [_handover_to_dict(h) for h in items], "total": total, "page": page}}


@router.post("")
async def create_handover(
    body: CreateHandoverRequest,
    db: AsyncSession = Depends(get_db),
):
    # Lấy offboarding_ref nếu có offboarding_id
    offboarding_ref = None
    if body.offboarding_id:
        p = (await db.execute(
            select(OffboardingProcess).where(OffboardingProcess.id == body.offboarding_id)
        )).scalar_one_or_none()
        if p:
            offboarding_ref = getattr(p, "application_ref", None) or f"HRM-R-{p.id}"

    handover = AssetHandover(
        tenant_id=body.tenant_id,
        created_by=str(body.created_by) if body.created_by else None,
        offboarding_id=body.offboarding_id,
        offboarding_ref=offboarding_ref,
        employee_id=str(body.employee_id) if body.employee_id else None,
        employee_name=body.employee_name,
        employee_code=body.employee_code,
        department=body.department,
        job_title=body.job_title,
        handover_date=body.handover_date,
        created_date=body.created_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        general_note=body.general_note,
        assets=[a.model_dump() for a in (body.assets or [])],
        status="DRAFT",
    )
    db.add(handover)
    await db.flush()  # lấy id trước khi commit

    handover.ref_code = _ref_code(handover.id)
    # Nếu linked offboarding: gắn asset_handover_id vào handover JSON
    if body.offboarding_id:
        p2 = (await db.execute(
            select(OffboardingProcess).where(OffboardingProcess.id == body.offboarding_id)
        )).scalar_one_or_none()
        if p2:
            h = dict(p2.handover or {})
            h["ho2_asset_handover_id"] = handover.id
            h["ho2_asset_handover_status"] = "DRAFT"
            p2.handover = h
            db.add(p2)

    await db.commit()
    await db.refresh(handover)
    return {"data": _handover_to_dict(handover)}


@router.get("/{handover_id}")
async def get_handover(handover_id: int, db: AsyncSession = Depends(get_db)):
    h = (await db.execute(
        select(AssetHandover).where(AssetHandover.id == handover_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Asset handover not found")
    return {"data": _handover_to_dict(h)}


@router.put("/{handover_id}/assets")
async def update_assets(
    handover_id: int,
    body: UpdateAssetsRequest,
    db: AsyncSession = Depends(get_db),
):
    h = (await db.execute(
        select(AssetHandover).where(AssetHandover.id == handover_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Asset handover not found")
    if h.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Chỉ có thể sửa tài sản khi biên bản ở trạng thái DRAFT")

    h.assets = [a.model_dump() for a in body.assets]
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return {"data": _handover_to_dict(h)}


@router.post("/{handover_id}/actions")
async def take_action(
    handover_id: int,
    body: TakeActionRequest,
    db: AsyncSession = Depends(get_db),
):
    h = (await db.execute(
        select(AssetHandover).where(AssetHandover.id == handover_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Asset handover not found")

    action = body.action.strip().lower()
    actor_name, actor_title = await _resolve_actor(body.actor_id, db)
    actor_name = actor_name or body.actor_name

    # ── Validate transition ────────────────────────────────────────────────────
    VALID_TRANSITIONS: Dict[str, List[str]] = {
        "DRAFT":                 ["send_to_employee", "reject"],
        "PENDING_EMPLOYEE_SIGN": ["sign", "reject"],
        "PENDING_HR_CONFIRM":    ["confirm", "reject"],
    }
    if h.status in ("COMPLETED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Biên bản đã kết thúc, không thể thao tác thêm")
    if action not in VALID_TRANSITIONS.get(h.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Hành động '{action}' không hợp lệ ở trạng thái '{h.status}'"
        )

    now = _now()

    if action == "send_to_employee":
        h.status = "PENDING_EMPLOYEE_SIGN"
        if h.offboarding_id:
            p = (await db.execute(
                select(OffboardingProcess).where(OffboardingProcess.id == h.offboarding_id)
            )).scalar_one_or_none()
            if p:
                hh = dict(p.handover or {})
                hh["ho2_asset_handover_status"] = "PENDING_EMPLOYEE_SIGN"
                p.handover = hh
                db.add(p)

    elif action == "sign":
        # Nhân viên ký nhận — lấy chữ ký từ user_signatures
        sig_url = await _get_signature_url(body.actor_id, db)
        h.status = "PENDING_HR_CONFIRM"
        h.employee_signed_at = now
        h.employee_signature_url = sig_url
        if h.offboarding_id:
            p = (await db.execute(
                select(OffboardingProcess).where(OffboardingProcess.id == h.offboarding_id)
            )).scalar_one_or_none()
            if p:
                hh = dict(p.handover or {})
                hh["ho2_asset_handover_status"] = "PENDING_HR_CONFIRM"
                p.handover = hh
                db.add(p)

    elif action == "confirm":
        # HR xác nhận nhận lại tài sản
        sig_url = await _get_signature_url(body.actor_id, db)
        h.status = "COMPLETED"
        h.hr_signer_id = str(body.actor_id) if body.actor_id else None
        h.hr_signer_name = actor_name
        h.hr_signed_at = now
        h.hr_signature_url = sig_url
        h.completed_at = now
        await _sync_offboarding_ho2(h, "COMPLETED", actor_name, db)

    elif action == "reject":
        h.status = "REJECTED"
        h.reject_note = body.note or "Biên bản bị từ chối"
        await _sync_offboarding_ho2(h, "REJECTED", actor_name, db)

    # Cập nhật nội dung biên bản nếu frontend gửi kèm
    if body.content is not None and body.content.get("assets") is not None:
        h.assets = body.content["assets"]

    # Ghi log step
    step = AssetHandoverStep(
        handover_id=h.id,
        action=action,
        actor_id=str(body.actor_id) if body.actor_id else None,
        actor_name=actor_name,
        actor_title=actor_title,
        note=body.note,
    )
    db.add(step)
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return {"data": _handover_to_dict(h)}


@router.get("/by-offboarding/{offboarding_id}")
async def get_by_offboarding(offboarding_id: int, db: AsyncSession = Depends(get_db)):
    """Lấy biên bản mới nhất được liên kết với một offboarding process."""
    h = (await db.execute(
        select(AssetHandover)
        .where(AssetHandover.offboarding_id == offboarding_id)
        .order_by(AssetHandover.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not h:
        return {"data": None}
    return {"data": _handover_to_dict(h)}
