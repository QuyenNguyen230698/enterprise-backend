"""
offboarding_route.py — Internal API (node-gateway ↔ python-service)
PostgreSQL là source of truth cho toàn bộ offboarding data.

Endpoint prefix: /api/v1/internal/offboarding  (mount trong main.py)
"""
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, and_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.database import get_db
from app.models.document_approval_log_model import DocumentApprovalLog
from app.models.offboarding_model import OffboardingProcess, OffboardingStep
from app.models.user_model import User
from app.models.user_signature_model import UserSignature
from app.services.email_service import send_offboarding_confirmation
from app.services.notification_service import create_notification, create_broadcast_notification

router = APIRouter()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_digits(length: int = 5) -> str:
    return "".join(random.choices(string.digits, k=length))


def _application_ref_by_id(process_id: int, year: Optional[int] = None) -> str:
    y = year or datetime.now(timezone.utc).year
    return f"HRM-R-{y}-{int(process_id):05d}"


def _default_handover() -> dict:
    return {
        "ho1_status": "PENDING", "ho1_confirmed_name": None, "ho1_date": None, "ho1_notes": None,
        "ho1_confirmed_signature_image_url": None, "ho1_confirmed_signature_data": None,
        "ho1_rejected_name": None, "ho1_rejected_date": None, "ho1_reject_reason": None,
        "ho2_status": "PENDING", "ho2_confirmed_name": None, "ho2_date": None, "ho2_notes": None,
        "ho2_confirmed_signature_image_url": None, "ho2_confirmed_signature_data": None,
        "ho2_rejected_name": None, "ho2_rejected_date": None, "ho2_reject_reason": None,
        "ho3_status": "PENDING", "ho3_confirmed_name": None, "ho3_date": None, "ho3_notes": None,
        "ho3_confirmed_signature_image_url": None, "ho3_confirmed_signature_data": None,
        "ho3_rejected_name": None, "ho3_rejected_date": None, "ho3_reject_reason": None,
    }


def _compute_payment_date(last_working_day: Optional[str]) -> Optional[str]:
    if not last_working_day:
        return None
    try:
        lwd = datetime.fromisoformat(last_working_day)
        month = lwd.month + 1
        year = lwd.year + (1 if month > 12 else 0)
        month = month if month <= 12 else 1
        return f"{year}-{month:02d}-05"
    except Exception:
        return None


async def _get_signature_payload(actor_id: Optional[str], db: AsyncSession) -> Dict[str, Optional[str]]:
    if not actor_id:
        return {"signature_image_url": None, "signature_data": None}
    row = (
        await db.execute(
            select(UserSignature.signature_image_url, UserSignature.signature_data)
            .where(cast(UserSignature.portal_user_id, String) == str(actor_id))
            .limit(1)
        )
    ).first()
    if not row:
        return {"signature_image_url": None, "signature_data": None}
    return {
        "signature_image_url": row[0] or None,
        "signature_data": row[1] or None,
    }


def _all_handover_confirmed(handover: Optional[dict]) -> bool:
    h = handover or {}
    return all(h.get(k) == "CONFIRMED" for k in ("ho1_status", "ho2_status", "ho3_status"))


def _should_log_sign_approval(step_number: int, action: str) -> bool:
    # SignHub approval log for current offboarding documents.
    # Keep this whitelist explicit so future document types can reuse the same model.
    allowed = {
        (2, "approve"),
        (3, "process"),
        (4, "approve"),
        (4, "authorize"),
        (5, "approve"),
        (5, "authorize"),
    }
    return (step_number, action) in allowed


def _step_to_dict(s: OffboardingStep) -> dict:
    return {
        "id": s.id,
        "step_number": s.step_number,
        "action": s.action,
        "actor_id": s.actor_id,
        "actor_name": s.actor_name,
        "note": s.note,
        "acted_at": s.acted_at.isoformat() if s.acted_at else None,
        **(s.extra or {}),
    }

def _pick_step(steps: List[OffboardingStep], step_number: int, actions: List[str]) -> Optional[OffboardingStep]:
    for s in steps:
        if s.step_number == step_number and s.action in actions:
            return s
    return None

