"""
exit_interview_route.py — Biên bản phỏng vấn nghỉ việc (QF-HRA-11)

Endpoint prefix: /api/v1/exit-interview  (mount trong main.py)

Luồng trạng thái:
  DRAFT
    → PENDING_EMPLOYEE_SIGN   (action: send_to_employee — HR)
    → PENDING_HR_CONFIRM      (action: sign — Employee)
    → COMPLETED               (action: confirm — HR)
    → REJECTED                (action: reject — HR bất kỳ bước)
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.exit_interview_model import ExitInterview, ExitInterviewStep
from app.models.user_model import User
from app.models.user_signature_model import UserSignature

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ref_code(interview_id: int) -> str:
    y = datetime.now(timezone.utc).year
    return f"QF-HRA-11-{y}-{int(interview_id):05d}"


def _step_to_dict(s: ExitInterviewStep) -> dict:
    return {
        "id": s.id,
        "action": s.action,
        "actor_id": s.actor_id,
        "actor_name": s.actor_name,
        "actor_title": s.actor_title,
        "note": s.note,
        "acted_at": s.acted_at.isoformat() if s.acted_at else None,
    }


def _interview_to_dict(h: ExitInterview) -> dict:
    return {
        "id": h.id,
        "ref_code": h.ref_code,
        "tenant_id": h.tenant_id,
        "created_by": h.created_by,
        "employee_id": h.employee_id,
        "employee_name": h.employee_name,
        "employee_code": h.employee_code,
        "department": h.department,
        "job_title": h.job_title,
        "email": h.email,
        "interview_date": h.interview_date,
        "interviewer_name": h.interviewer_name,
        "joining_date": h.joining_date,
        "contract_type": h.contract_type,
        "created_date": h.created_date,
        "content": h.content or {},
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


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────

class CreateExitInterviewRequest(BaseModel):
    tenant_id: Optional[str] = None
    created_by: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: str
    employee_code: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    email: Optional[str] = None
    interview_date: Optional[str] = None
    interviewer_name: Optional[str] = None
    joining_date: Optional[str] = None
    contract_type: Optional[str] = None
    content: Optional[Dict[str, Any]] = {}


class TakeActionRequest(BaseModel):
    action: str
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_interviews(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    created_by: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ExitInterview)
    if tenant_id:
        stmt = stmt.where(ExitInterview.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(ExitInterview.status == status)
    if created_by:
        stmt = stmt.where(ExitInterview.created_by == str(created_by))
    if employee_id:
        stmt = stmt.where(ExitInterview.employee_id == str(employee_id))

    total = (await db.execute(select(sa_func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (
        await db.execute(
            stmt.order_by(ExitInterview.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {"data": {"items": [_interview_to_dict(h) for h in items], "total": total, "page": page}}


@router.post("")
async def create_interview(
    body: CreateExitInterviewRequest,
    db: AsyncSession = Depends(get_db),
):
    interview = ExitInterview(
        tenant_id=body.tenant_id,
        created_by=str(body.created_by) if body.created_by else None,
        employee_id=str(body.employee_id) if body.employee_id else None,
        employee_name=body.employee_name,
        employee_code=body.employee_code,
        department=body.department,
        job_title=body.job_title,
        email=body.email,
        interview_date=body.interview_date,
        interviewer_name=body.interviewer_name,
        joining_date=body.joining_date,
        contract_type=body.contract_type,
        created_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        content=body.content or {},
        status="DRAFT",
    )
    db.add(interview)
    await db.flush()
    interview.ref_code = _ref_code(interview.id)
    await db.commit()
    await db.refresh(interview)
    return {"data": _interview_to_dict(interview)}


@router.get("/{interview_id}")
async def get_interview(interview_id: int, db: AsyncSession = Depends(get_db)):
    h = (await db.execute(
        select(ExitInterview).where(ExitInterview.id == interview_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Exit interview not found")
    return {"data": _interview_to_dict(h)}


@router.post("/{interview_id}/actions")
async def take_action(
    interview_id: int,
    body: TakeActionRequest,
    db: AsyncSession = Depends(get_db),
):
    h = (await db.execute(
        select(ExitInterview).where(ExitInterview.id == interview_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Exit interview not found")

    action = body.action.strip().lower()
    actor_name, actor_title = await _resolve_actor(body.actor_id, db)
    actor_name = actor_name or body.actor_name

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

    elif action == "sign":
        sig_url = await _get_signature_url(body.actor_id, db)
        h.status = "PENDING_HR_CONFIRM"
        h.employee_signed_at = now
        h.employee_signature_url = sig_url

    elif action == "confirm":
        sig_url = await _get_signature_url(body.actor_id, db)
        h.status = "COMPLETED"
        h.hr_signer_id = str(body.actor_id) if body.actor_id else None
        h.hr_signer_name = actor_name
        h.hr_signed_at = now
        h.hr_signature_url = sig_url
        h.completed_at = now

    elif action == "reject":
        h.status = "REJECTED"
        h.reject_note = body.note or "Biên bản bị từ chối"

    # Cập nhật nội dung biên bản nếu frontend gửi kèm
    if body.content is not None:
        h.content = body.content

    step = ExitInterviewStep(
        interview_id=h.id,
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
    return {"data": _interview_to_dict(h)}
