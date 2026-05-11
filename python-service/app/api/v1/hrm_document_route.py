"""
hrm_document_route.py — Internal API (node-gateway ↔ python-service)
Prefix: /api/v1/internal/hrm/documents  (mounted in main.py)

Endpoints:
  POST   /                              → Tạo biên bản từ template
  GET    /                              → Danh sách (filter tenant, status, submitted_by)
  GET    /{doc_id}                      → Chi tiết
  POST   /{doc_id}/submit               → Nộp biên bản (DRAFT → PENDING_STEP_2)
  PATCH  /{doc_id}/content              → Lưu nội dung tự động (auto-save draft)
  POST   /{doc_id}/steps/{n}/action     → Approve / Reject theo bước (có verify_token cho ký số)
  POST   /{doc_id}/notify               → Gửi thông báo cho bước tiếp theo
  DELETE /{doc_id}                      → Xóa biên bản (chỉ khi chưa ký)
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.database import get_db
from app.models.hrm_document_model import HrmDocument
from app.models.user_model import User
from app.models.user_signature_model import UserSignature
from app.models.signature_otp_model import SignatureOtp

router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(doc: HrmDocument) -> Dict[str, Any]:
    return {
        "id": doc.id,
        "tenantId": doc.tenant_id,
        "templateId": doc.template_id,
        "name": doc.name,
        "code": doc.code,
        "docType": doc.doc_type,
        "titleVn": doc.title_vn,
        "titleEn": doc.title_en,
        "contentBlocks": doc.content_blocks or [],
        "signers": doc.signers or [],
        "workflowSteps": doc.workflow_steps or [],
        "status": doc.status,
        "approvalLogs": doc.approval_logs or [],
        "submittedBy": doc.submitted_by,
        "submittedByName": doc.submitted_by_name,
        "submittedByTitle": doc.submitted_by_title,
        "submittedByDept": doc.submitted_by_dept,
        "note": doc.note,
        "completedAt": doc.completed_at.isoformat() if doc.completed_at else None,
        "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        "updatedAt": doc.updated_at.isoformat() if doc.updated_at else None,
    }


async def _resolve_actor(actor_id: Optional[str], fallback_name: Optional[str], db: AsyncSession):
    """Return (name, title) resolved from users table."""
    if not actor_id:
        return (fallback_name or "").strip() or None, None
    row = (
        await db.execute(
            select(User.name, User.title)
            .where(User.portal_user_id == str(actor_id))
            .limit(1)
        )
    ).first()
    if row and row[0]:
        return (row[0] or "").strip() or None, (row[1] or "").strip() or None
    return (fallback_name or "").strip() or None, None


async def _get_signature_url(actor_id: Optional[str], db: AsyncSession) -> Optional[str]:
    """Return signature_image_url for actor_id from user_signatures."""
    if not actor_id:
        return None
    row = (
        await db.execute(
            select(UserSignature.signature_image_url)
            .where(cast(UserSignature.portal_user_id, String) == str(actor_id))
            .limit(1)
        )
    ).first()
    return row[0] if row else None


async def _verify_otp_token(actor_id: str, verify_token: str, db: AsyncSession) -> bool:
    """
    Kiểm tra verify_token còn hiệu lực từ bảng signature_otp_verifications.
    Token hợp lệ: verified=True, chưa hết hạn, khớp actor_id.
    """
    now = datetime.now(timezone.utc)
    row = (
        await db.execute(
            select(SignatureOtp)
            .where(
                SignatureOtp.portal_user_id == str(actor_id),
                SignatureOtp.verify_token == verify_token,
                SignatureOtp.verified == True,  # noqa: E712
                SignatureOtp.expires_at > now,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


def _next_status(workflow_steps: List[Dict], current_step_number: int, action: str) -> str:
    """
    Tính trạng thái kế tiếp dựa trên workflow_steps của template.
    - reject → REJECTED
    - approve/process/authorize → statusPending của bước tiếp theo, hoặc COMPLETED nếu hết bước
    """
    if action == "reject":
        return "REJECTED"

    sorted_steps = sorted(workflow_steps, key=lambda s: s.get("stepNumber", 0))
    next_steps = [s for s in sorted_steps if s.get("stepNumber", 0) > current_step_number]
    if next_steps:
        return next_steps[0].get("statusPending", f"PENDING_STEP_{next_steps[0]['stepNumber']}")
    return "COMPLETED"


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────

class CreateDocumentBody(BaseModel):
    templateId: Optional[int] = None
    name: str
    code: Optional[str] = None
    docType: Optional[str] = "CUSTOM"
    titleVn: Optional[str] = None
    titleEn: Optional[str] = None
    contentBlocks: Optional[List[Any]] = []
    signers: Optional[List[Any]] = []
    workflowSteps: Optional[List[Any]] = []
    note: Optional[str] = None
    # Actor info (injected by node gateway from JWT)
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    actor_title: Optional[str] = None
    actor_dept: Optional[str] = None
    tenant_id: Optional[str] = None


class SubmitDocumentBody(BaseModel):
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None


class StepActionBody(BaseModel):
    action: str          # approve | reject | process | authorize
    note: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    verify_token: Optional[str] = None   # OTP verify_token cho bước ký số


class ContentPatchBody(BaseModel):
    contentBlocks: List[Any]


# ─── Routes ───────────────────────────────────────────────────────────────────

# ── POST /  Tạo biên bản ──────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_document(body: CreateDocumentBody, db: AsyncSession = Depends(get_db)):
    actor_name, actor_title = await _resolve_actor(body.actor_id, body.actor_name, db)

    # Workflow steps: inject statusPending nếu thiếu
    steps = body.workflowSteps or []
    for i, s in enumerate(steps):
        if not s.get("statusPending"):
            s["statusPending"] = f"PENDING_STEP_{s.get('stepNumber', i + 2)}"

    doc = HrmDocument(
        tenant_id=body.tenant_id,
        template_id=body.templateId,
        name=body.name,
        code=body.code,
        doc_type=body.docType or "CUSTOM",
        title_vn=body.titleVn,
        title_en=body.titleEn,
        content_blocks=body.contentBlocks or [],
        signers=body.signers or [],
        workflow_steps=steps,
        status="DRAFT",
        approval_logs=[],
        submitted_by=body.actor_id,
        submitted_by_name=actor_name or body.actor_name,
        submitted_by_title=actor_title or body.actor_title,
        submitted_by_dept=body.actor_dept,
        note=body.note,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return {"success": True, "data": _serialize(doc)}


# ── GET /  Danh sách ─────────────────────────────────────────────────────────
@router.get("")
async def list_documents(
    tenant_id: Optional[str] = Query(None),
    submitted_by: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pending_dept: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),  # portal_user_id — lọc biên bản được giao cho user này
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(HrmDocument)
    if tenant_id:
        stmt = stmt.where(HrmDocument.tenant_id == tenant_id)
    if submitted_by:
        stmt = stmt.where(HrmDocument.submitted_by == submitted_by)
    if status:
        stmt = stmt.where(HrmDocument.status == status)

    if pending_dept:
        # Lọc các biên bản mà bước hiện tại (khớp với status) thuộc về department này
        # status của biên bản thường khớp với statusPending của một bước nào đó
        # Chúng ta dùng cast và JSON path hoặc đơn giản là lọc trong memory nếu list nhỏ.
        # Ở đây dùng logic: doc.workflow_steps chứa bước có statusPending == doc.status
        # Tuy nhiên SQLAlchemy JSON query hơi phức tạp cho list of objects.
        # Ta sẽ fetch hết rồi lọc trong memory hoặc dùng subquery nếu cần.
        # Vì đây là Enterprise app, lọc memory cho < 1000 items là ổn.
        # Nhưng để chuẩn, ta sẽ dùng status filter và verify dept ở tầng Gateway/Frontend.
        pass

    count_stmt = select(sa_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(HrmDocument.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    # Lọc trong memory theo pending_dept và assigned_to
    items = []
    for r in rows:
        serialized = _serialize(r)
        current_step = next((s for s in (r.workflow_steps or []) if s.get("statusPending") == r.status), None)

        if assigned_to:
            # Hiển thị biên bản mà user này được giao xử lý ở bước hiện tại
            assigned_ids = []
            if current_step:
                assigned_ids = [str(u.get("userId") or u.get("id", "")) for u in (current_step.get("assignedUsers") or [])]
            if str(assigned_to) not in assigned_ids:
                continue

        if pending_dept and not assigned_to:
            if not current_step or current_step.get("deptCode") != pending_dept:
                continue

        items.append(serialized)

    return {
        "success": True,
        "data": {
            "items": items,
            "total": total, # Note: total might be inaccurate if filtered by pending_dept in memory
            "page": page,
            "pageSize": page_size,
        },
    }


# ── GET /{doc_id}  Chi tiết ───────────────────────────────────────────────────
@router.get("/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(HrmDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy biên bản")
    return {"success": True, "data": _serialize(doc)}


# ── POST /{doc_id}/submit  Nộp biên bản (DRAFT → PENDING_STEP_2) ─────────────
@router.post("/{doc_id}/submit")
async def submit_document(
    doc_id: int,
    body: SubmitDocumentBody,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(HrmDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy biên bản")
    if doc.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Biên bản không ở trạng thái DRAFT")

    actor_name, _ = await _resolve_actor(body.actor_id, body.actor_name, db)

    # Tìm bước 2 (đầu tiên sau bước 1) để lấy statusPending
    sorted_steps = sorted(doc.workflow_steps or [], key=lambda s: s.get("stepNumber", 0))
    step2 = next((s for s in sorted_steps if s.get("stepNumber", 0) >= 2), None)
    new_status = step2.get("statusPending", "PENDING_STEP_2") if step2 else "COMPLETED"

    doc.status = new_status
    logs = list(doc.approval_logs or [])
    logs.append({
        "stepNumber": 1,
        "action": "submit",
        "actorId": body.actor_id,
        "actorName": actor_name or doc.submitted_by_name,
        "note": body.note,
        "signatureUrl": None,
        "signerRoleKey": None,
        "actionAt": _now_iso(),
        "statusAfter": new_status,
    })
    doc.approval_logs = logs
    flag_modified(doc, "approval_logs")
    await db.commit()
    await db.refresh(doc)
    return {"success": True, "data": _serialize(doc)}


# ── PATCH /{doc_id}/content  Auto-save nội dung DRAFT ────────────────────────
@router.patch("/{doc_id}/content")
async def save_content(doc_id: int, body: ContentPatchBody, db: AsyncSession = Depends(get_db)):
    doc = await db.get(HrmDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy biên bản")
    if doc.status not in ("DRAFT",):
        raise HTTPException(status_code=400, detail="Chỉ cập nhật nội dung khi biên bản ở trạng thái DRAFT")
    doc.content_blocks = body.contentBlocks
    flag_modified(doc, "content_blocks")
    await db.commit()
    await db.refresh(doc)
    return {"success": True, "data": _serialize(doc)}


# ── POST /{doc_id}/steps/{step_number}/action  Approve / Reject ───────────────
@router.post("/{doc_id}/steps/{step_number}/action")
async def take_step_action(
    doc_id: int,
    step_number: int,
    body: StepActionBody,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(HrmDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy biên bản")

    # Validate action value
    valid_actions = {"approve", "reject", "process", "authorize"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action không hợp lệ. Phải là: {', '.join(valid_actions)}")

    if body.action == "reject" and not (body.note or "").strip():
        raise HTTPException(status_code=400, detail="Bắt buộc phải nhập lý do khi từ chối.")

    # Lấy bước hiện tại từ workflow
    workflow = doc.workflow_steps or []
    current_step_cfg = next(
        (s for s in workflow if s.get("stepNumber") == step_number), None
    )
    if not current_step_cfg:
        raise HTTPException(status_code=400, detail=f"Bước {step_number} không tồn tại trong workflow")

    # Kiểm tra trạng thái biên bản phải đúng bước
    expected_status = current_step_cfg.get("statusPending", f"PENDING_STEP_{step_number}")
    if doc.status != expected_status:
        raise HTTPException(
            status_code=400,
            detail=f"Biên bản đang ở trạng thái '{doc.status}', không thể thao tác bước {step_number} (cần '{expected_status}')",
        )

    # Nếu bước yêu cầu ký số → validate verify_token
    signature_url: Optional[str] = None
    if current_step_cfg.get("signatureRequired") and body.action != "reject":
        if not body.verify_token:
            raise HTTPException(
                status_code=400,
                detail="Bước này yêu cầu ký số. Vui lòng cung cấp verify_token từ OTP.",
            )
        if not body.actor_id:
            raise HTTPException(status_code=400, detail="actor_id là bắt buộc cho bước ký số")
        token_valid = await _verify_otp_token(body.actor_id, body.verify_token, db)
        if not token_valid:
            raise HTTPException(
                status_code=400,
                detail="verify_token không hợp lệ hoặc đã hết hạn. Vui lòng xác thực OTP lại.",
            )
        # Lấy ảnh chữ ký
        signature_url = await _get_signature_url(body.actor_id, db)

    actor_name, actor_title = await _resolve_actor(body.actor_id, body.actor_name, db)

    # Tính trạng thái mới
    new_status = _next_status(workflow, step_number, body.action)
    doc.status = new_status

    # Nếu hoàn thành → ghi completedAt
    if new_status == "COMPLETED":
        doc.completed_at = datetime.now(timezone.utc)

    # Append vào approval_logs
    logs = list(doc.approval_logs or [])

    # Tìm signerRoleKey từ signers config (match theo deptCode)
    signer_role_key = None
    dept_code = current_step_cfg.get("deptCode")
    if dept_code:
        matched_signer = next(
            (s for s in (doc.signers or []) if s.get("deptCodeFilter") == dept_code),
            None,
        )
        signer_role_key = matched_signer.get("roleKey") if matched_signer else None

    logs.append({
        "stepNumber": step_number,
        "action": body.action,
        "actorId": body.actor_id,
        "actorName": actor_name,
        "actorTitle": actor_title,
        "note": body.note,
        "signatureUrl": signature_url,
        "signerRoleKey": signer_role_key,
        "actionAt": _now_iso(),
        "statusAfter": new_status,
    })
    doc.approval_logs = logs
    flag_modified(doc, "approval_logs")

    await db.commit()
    await db.refresh(doc)
    return {"success": True, "data": _serialize(doc)}


# ── POST /{doc_id}/notify  Gửi thông báo ──────────────────────────────────────
@router.post("/{doc_id}/notify")
async def notify_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """
    Tạo notification cho những người được giao xử lý bước hiện tại.
    Ưu tiên: assignedUsers (người cụ thể) → fallback deptCode (theo phòng ban).
    """
    doc = await db.get(HrmDocument, doc_id)
    if not doc or doc.status in ("DRAFT", "COMPLETED", "REJECTED"):
        return {"success": False, "message": "Không cần notify ở trạng thái này"}

    current_step = next((s for s in (doc.workflow_steps or []) if s.get("statusPending") == doc.status), None)
    if not current_step:
        return {"success": False, "message": "Không tìm thấy bước hiện tại"}

    step_label = current_step.get("name") or current_step.get("label") or f"Bước {current_step.get('stepNumber', '?')}"
    title = f"Biên bản chờ xử lý: {doc.name}"
    message = f"Bạn được yêu cầu xử lý biên bản '{doc.name}' tại bước: {step_label}"
    link = f"/hrm/documents/{doc.id}"

    # Lấy assignedUsers từ bước hiện tại (người cụ thể được giao)
    assigned_users = current_step.get("assignedUsers") or []
    user_ids = [str(u.get("userId") or u.get("id", "")) for u in assigned_users if u.get("userId") or u.get("id")]

    # Nếu không có người cụ thể → fallback theo deptCode
    if not user_ids:
        dept_code = current_step.get("deptCode")
        if dept_code:
            stmt = select(User.portal_user_id).where(
                User.tenant_id == doc.tenant_id,
                (User.dept_code == dept_code) | (User.department == dept_code),
            )
            user_ids = [str(uid) for uid in (await db.execute(stmt)).scalars().all()]

    # Luôn notify người tạo biên bản (submittedBy) nếu không có ai được giao
    if not user_ids and doc.submitted_by:
        user_ids = [str(doc.submitted_by)]

    user_ids = [uid for uid in user_ids if uid]
    if not user_ids:
        return {"success": True, "notifications": []}

    from app.services.notification_service import create_broadcast_notification
    notifications = await create_broadcast_notification(
        db=db,
        tenant_id=doc.tenant_id,
        user_ids=user_ids,
        title=title,
        message=message,
        type="info",
        link=link,
    )

    return {
        "success": True,
        "notifications": [
            {
                "id": str(n.id),
                "user_id": n.user_id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "link": n.link,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
    }


# ── DELETE /{doc_id}  Xóa biên bản ──────────────────────────────────────────
@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(HrmDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy biên bản")

    # Chỉ cho xóa nếu là DRAFT hoặc chưa có ai phê duyệt (chỉ mới có submit log)
    # Lấy log actions khác 'submit'
    action_logs = [l for l in (doc.approval_logs or []) if l.get("action") not in ("submit", "create")]

    if action_logs:
        raise HTTPException(
            status_code=400,
            detail="Không thể xóa biên bản đã có người xử lý hoặc ký tên."
        )

    await db.delete(doc)
    await db.commit()
    return {"success": True, "message": "Đã xóa biên bản thành công"}