def _approval_summary(p: OffboardingProcess) -> dict:
    steps = list(p.steps or [])
    requested = _pick_step(steps, 1, ["submit"])
    verified = _pick_step(steps, 2, ["approve", "reject"])
    checked = _pick_step(steps, 4, ["approve", "authorize", "reject"])
    approved = _pick_step(steps, 5, ["approve", "reject", "authorize"])
    return {
        "requested": {
            "name": p.employee_name,
            "title": p.job_title,
            "date": requested.acted_at.isoformat() if requested and requested.acted_at else p.resignation_date,
            "signature_text": "Signed" if requested else None,
        },
        "verified": {
            "name": verified.actor_name if verified else None,
            "title": "Head of Dept.",
            "date": verified.acted_at.isoformat() if verified and verified.acted_at else None,
            "signature_text": "Signed" if verified else None,
        },
        "checked": {
            "name": checked.actor_name if checked else None,
            "title": "HR Dept.",
            "date": checked.acted_at.isoformat() if checked and checked.acted_at else None,
            "signature_text": "Signed" if checked else None,
        },
        "approved": {
            "name": approved.actor_name if approved else None,
            "title": "Management",
            "date": approved.acted_at.isoformat() if approved and approved.acted_at else None,
            "signature_text": "Signed" if approved else None,
        },
    }


async def _resolve_employee_email(process: OffboardingProcess, db: AsyncSession) -> Optional[str]:
    """
    Resolve employee email from users table.
    Primary: users.portal_user_id == offboarding.employee_id
    Fallback: users.e_code/hr_code == offboarding.employee_id / offboarding.employee_code
    """
    employee_id = str(process.employee_id or "").strip()
    employee_code = str(process.employee_code or "").strip()
    if not employee_id and not employee_code:
        return None

    stmt = select(User.email).where(
        (User.portal_user_id == employee_id)
        | (User.e_code == employee_id)
        | (User.hr_code == employee_id)
        | (User.e_code == employee_code)
        | (User.hr_code == employee_code)
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _resolve_actor_identity(
    actor_id: Optional[str],
    fallback_name: Optional[str],
    db: AsyncSession,
) -> Tuple[Optional[str], Optional[str]]:
    actor_id_val = str(actor_id or "").strip()
    if not actor_id_val:
        normalized_fallback = (fallback_name or "").strip() or None
        return normalized_fallback, None
    user = (
        await db.execute(
            select(User.name, User.title).where(User.portal_user_id == actor_id_val).limit(1)
        )
    ).first()
    if user:
        name = (user[0] or "").strip() or None
        title = (user[1] or "").strip() or None
        if name:
            return name, title
    normalized_fallback = (fallback_name or "").strip() or None
    return normalized_fallback, None


def _process_to_dict(p: OffboardingProcess) -> dict:
    ref_year = None
    try:
        ref_year = datetime.fromisoformat(p.resignation_date).year if p.resignation_date else None
    except Exception:
        ref_year = p.created_at.year if p.created_at else None

    return {
        "id": p.id,
        "application_ref": _application_ref_by_id(p.id, ref_year),
        "tenant_id": p.tenant_id,
        "employee_id": p.employee_id,
        "employee_name": p.employee_name,
        "employee_code": p.employee_code,
        "dept_code": p.dept_code,
        "department": p.department,
        "job_title": p.job_title,
        "joining_date": p.joining_date,
        "resignation_date": p.resignation_date,
        "last_working_day": p.last_working_day,
        "contract_type": p.contract_type,
        "reason_for_resignation": p.reason_for_resignation,
        "commitment_accepted": p.commitment_accepted,
        "status": p.status,
        "payment_date": p.payment_date,
        "handover": p.handover or _default_handover(),
        "approval_summary": _approval_summary(p),
        "steps": [_step_to_dict(s) for s in (p.steps or [])],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class ProcessCreate(BaseModel):
    tenant_id: Optional[str] = None
    employee_id: str
    employee_name: str
    employee_code: Optional[str] = None
    dept_code: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    joining_date: Optional[str] = None
    last_working_day: Optional[str] = None
    contract_type: Optional[str] = "DEFINITE"
    reason_for_resignation: str
    commitment_accepted: Optional[bool] = False
    # Step 1 actor info
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None


class TakeActionBody(BaseModel):
    action: str
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    extra: Optional[Dict[str, Any]] = {}


class ConfirmHandoverBody(BaseModel):
    notes: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None


class OverrideReturnBody(BaseModel):
    reason: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None

class RejectHandoverBody(BaseModel):
    reason: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None

class HandoverTimelineActionBody(BaseModel):
    action: str  # verify | sign | complete
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None

class HandoverContentBody(BaseModel):
    content: Dict[str, Any]  # arbitrary row data keyed by field name


# ─── Tạo process ─────────────────────────────────────────────────────────────

@router.post("/processes", status_code=201)
async def create_process(data: ProcessCreate, db: AsyncSession = Depends(get_db)):
    # Block re-submit when employee already has a non-rejected process.
    existing_stmt = select(OffboardingProcess).where(
        OffboardingProcess.employee_id == str(data.employee_id),
        OffboardingProcess.status != "REJECTED",
    )
    existing = (await db.execute(existing_stmt)).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="User này đã nộp đơn nghỉ việc rồi. Chỉ được nộp lại khi đơn trước bị REJECTED.",
        )

    today = datetime.now(timezone.utc).date().isoformat()

    process = OffboardingProcess(
        application_ref=f"TEMP-{_random_digits(10)}",
        tenant_id=data.tenant_id,
        employee_id=data.employee_id,
        employee_name=data.employee_name,
        employee_code=data.employee_code,
        dept_code=data.dept_code or data.department,
        department=data.department,
        job_title=data.job_title,
        joining_date=data.joining_date,
        resignation_date=today,
        last_working_day=data.last_working_day,
        contract_type=data.contract_type or "DEFINITE",
        reason_for_resignation=data.reason_for_resignation,
        commitment_accepted=data.commitment_accepted or False,
        status="PENDING_MANAGER",
        payment_date=None,
        handover=_default_handover(),
    )
    db.add(process)
    await db.flush()  # get process.id
    process.application_ref = _application_ref_by_id(process.id, datetime.now(timezone.utc).year)

    actor_name, actor_title = await _resolve_actor_identity(data.actor_id, data.actor_name, db)
    step = OffboardingStep(
        process_id=process.id,
        step_number=1,
        action="submit",
        actor_id=data.actor_id,
        actor_name=actor_name,
        note="Submit resignation",
        extra={},
    )
    db.add(step)
    db.add(
        DocumentApprovalLog(
            tenant_id=process.tenant_id,
            document_type="OFFBOARDING",
            document_id=str(process.id),
            document_ref=process.application_ref or _application_ref_by_id(process.id),
            source_module="sign-hub",
            step_number=1,
            action="submit",
            status_after=process.status,
            actor_id=data.actor_id,
            actor_name=actor_name,
            actor_title=actor_title,
            note="Submit resignation",
            extra={},
        )
    )
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Danh sách process ────────────────────────────────────────────────────────

@router.get("/processes")
async def list_processes(
    tenant_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(OffboardingProcess)

    if tenant_id:
        stmt = stmt.where(OffboardingProcess.tenant_id == tenant_id)
    if employee_id:
        stmt = stmt.where(OffboardingProcess.employee_id == employee_id)
    if status:
        stmt = stmt.where(OffboardingProcess.status == status)

    count_stmt = select(sa_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(OffboardingProcess.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    processes = (await db.execute(stmt)).scalars().all()

    return {
        "success": True,
        "data": {
            "items": [_process_to_dict(p) for p in processes],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


# ─── Chi tiết process ─────────────────────────────────────────────────────────

@router.get("/processes/{process_id}")
async def get_process(process_id: int, db: AsyncSession = Depends(get_db)):
    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    return {"success": True, "data": _process_to_dict(process)}

# ─── Thực hiện action theo step ───────────────────────────────────────────────

@router.post("/processes/{process_id}/steps/{step_number}/action")
async def take_action(
    process_id: int,
    step_number: int,
    body: TakeActionBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    action = body.action

    if step_number == 2:
        process.status = "REJECTED" if action == "reject" else "PENDING_HR_PROCESS"
    elif step_number == 3:
        process.status = "PENDING_HR_APPROVAL"
    elif step_number == 4:
        process.status = "REJECTED" if action == "reject" else "PENDING_GM"
    elif step_number == 5:
        process.status = "REJECTED" if action == "reject" else "PENDING_HANDOVER"
        if action in ("approve", "authorize"):
            employee_email = await _resolve_employee_email(process, db)
            if employee_email:
                payment = _compute_payment_date(process.last_working_day)
                background_tasks.add_task(
                    send_offboarding_confirmation,
                    to_email=employee_email,
                    process_data={
                        "employee_name": process.employee_name,
                        "application_ref": process.application_ref,
                        "resignation_date": process.resignation_date or "—",
                        "last_working_day": process.last_working_day or "—",
                        "department": process.department,
                        "job_title": process.job_title,
                        "payment_date": payment or "—",
                    },
                )
    elif step_number == 6 and action == "approve":
        process.status = "PENDING_HANDOVER"
    elif step_number == 7:
        if action == "complete":
            if not _all_handover_confirmed(process.handover):
                raise HTTPException(status_code=400, detail="Cần hoàn tất bàn giao HO-1/2/3 trước khi complete bước 7")
            process.status = "COMPLETED"
            computed = _compute_payment_date(process.last_working_day)
            if computed and (not process.payment_date or process.payment_date == process.resignation_date):
                process.payment_date = computed
        elif action == "block":
            process.status = "COMPLETED_BLOCKED"
        elif action == "unblock":
            if not _all_handover_confirmed(process.handover):
                raise HTTPException(status_code=400, detail="Cần hoàn tất bàn giao HO-1/2/3 trước khi unlock thanh toán")
            process.status = "COMPLETED"
            computed = _compute_payment_date(process.last_working_day)
            if computed and (not process.payment_date or process.payment_date == process.resignation_date):
                process.payment_date = computed

    actor_name, actor_title = await _resolve_actor_identity(body.actor_id, body.actor_name, db)
    step = OffboardingStep(
        process_id=process.id,
        step_number=step_number,
        action=action,
        actor_id=body.actor_id,
        actor_name=actor_name,
        note=body.note,
        extra=body.extra or {},
    )
    db.add(step)
    if _should_log_sign_approval(step_number, action):
        db.add(
            DocumentApprovalLog(
                tenant_id=process.tenant_id,
                document_type="OFFBOARDING",
                document_id=str(process.id),
                document_ref=process.application_ref or _application_ref_by_id(process.id),
                source_module="sign-hub",
                step_number=step_number,
                action=action,
                status_after=process.status,
                actor_id=body.actor_id,
                actor_name=actor_name,
                actor_title=actor_title,
                note=body.note,
                extra=body.extra or {},
            )
        )
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Xác nhận handover ────────────────────────────────────────────────────────

@router.post("/processes/{process_id}/handover/{ho_key}/confirm")
async def confirm_handover(
    process_id: int,
    ho_key: str,
    body: ConfirmHandoverBody,
    db: AsyncSession = Depends(get_db),
):
    if ho_key not in ("ho1", "ho2", "ho3"):
        raise HTTPException(status_code=400, detail="Handover key không hợp lệ")

    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    handover = dict(process.handover or _default_handover())
    timeline = dict(handover.get(f"{ho_key}_timeline") or {})
    if not timeline.get("completed_at"):
        raise HTTPException(status_code=400, detail="Biên bản chưa hoàn tất timeline (xác thực/ký/complete)")
    signature = await _get_signature_payload(body.actor_id, db)
    handover[f"{ho_key}_status"] = "CONFIRMED"
    handover[f"{ho_key}_confirmed_name"] = body.actor_name
    handover[f"{ho_key}_date"] = _now_iso()
    handover[f"{ho_key}_notes"] = body.notes
    handover[f"{ho_key}_confirmed_signature_image_url"] = signature["signature_image_url"]
    handover[f"{ho_key}_confirmed_signature_data"] = signature["signature_data"]
    handover[f"{ho_key}_rejected_name"] = None
    handover[f"{ho_key}_rejected_date"] = None
    handover[f"{ho_key}_reject_reason"] = None
    process.handover = handover
    flag_modified(process, "handover")

    confirmed_count = sum(
        1 for k in ("ho1_status", "ho2_status", "ho3_status") if handover.get(k) == "CONFIRMED"
    )

    step = OffboardingStep(
        process_id=process.id,
        step_number=6,
        action=f"confirm_{ho_key}",
        actor_id=body.actor_id,
        actor_name=body.actor_name,
        note=body.notes,
        extra={"ho_key": ho_key, "handover_progress": confirmed_count},
    )
    db.add(step)
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


@router.post("/processes/{process_id}/handover/{ho_key}/timeline-action")
async def handover_timeline_action(
    process_id: int,
    ho_key: str,
    body: HandoverTimelineActionBody,
    db: AsyncSession = Depends(get_db),
):
    if ho_key not in ("ho1", "ho2", "ho3"):
        raise HTTPException(status_code=400, detail="Handover key không hợp lệ")
    action = (body.action or "").strip().lower()
    if action not in ("verify", "authenticate", "sign", "complete"):
        raise HTTPException(status_code=400, detail="Action timeline không hợp lệ")

    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    if process.status != "PENDING_HANDOVER":
        raise HTTPException(status_code=400, detail="Chỉ thao tác timeline khi process ở bước handover")

    handover = dict(process.handover or _default_handover())
    timeline = dict(handover.get(f"{ho_key}_timeline") or {})
    now = _now_iso()

    signature = await _get_signature_payload(body.actor_id, db)

    if action == "verify":
        if timeline.get("verified_at"):
            raise HTTPException(status_code=400, detail="Biên bản đã xác thực")
        timeline["verified_by"] = body.actor_name
        timeline["verified_at"] = now
        timeline["verify_note"] = body.note
        timeline["verified_signature_image_url"] = signature["signature_image_url"]
        timeline["verified_signature_data"] = signature["signature_data"]
    elif action == "authenticate":
        if not timeline.get("verified_at"):
            raise HTTPException(status_code=400, detail="Cần employee ký trước khi xác thực")
        if timeline.get("authenticated_at"):
            raise HTTPException(status_code=400, detail="Biên bản đã được xác thực")
        timeline["authenticated_by"] = body.actor_name
        timeline["authenticated_at"] = now
        timeline["authenticate_note"] = body.note
    elif action == "sign":
        if not timeline.get("verified_at") or not timeline.get("authenticated_at"):
            raise HTTPException(status_code=400, detail="Cần employee ký và xác thực trước khi ký")
        if timeline.get("signed_at"):
            raise HTTPException(status_code=400, detail="Biên bản đã ký")
        timeline["signed_by"] = body.actor_name
        timeline["signed_at"] = now
        timeline["sign_note"] = body.note
        timeline["signed_signature_image_url"] = signature["signature_image_url"]
        timeline["signed_signature_data"] = signature["signature_data"]
    elif action == "complete":
        if not timeline.get("verified_at") or not timeline.get("authenticated_at") or not timeline.get("signed_at"):
            raise HTTPException(status_code=400, detail="Cần hoàn thành các bước trước khi complete")
        if timeline.get("completed_at"):
            raise HTTPException(status_code=400, detail="Biên bản đã complete")
        timeline["completed_by"] = body.actor_name
        timeline["completed_at"] = now
        timeline["complete_note"] = body.note
        timeline["completed_signature_image_url"] = signature["signature_image_url"]
        timeline["completed_signature_data"] = signature["signature_data"]

    handover[f"{ho_key}_timeline"] = timeline
    process.handover = handover
    flag_modified(process, "handover")

    step = OffboardingStep(
        process_id=process.id,
        step_number=6,
        action=f"{action}_{ho_key}",
        actor_id=body.actor_id,
        actor_name=body.actor_name,
        note=body.note,
        extra={"ho_key": ho_key, "timeline": timeline},
    )
    db.add(step)
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


@router.post("/processes/{process_id}/handover/{ho_key}/reject")
async def reject_handover(
    process_id: int,
    ho_key: str,
    body: RejectHandoverBody,
    db: AsyncSession = Depends(get_db),
):
    if ho_key not in ("ho1", "ho2", "ho3"):
        raise HTTPException(status_code=400, detail="Handover key không hợp lệ")
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="Lý do reject là bắt buộc")

    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    handover = dict(process.handover or _default_handover())
    handover[f"{ho_key}_status"] = "REJECTED"
    handover[f"{ho_key}_rejected_name"] = body.actor_name
    handover[f"{ho_key}_rejected_date"] = _now_iso()
    handover[f"{ho_key}_reject_reason"] = body.reason
    handover[f"{ho_key}_confirmed_name"] = None
    handover[f"{ho_key}_date"] = None
    process.handover = handover
    flag_modified(process, "handover")
    # Any HO reject forces employee to restart offboarding from the beginning.
    process.status = "REJECTED"

    confirmed_count = sum(
        1 for k in ("ho1_status", "ho2_status", "ho3_status") if handover.get(k) == "CONFIRMED"
    )

    step = OffboardingStep(
        process_id=process.id,
        step_number=6,
        action=f"reject_{ho_key}",
        actor_id=body.actor_id,
        actor_name=body.actor_name,
        note=body.reason,
        extra={"ho_key": ho_key, "handover_progress": confirmed_count},
    )
    db.add(step)
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Lưu nội dung biên bản (rows, interview data) ────────────────────────────

@router.patch("/processes/{process_id}/handover/{ho_key}/content")
async def save_handover_content(
    process_id: int,
    ho_key: str,
    body: HandoverContentBody,
    db: AsyncSession = Depends(get_db),
):
    if ho_key not in ("ho1", "ho2", "ho3"):
        raise HTTPException(status_code=400, detail="Handover key không hợp lệ")

    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    handover = dict(process.handover or _default_handover())
    handover[f"{ho_key}_content"] = body.content
    process.handover = handover
    flag_modified(process, "handover")
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Reset một HO về trạng thái ban đầu ──────────────────────────────────────

@router.post("/processes/{process_id}/handover/{ho_key}/reset")
async def reset_handover(
    process_id: int,
    ho_key: str,
    body: OverrideReturnBody,
    db: AsyncSession = Depends(get_db),
):
    if ho_key not in ("ho1", "ho2", "ho3"):
        raise HTTPException(status_code=400, detail="Handover key không hợp lệ")

    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    handover = dict(process.handover or _default_handover())
    # Reset status, timeline, confirmed/rejected fields — giữ nguyên content
    for field in (
        f"{ho_key}_status", f"{ho_key}_confirmed_name", f"{ho_key}_date", f"{ho_key}_notes",
        f"{ho_key}_confirmed_signature_image_url", f"{ho_key}_confirmed_signature_data",
        f"{ho_key}_rejected_name", f"{ho_key}_rejected_date", f"{ho_key}_reject_reason",
        f"{ho_key}_timeline",
    ):
        if field == f"{ho_key}_status":
            handover[field] = "PENDING"
        else:
            handover[field] = None

    process.handover = handover
    flag_modified(process, "handover")

    step = OffboardingStep(
        process_id=process.id,
        step_number=6,
        action=f"reset_{ho_key}",
        actor_id=body.actor_id,
        actor_name=body.actor_name,
        note=body.reason,
        extra={},
    )
    db.add(step)
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Override: trả về bước handover ─────────────────────────────────────────

@router.post("/processes/{process_id}/override/return-handover")
async def override_return(
    process_id: int,
    body: OverrideReturnBody,
    db: AsyncSession = Depends(get_db),
):
    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    process.status = "PENDING_HANDOVER"

    step = OffboardingStep(
        process_id=process.id,
        step_number=6,
        action="override_return_step6",
        actor_id=body.actor_id,
        actor_name=body.actor_name,
        note=body.reason,
        extra={},
    )
    db.add(step)
    await db.commit()
    await db.refresh(process)
    return {"success": True, "data": _process_to_dict(process)}


# ─── Notify: gửi in-app notification sau mỗi step ────────────────────────────

_ROLE_SUPER = "2000000001"
_ROLE_ADMIN = "2000000002"

_STEP_TITLE = {
    (1, "submit"):                ("Don thoi viec da nop", "Don thoi viec moi can duyet", None),
    (2, "approve"):               ("Manager da duyet don", "Manager da duyet, cho HR xu ly", None),
    (2, "reject"):                ("Don thoi viec bi tu choi", "Manager tu choi don", None),
    (3, "process"):               ("HR dang xu ly don", "HR da xu ly, cho HR Director duyet", None),
    (4, "approve"):               ("HR Director da duyet don", "HR Director duyet, cho GM ky", "Don thoi viec can GM phe duyet"),
    (4, "reject"):                ("HR Director tu choi don", "HR Director tu choi don", None),
    (5, "authorize"):             ("GM da phe duyet - email huong dan da gui", "GM da phe duyet, chuyen ban giao", None),
    (5, "reject"):                ("GM tu choi don thoi viec", "GM tu choi don", None),
    (6, "confirm_ho1"):           ("HO-1 ban giao cong viec da xac nhan", "HO-1 da xac nhan", None),
    (6, "confirm_ho2"):           ("HO-2 ban giao tai san da xac nhan", "HO-2 da xac nhan", None),
    (6, "confirm_ho3"):           ("HO-3 phong van nghi viec da xac nhan", "HO-3 da xac nhan", None),
    (6, "override_return_step6"): ("Yeu cau lam lai ban giao", "Da yeu cau lam lai ban giao", None),
    (7, "complete"):              ("Quy trinh thoi viec hoan tat", "Quy trinh thoi viec hoan tat", None),
    (7, "block"):                 ("Thanh toan bi tam giu - lien he HR", "Da chan thanh toan", None),
    (7, "unblock"):               ("Thanh toan da duoc mo lai", "Da mo chan thanh toan", None),
}

_ACTION_TYPE = {
    "submit": "info", "approve": "success", "authorize": "success",
    "process": "info", "reject": "warning", "complete": "success",
    "block": "warning", "confirm_ho1": "success", "confirm_ho2": "success",
    "confirm_ho3": "success", "override_return_step6": "warning",
    "unblock": "success",
}


class NotifyBody(BaseModel):
    step_number: int
    action: str
    note: Optional[str] = None
    extra: Optional[Dict[str, Any]] = {}


@router.post("/processes/{process_id}/notify")
async def notify_step(
    process_id: int,
    body: NotifyBody,
    db: AsyncSession = Depends(get_db),
):
    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Khong tim thay don")

    key = (body.step_number, body.action)
    titles = _STEP_TITLE.get(key, ("Cap nhat don thoi viec", "Cap nhat don thoi viec", None))
    emp_title, admin_title, super_title = titles
    ntype = _ACTION_TYPE.get(body.action, "info")
    link = f"/offboarding/{process_id}"

    created: list = []

    # 1. Notify employee
    if process.employee_id and process.tenant_id:
        n = await create_notification(
            db=db,
            tenant_id=process.tenant_id,
            user_id=str(process.employee_id),
            title=emp_title,
            message=f"Don {process.application_ref}" + (f" - {body.note}" if body.note else ""),
            type=ntype,
            link=link,
        )
        created.append(n)

    # 2. Notify admins in same tenant (exclude employee)
    if process.tenant_id:
        admin_rows = (await db.execute(
            select(User.portal_user_id).where(
                User.tenant_id == process.tenant_id,
                User.role == _ROLE_ADMIN,
            )
        )).scalars().all()
        target_admins = [uid for uid in admin_rows if uid != str(process.employee_id)]
        if target_admins:
            ns = await create_broadcast_notification(
                db=db,
                tenant_id=process.tenant_id,
                user_ids=target_admins,
                title=admin_title,
                message=f"{process.employee_name} - {process.application_ref}",
                type=ntype,
                link=link,
            )
            created.extend(ns)

    # 3. Notify superAdmins chỉ khi step 4 approve (GM bắt buộc phải xử lý)
    if key == (4, "approve"):
        super_rows = (await db.execute(
            select(User.portal_user_id, User.tenant_id).where(User.role == _ROLE_SUPER)
        )).all()
        for uid, tid in super_rows:
            n = await create_notification(
                db=db,
                tenant_id=tid,
                user_id=str(uid),
                title=super_title or admin_title,
                message=f"{process.employee_name} - {process.application_ref} - can GM phe duyet",
                type="warning",
                link=link,
            )
            created.append(n)

    return {
        "success": True,
        "notifications": [
            {
                "id": n.id,
                "user_id": n.user_id,
                "tenant_id": n.tenant_id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "link": n.link,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in created
        ],
    }


@router.post("/processes/{process_id}/resend-confirmation")
async def resend_confirmation_email(
    process_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    process = (await db.execute(
        select(OffboardingProcess).where(OffboardingProcess.id == process_id)
    )).scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")

    # Chỉ cho resend sau khi GM đã xử lý step 5 và quy trình đã chuyển sang hậu GM.
    if process.status not in ("PENDING_HANDOVER", "COMPLETED", "COMPLETED_BLOCKED"):
        raise HTTPException(status_code=400, detail="Chỉ gửi lại email khi đơn đã qua bước GM phê duyệt")

    employee_email = await _resolve_employee_email(process, db)
    if not employee_email:
        raise HTTPException(status_code=404, detail="Không tìm thấy email nhân viên trong bảng users")

    payment = _compute_payment_date(process.last_working_day)
    background_tasks.add_task(
        send_offboarding_confirmation,
        to_email=employee_email,
        process_data={
            "employee_name": process.employee_name,
            "application_ref": process.application_ref,
            "resignation_date": process.resignation_date or "—",
            "last_working_day": process.last_working_day or "—",
            "department": process.department,
            "job_title": process.job_title,
            "payment_date": payment or "—",
        },
    )

    return {
        "success": True,
        "data": {
            "process_id": process.id,
            "application_ref": process.application_ref,
            "email": employee_email,
            "message": "Đã đưa yêu cầu gửi lại email xác nhận vào hàng đợi.",
        },
    }


@router.get("/sign-hub/approval-logs")
async def list_approval_logs(
    document_type: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DocumentApprovalLog)
    count_stmt = select(sa_func.count(DocumentApprovalLog.id))
    filters = []

    if document_type:
        filters.append(DocumentApprovalLog.document_type == document_type.upper())
    if actor:
        keyword = f"%{actor.strip().lower()}%"
        filters.append(
            sa_func.lower(
                sa_func.concat(
                    sa_func.coalesce(DocumentApprovalLog.actor_name, ""),
                    " ",
                    sa_func.coalesce(cast(DocumentApprovalLog.actor_id, String), ""),
                )
            ).like(keyword)
        )
    if from_date:
        filters.append(cast(DocumentApprovalLog.acted_at, String) >= f"{from_date} 00:00:00")
    if to_date:
        filters.append(cast(DocumentApprovalLog.acted_at, String) <= f"{to_date} 23:59:59")

    if filters:
        stmt = stmt.where(and_(*filters))
        count_stmt = count_stmt.where(and_(*filters))

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(DocumentApprovalLog.acted_at.desc(), DocumentApprovalLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": r.id,
                    "document_type": r.document_type,
                    "document_id": r.document_id,
                    "document_ref": r.document_ref,
                    "step_number": r.step_number,
                    "action": r.action,
                    "status_after": r.status_after,
                    "actor_id": r.actor_id,
                    "actor_name": r.actor_name,
                    "actor_title": r.actor_title,
                    "note": r.note,
                    "acted_at": r.acted_at.isoformat() if r.acted_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
