"""
Email Recruitment — Phase 1 + 2: Core Inbox & Bulk Reply

Endpoints:
  Jobs        : GET/POST /recruitment/jobs, GET/PATCH/DELETE /recruitment/jobs/{id}
  Inbox       : GET /recruitment/inbox, GET /recruitment/inbox/{id},
                PATCH /recruitment/inbox/{id}, DELETE /recruitment/inbox/{id}
  Pull        : POST /recruitment/inbox/pull
  Bulk Reply  : POST /recruitment/bulk-reply
  Reply Hist. : GET /recruitment/replies, GET /recruitment/replies/{bulk_id}
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
import io
from pydantic import BaseModel
from sqlalchemy import select, func as sql_func, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.recruitment_model import CandidateEmail, RecruitmentJob, RecruitmentReply, RecruitmentAutoRule
from app.models.email_config_model import EmailConfig
from app.models.template_model import Template
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────

class JobCreate(BaseModel):
    title: str
    department: Optional[str] = None
    email_alias: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = "open"


class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    email_alias: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class InboxPatch(BaseModel):
    status: Optional[str] = None   # new | reviewing | shortlisted | rejected | replied
    is_read: Optional[bool] = None
    job_id: Optional[int] = None


class PullRequest(BaseModel):
    email_config_id: Optional[int] = None   # None → use default config
    job_id: Optional[int] = None            # auto-tag pulled emails to this job
    max_fetch: Optional[int] = 50
    folder: Optional[str] = "INBOX"         # IMAP folder to pull from


class BulkReplyRequest(BaseModel):
    # Danh sách candidate_email IDs cần reply
    candidate_ids: List[int]
    subject: str
    body_html: str
    # Dùng template thay vì body_html trực tiếp (ưu tiên template_id nếu có)
    template_id: Optional[int] = None
    # Config email gửi; None → dùng default
    email_config_id: Optional[int] = None
    from_name: Optional[str] = None
    # Tự động cập nhật status ứng viên sau khi gửi
    update_candidate_status: Optional[str] = None  # vd: "replied"
    # reply | forward | new — kiểu gửi, ảnh hưởng có quote nội dung gốc không
    reply_mode: Optional[str] = "reply"
    # Dùng khi reply_mode="forward": email đích nhận forward
    forward_to: Optional[str] = None


class AutoRuleCreate(BaseModel):
    name: str
    job_id: Optional[int] = None           # None = áp dụng cho mọi job
    trigger: Optional[str] = "on_receive"
    template_id: Optional[int] = None
    email_config_id: Optional[int] = None
    reply_subject: Optional[str] = None    # None = tự động "Re:..." hoặc "Fwd:..."
    body_html: Optional[str] = None
    from_name: Optional[str] = None
    delay_minutes: Optional[int] = 0
    is_active: Optional[bool] = True
    reply_type: Optional[str] = "reply"   # reply | forward


class AutoRuleUpdate(BaseModel):
    name: Optional[str] = None
    job_id: Optional[int] = None
    trigger: Optional[str] = None
    template_id: Optional[int] = None
    email_config_id: Optional[int] = None
    reply_subject: Optional[str] = None
    body_html: Optional[str] = None
    from_name: Optional[str] = None
    delay_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    reply_type: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────

def _job_out(j: RecruitmentJob) -> dict:
    return {
        "id": j.id,
        "title": j.title,
        "department": j.department,
        "email_alias": j.email_alias,
        "description": j.description,
        "status": j.status,
        "createdAt": j.created_at.isoformat() if j.created_at else None,
        "updatedAt": j.updated_at.isoformat() if j.updated_at else None,
    }


def _reply_out(r: RecruitmentReply) -> dict:
    return {
        "id": r.id,
        "candidateEmailId": r.candidate_email_id,
        "bulkId": r.bulk_id,
        "toEmail": r.to_email,
        "toName": r.to_name,
        "subject": r.subject,
        "status": r.status,
        "errorMessage": r.error_message,
        "sentAt": r.sent_at.isoformat() if r.sent_at else None,
        "templateId": r.template_id,
        "emailConfigId": r.email_config_id,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    }


def _rule_out(r: RecruitmentAutoRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "jobId": r.job_id,
        "trigger": r.trigger,
        "templateId": r.template_id,
        "emailConfigId": r.email_config_id,
        "replySubject": r.reply_subject,
        "replyType": r.reply_type or "reply",
        "fromName": r.from_name,
        "bodyHtml": r.body_html,
        "delayMinutes": r.delay_minutes,
        "isActive": r.is_active,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
        "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
    }


def _email_out(e: CandidateEmail, portal_user_id: str = "") -> dict:
    attachments = []
    if e.attachments:
        try:
            raw = json.loads(e.attachments)
            for att in raw:
                idx = att.get("attachmentIndex")
                if idx is not None and portal_user_id:
                    att["downloadUrl"] = (
                        f"/api/v1/recruitment/inbox/{e.id}/attachments/{idx}"
                        f"?portal_user_id={portal_user_id}"
                    )
                attachments.append(att)
        except Exception:
            pass
    return {
        "id": e.id,
        "jobId": e.job_id,
        "messageId": e.message_id,
        "fromEmail": e.from_email,
        "fromName": e.from_name,
        "subject": e.subject,
        "bodyText": e.body_text,
        "bodyHtml": e.body_html,
        "receivedAt": e.received_at.isoformat() if e.received_at else None,
        "status": e.status,
        "isRead": e.is_read,
        "attachments": attachments,
        "threadId": e.thread_id,
        "createdAt": e.created_at.isoformat() if e.created_at else None,
    }


async def _get_job_or_404(job_id: int, portal_user_id: str, db: AsyncSession) -> RecruitmentJob:
    result = await db.execute(
        select(RecruitmentJob).where(
            RecruitmentJob.id == job_id,
            RecruitmentJob.portal_user_id == portal_user_id,
            RecruitmentJob.is_active == True,
        )
    )
    j = result.scalar_one_or_none()
    if not j:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng")
    return j


async def _get_email_or_404(email_id: int, portal_user_id: str, db: AsyncSession) -> CandidateEmail:
    result = await db.execute(
        select(CandidateEmail).where(
            CandidateEmail.id == email_id,
            CandidateEmail.portal_user_id == portal_user_id,
        )
    )
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Không tìm thấy email ứng viên")
    return e


# ─── Job Endpoints ────────────────────────────────────────────────

@router.get("/recruitment/jobs")
async def list_jobs(
    portal_user_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RecruitmentJob).where(
        RecruitmentJob.portal_user_id == portal_user_id,
        RecruitmentJob.is_active == True,
    )
    if status:
        stmt = stmt.where(RecruitmentJob.status == status)
    stmt = stmt.order_by(RecruitmentJob.created_at.desc())
    result = await db.execute(stmt)
    jobs = result.scalars().all()

    # Count candidates per job
    count_result = await db.execute(
        select(CandidateEmail.job_id, sql_func.count(CandidateEmail.id))
        .where(CandidateEmail.portal_user_id == portal_user_id)
        .group_by(CandidateEmail.job_id)
    )
    count_map = {row[0]: row[1] for row in count_result.all()}

    data = []
    for j in jobs:
        out = _job_out(j)
        out["candidateCount"] = count_map.get(j.id, 0)
        data.append(out)

    return {"success": True, "data": data}


@router.post("/recruitment/jobs", status_code=201)
async def create_job(
    data: JobCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not data.title:
        raise HTTPException(status_code=422, detail="Tiêu đề vị trí là bắt buộc")
    j = RecruitmentJob(
        portal_user_id=portal_user_id,
        title=data.title,
        department=data.department,
        email_alias=data.email_alias,
        description=data.description,
        status=data.status or "open",
    )
    db.add(j)
    await db.commit()
    await db.refresh(j)
    return {"success": True, "data": _job_out(j)}


@router.get("/recruitment/jobs/{job_id}")
async def get_job(
    job_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    j = await _get_job_or_404(job_id, portal_user_id, db)
    return {"success": True, "data": _job_out(j)}


@router.patch("/recruitment/jobs/{job_id}")
async def update_job(
    job_id: int,
    data: JobUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    j = await _get_job_or_404(job_id, portal_user_id, db)
    if data.title is not None:
        j.title = data.title
    if data.department is not None:
        j.department = data.department
    if data.email_alias is not None:
        j.email_alias = data.email_alias
    if data.description is not None:
        j.description = data.description
    if data.status is not None:
        j.status = data.status
    await db.commit()
    await db.refresh(j)
    return {"success": True, "data": _job_out(j)}


@router.delete("/recruitment/jobs/{job_id}")
async def delete_job(
    job_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    j = await _get_job_or_404(job_id, portal_user_id, db)
    j.is_active = False
    await db.commit()
    return {"success": True}


# ─── Inbox Endpoints ──────────────────────────────────────────────

@router.get("/recruitment/inbox")
async def list_inbox(
    portal_user_id: str = Query(...),
    job_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CandidateEmail).where(
        CandidateEmail.portal_user_id == portal_user_id,
    )
    if job_id is not None:
        stmt = stmt.where(CandidateEmail.job_id == job_id)
    if status:
        stmt = stmt.where(CandidateEmail.status == status)
    if is_read is not None:
        stmt = stmt.where(CandidateEmail.is_read == is_read)
    if search:
        like = f"%{search}%"
        from sqlalchemy import or_
        stmt = stmt.where(or_(
            CandidateEmail.from_email.ilike(like),
            CandidateEmail.from_name.ilike(like),
            CandidateEmail.subject.ilike(like),
        ))

    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.order_by(CandidateEmail.received_at.desc().nullslast()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    emails = result.scalars().all()

    # Unread count
    unread_result = await db.execute(
        select(sql_func.count()).where(
            CandidateEmail.portal_user_id == portal_user_id,
            CandidateEmail.is_read == False,
        )
    )
    unread_count = unread_result.scalar()

    return {
        "success": True,
        "data": [_email_out(e, portal_user_id) for e in emails],
        "pagination": {"total": total, "page": page, "limit": limit},
        "unreadCount": unread_count,
    }


@router.get("/recruitment/inbox/{email_id}")
async def get_inbox_email(
    email_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    e = await _get_email_or_404(email_id, portal_user_id, db)
    # Auto-mark read on open
    if not e.is_read:
        e.is_read = True
        await db.commit()
        await db.refresh(e)

    # Fetch thread siblings
    thread = []
    if e.thread_id:
        thread_result = await db.execute(
            select(CandidateEmail).where(
                CandidateEmail.portal_user_id == portal_user_id,
                CandidateEmail.thread_id == e.thread_id,
                CandidateEmail.id != e.id,
            ).order_by(CandidateEmail.received_at.asc())
        )
        thread = [_email_out(t, portal_user_id) for t in thread_result.scalars().all()]

    return {"success": True, "data": _email_out(e, portal_user_id), "thread": thread}


@router.get("/recruitment/inbox/{email_id}/attachments/{attachment_index}")
async def download_attachment(
    email_id: int,
    attachment_index: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Stream một file đính kèm từ IMAP về client, không lưu trên server."""
    from app.services.imap_service import fetch_attachment_imap

    e = await _get_email_or_404(email_id, portal_user_id, db)
    if not e.message_id:
        raise HTTPException(status_code=404, detail="Email không có Message-ID")

    # Lấy email config của user
    cfg_result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
            EmailConfig.is_default == True,
        )
    )
    cfg = cfg_result.scalar_one_or_none()
    if not cfg:
        cfg_result = await db.execute(
            select(EmailConfig).where(
                EmailConfig.portal_user_id == portal_user_id,
                EmailConfig.is_active == True,
            ).limit(1)
        )
        cfg = cfg_result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=422, detail="Chưa cấu hình email")

    try:
        if cfg.provider == "gmail":
            imap_host, imap_port = "imap.gmail.com", 993
            username = cfg.gmail_address
            password = decrypt(cfg.gmail_app_password_enc) if cfg.gmail_app_password_enc else None
        else:
            imap_host = cfg.smtp_host
            imap_port = 993
            username = cfg.smtp_username
            password = decrypt(cfg.smtp_password_enc) if cfg.smtp_password_enc else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Lỗi giải mã thông tin đăng nhập")

    if not username or not password:
        raise HTTPException(status_code=422, detail="Thông tin đăng nhập email chưa đầy đủ")

    result = await fetch_attachment_imap(
        imap_host=imap_host,
        imap_port=imap_port,
        username=username,
        password=password,
        message_id=e.message_id,
        attachment_index=attachment_index,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file đính kèm")

    data, filename, mime_type = result
    safe_filename = filename.encode("utf-8").decode("latin-1", errors="replace")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{filename}',
        "Content-Length": str(len(data)),
    }
    return StreamingResponse(io.BytesIO(data), media_type=mime_type, headers=headers)


@router.patch("/recruitment/inbox/{email_id}")
async def patch_inbox_email(
    email_id: int,
    data: InboxPatch,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    e = await _get_email_or_404(email_id, portal_user_id, db)
    if data.status is not None:
        allowed = {"new", "reviewing", "shortlisted", "rejected", "replied"}
        if data.status not in allowed:
            raise HTTPException(status_code=422, detail=f"Status không hợp lệ. Chọn: {allowed}")
        e.status = data.status
    if data.is_read is not None:
        e.is_read = data.is_read
    if data.job_id is not None:
        e.job_id = data.job_id
    await db.commit()
    await db.refresh(e)
    return {"success": True, "data": _email_out(e, portal_user_id)}


@router.delete("/recruitment/inbox/{email_id}")
async def delete_inbox_email(
    email_id: int,
    portal_user_id: str = Query(...),
    delete_from_mail: bool = Query(False),  # xóa luôn trên Gmail/IMAP
    db: AsyncSession = Depends(get_db),
):
    e = await _get_email_or_404(email_id, portal_user_id, db)
    message_id = e.message_id

    await db.delete(e)
    await db.commit()

    # Xóa trên IMAP nếu được yêu cầu
    imap_deleted = False
    if delete_from_mail and message_id:
        try:
            cfg_result = await db.execute(
                select(EmailConfig).where(
                    EmailConfig.portal_user_id == portal_user_id,
                    EmailConfig.is_active == True,
                    EmailConfig.is_default == True,
                )
            )
            cfg = cfg_result.scalar_one_or_none()
            if not cfg:
                cfg_result = await db.execute(
                    select(EmailConfig).where(
                        EmailConfig.portal_user_id == portal_user_id,
                        EmailConfig.is_active == True,
                    ).limit(1)
                )
                cfg = cfg_result.scalar_one_or_none()

            if cfg:
                if cfg.provider == "gmail":
                    imap_host = "imap.gmail.com"
                    imap_port = 993
                    username = cfg.gmail_address
                    password = decrypt(cfg.gmail_app_password_enc) if cfg.gmail_app_password_enc else None
                else:
                    imap_host = cfg.smtp_host
                    imap_port = 993
                    username = cfg.smtp_username
                    password = decrypt(cfg.smtp_password_enc) if cfg.smtp_password_enc else None

                if username and password:
                    from app.services.imap_service import delete_email_imap
                    imap_deleted = await delete_email_imap(
                        imap_host=imap_host,
                        imap_port=imap_port,
                        username=username,
                        password=password,
                        message_id=message_id,
                    )
        except Exception as exc:
            logger.error(f"[RECRUITMENT] IMAP delete failed: {exc}")

    return {"success": True, "imapDeleted": imap_deleted}


class BulkDeleteRequest(BaseModel):
    ids: List[int]
    delete_from_mail: Optional[bool] = False


@router.post("/recruitment/inbox/bulk-delete")
async def bulk_delete_inbox_emails(
    body: BulkDeleteRequest,
    background_tasks: BackgroundTasks,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Xóa nhiều email cùng lúc. Nếu delete_from_mail=True thì xóa luôn trên IMAP trong background."""
    if not body.ids:
        raise HTTPException(status_code=422, detail="Cần ít nhất 1 ID để xóa")

    result = await db.execute(
        select(CandidateEmail).where(
            CandidateEmail.id.in_(body.ids),
            CandidateEmail.portal_user_id == portal_user_id,
        )
    )
    emails = result.scalars().all()
    if not emails:
        raise HTTPException(status_code=404, detail="Không tìm thấy email nào")

    message_ids = [e.message_id for e in emails if e.message_id]
    deleted_count = len(emails)

    for e in emails:
        await db.delete(e)
    await db.commit()

    # Xóa trên IMAP trong background nếu được yêu cầu
    if body.delete_from_mail and message_ids:
        try:
            cfg_result = await db.execute(
                select(EmailConfig).where(
                    EmailConfig.portal_user_id == portal_user_id,
                    EmailConfig.is_active == True,
                    EmailConfig.is_default == True,
                )
            )
            cfg = cfg_result.scalar_one_or_none()
            if not cfg:
                cfg_result = await db.execute(
                    select(EmailConfig).where(
                        EmailConfig.portal_user_id == portal_user_id,
                        EmailConfig.is_active == True,
                    ).limit(1)
                )
                cfg = cfg_result.scalar_one_or_none()

            if cfg:
                if cfg.provider == "gmail":
                    imap_creds = {
                        "imap_host": "imap.gmail.com",
                        "imap_port": 993,
                        "username": cfg.gmail_address,
                        "password": decrypt(cfg.gmail_app_password_enc) if cfg.gmail_app_password_enc else None,
                    }
                else:
                    imap_creds = {
                        "imap_host": cfg.smtp_host,
                        "imap_port": 993,
                        "username": cfg.smtp_username,
                        "password": decrypt(cfg.smtp_password_enc) if cfg.smtp_password_enc else None,
                    }
                if imap_creds.get("username") and imap_creds.get("password"):
                    background_tasks.add_task(_bulk_imap_delete_bg, imap_creds, message_ids)
        except Exception as exc:
            logger.error(f"[RECRUITMENT] bulk imap delete setup failed: {exc}")

    return {"success": True, "deleted": deleted_count}


async def _bulk_imap_delete_bg(imap_creds: dict, message_ids: list[str]):
    """Background: xóa từng email trên IMAP theo message_id."""
    from app.services.imap_service import delete_email_imap
    success = 0
    for mid in message_ids:
        ok = await delete_email_imap(
            imap_host=imap_creds["imap_host"],
            imap_port=imap_creds["imap_port"],
            username=imap_creds["username"],
            password=imap_creds["password"],
            message_id=mid,
        )
        if ok:
            success += 1
    logger.info(f"[RECRUITMENT BG] bulk imap delete: {success}/{len(message_ids)} deleted")


# ─── Pull Endpoint ────────────────────────────────────────────────

@router.post("/recruitment/inbox/pull")
async def pull_inbox(
    body: PullRequest,
    background_tasks: BackgroundTasks,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Kéo email mới từ Gmail/IMAP vào inbox ứng viên (async background).
    Trả về ngay lập tức với job_id, frontend poll để lấy kết quả.
    """
    # Resolve email config
    if body.email_config_id:
        cfg_result = await db.execute(
            select(EmailConfig).where(
                EmailConfig.id == body.email_config_id,
                EmailConfig.portal_user_id == portal_user_id,
                EmailConfig.is_active == True,
            )
        )
        cfg = cfg_result.scalar_one_or_none()
    else:
        cfg_result = await db.execute(
            select(EmailConfig).where(
                EmailConfig.portal_user_id == portal_user_id,
                EmailConfig.is_active == True,
                EmailConfig.is_default == True,
            )
        )
        cfg = cfg_result.scalar_one_or_none()
        if not cfg:
            cfg_result = await db.execute(
                select(EmailConfig).where(
                    EmailConfig.portal_user_id == portal_user_id,
                    EmailConfig.is_active == True,
                ).limit(1)
            )
            cfg = cfg_result.scalar_one_or_none()

    if not cfg:
        raise HTTPException(
            status_code=422,
            detail="Chưa cấu hình email. Vui lòng thêm Email Config trước.",
        )

    # Decrypt credentials
    try:
        if cfg.provider == "gmail":
            username = cfg.gmail_address
            password = decrypt(cfg.gmail_app_password_enc) if cfg.gmail_app_password_enc else None
            imap_host = "imap.gmail.com"
            imap_port = 993
        else:
            username = cfg.smtp_username
            password = decrypt(cfg.smtp_password_enc) if cfg.smtp_password_enc else None
            imap_host = cfg.smtp_host
            imap_port = 993
    except Exception as exc:
        logger.error(f"[RECRUITMENT] Decrypt credentials failed: {exc}")
        raise HTTPException(status_code=500, detail="Lỗi giải mã thông tin đăng nhập email")

    if not username or not password:
        raise HTTPException(status_code=422, detail="Thông tin đăng nhập email chưa đầy đủ")

    pull_params = {
        "imap_host": imap_host,
        "imap_port": imap_port,
        "username": username,
        "password": password,
        "folder": body.folder or "INBOX",
        "max_fetch": body.max_fetch or 50,
        "job_id": body.job_id,
        "portal_user_id": portal_user_id,
    }

    # Chạy trong background để tránh timeout
    background_tasks.add_task(_pull_inbox_bg, pull_params)

    return {
        "success": True,
        "data": {
            "message": "Đang kéo email trong nền. Vui lòng refresh sau vài giây.",
            "folder": body.folder or "INBOX",
            "maxFetch": body.max_fetch or 50,
        },
    }


def _detect_job_from_subject(subject: str, jobs: list) -> Optional[int]:
    """
    So khớp subject email với title của các job đang mở.
    Ưu tiên match dài nhất (tránh "Developer" match trước "Frontend Developer").
    Trả về job_id nếu tìm thấy, None nếu không khớp.
    """
    if not subject or not jobs:
        return None
    subject_lower = subject.lower()
    best_id = None
    best_len = 0
    for job in jobs:
        title = (job.title or "").strip()
        if not title:
            continue
        if title.lower() in subject_lower and len(title) > best_len:
            best_id = job.id
            best_len = len(title)
    return best_id


async def _pull_inbox_bg(params: dict):
    """Background task: kéo IMAP và lưu vào DB."""
    from app.db.database import AsyncSessionLocal
    from app.services.imap_service import pull_emails_imap
    from app.services.auto_reply_service import trigger_auto_reply

    portal_user_id = params["portal_user_id"]
    fallback_job_id = params.get("job_id")  # job chọn thủ công trong Pull Modal

    try:
        raw_emails = await pull_emails_imap(
            imap_host=params["imap_host"],
            imap_port=params["imap_port"],
            username=params["username"],
            password=params["password"],
            folder=params["folder"],
            max_fetch=params["max_fetch"],
        )
    except Exception as exc:
        logger.error(f"[RECRUITMENT BG] IMAP pull failed: {exc}")
        return

    async with AsyncSessionLocal() as db:
        # Load danh sách job đang mở để auto-detect từ subject
        jobs_result = await db.execute(
            select(RecruitmentJob).where(
                RecruitmentJob.portal_user_id == portal_user_id,
                RecruitmentJob.is_active == True,
                RecruitmentJob.status == "open",
            )
        )
        open_jobs = jobs_result.scalars().all()

        saved = 0
        skipped = 0
        new_candidates: list[CandidateEmail] = []

        for raw in raw_emails:
            if raw.get("message_id"):
                dup = await db.execute(
                    select(CandidateEmail).where(
                        CandidateEmail.message_id == raw["message_id"]
                    )
                )
                if dup.scalar_one_or_none():
                    skipped += 1
                    continue

            # Ưu tiên: auto-detect từ subject → fallback về job chọn thủ công
            subject = raw.get("subject") or ""
            detected_job_id = _detect_job_from_subject(subject, open_jobs)
            resolved_job_id = detected_job_id if detected_job_id is not None else fallback_job_id

            if detected_job_id:
                matched = next(j for j in open_jobs if j.id == detected_job_id)
                logger.info(f"[RECRUITMENT BG] Auto-detect job: '{matched.title}' ← subject='{subject}'")
            elif fallback_job_id:
                logger.info(f"[RECRUITMENT BG] Fallback job_id={fallback_job_id} ← subject='{subject}'")
            else:
                logger.info(f"[RECRUITMENT BG] No job matched ← subject='{subject}'")

            candidate = CandidateEmail(
                portal_user_id=portal_user_id,
                job_id=resolved_job_id,
                message_id=raw.get("message_id"),
                from_email=raw["from_email"],
                from_name=raw.get("from_name"),
                subject=subject,
                body_text=raw.get("body_text"),
                body_html=raw.get("body_html"),
                received_at=raw.get("received_at"),
                thread_id=raw.get("thread_id"),
                attachments=raw.get("attachments", "[]"),
                status="new",
                is_read=False,
            )
            db.add(candidate)
            saved += 1
            new_candidates.append(candidate)

        await db.commit()

        triggered = 0
        for cand in new_candidates:
            await db.refresh(cand)
            triggered += await trigger_auto_reply(
                portal_user_id=portal_user_id,
                candidate=cand,
                job_id=cand.job_id,  # dùng job_id đã được resolve (detected hoặc fallback)
            )

        logger.info(f"[RECRUITMENT BG] Pull done: saved={saved}, skipped={skipped}, auto_rules={triggered}")


# ─── Stats ────────────────────────────────────────────────────────

@router.get("/recruitment/stats")
async def get_stats(
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Tổng quan inbox: tổng ứng viên, phân bổ theo status, theo job."""
    # Total by status
    status_result = await db.execute(
        select(CandidateEmail.status, sql_func.count(CandidateEmail.id))
        .where(CandidateEmail.portal_user_id == portal_user_id)
        .group_by(CandidateEmail.status)
    )
    by_status = {row[0]: row[1] for row in status_result.all()}

    # Total
    total = sum(by_status.values())

    # Unread
    unread_result = await db.execute(
        select(sql_func.count()).where(
            CandidateEmail.portal_user_id == portal_user_id,
            CandidateEmail.is_read == False,
        )
    )
    unread = unread_result.scalar()

    # Open jobs count
    jobs_result = await db.execute(
        select(sql_func.count()).where(
            RecruitmentJob.portal_user_id == portal_user_id,
            RecruitmentJob.status == "open",
            RecruitmentJob.is_active == True,
        )
    )
    open_jobs = jobs_result.scalar()

    # Active auto-rules count
    rules_result = await db.execute(
        select(sql_func.count()).where(
            RecruitmentAutoRule.portal_user_id == portal_user_id,
            RecruitmentAutoRule.is_active == True,
        )
    )
    active_rules = rules_result.scalar()

    # Candidates per job (join với job title)
    by_job_result = await db.execute(
        select(
            RecruitmentJob.id,
            RecruitmentJob.title,
            RecruitmentJob.status.label("job_status"),
            sql_func.count(CandidateEmail.id).label("candidate_count"),
            sql_func.sum(
                sql_func.cast(CandidateEmail.is_read == False, Integer)
            ).label("unread_count"),
        )
        .outerjoin(
            CandidateEmail,
            (CandidateEmail.job_id == RecruitmentJob.id) &
            (CandidateEmail.portal_user_id == portal_user_id),
        )
        .where(
            RecruitmentJob.portal_user_id == portal_user_id,
            RecruitmentJob.is_active == True,
        )
        .group_by(RecruitmentJob.id, RecruitmentJob.title, RecruitmentJob.status)
        .order_by(sql_func.count(CandidateEmail.id).desc())
    )
    by_job = [
        {
            "jobId": row.id,
            "jobTitle": row.title,
            "jobStatus": row.job_status,
            "candidateCount": row.candidate_count or 0,
            "unreadCount": row.unread_count or 0,
        }
        for row in by_job_result.all()
    ]

    # Reply rate: tổng sent / tổng candidates
    total_sent_result = await db.execute(
        select(sql_func.count()).where(
            RecruitmentReply.portal_user_id == portal_user_id,
            RecruitmentReply.status == "sent",
        )
    )
    total_sent_replies = total_sent_result.scalar()
    reply_rate = round(total_sent_replies / total * 100, 1) if total > 0 else 0

    return {
        "success": True,
        "data": {
            "total": total,
            "unread": unread,
            "openJobs": open_jobs,
            "activeAutoRules": active_rules,
            "replyRate": reply_rate,
            "byStatus": {
                "new": by_status.get("new", 0),
                "reviewing": by_status.get("reviewing", 0),
                "shortlisted": by_status.get("shortlisted", 0),
                "rejected": by_status.get("rejected", 0),
                "replied": by_status.get("replied", 0),
            },
            "byJob": by_job,
        },
    }


# ─── Bulk Reply Endpoints ─────────────────────────────────────────

async def _resolve_email_config(portal_user_id: str, config_id: Optional[int], db: AsyncSession):
    """Lấy EmailConfig theo ID hoặc fallback về default."""
    if config_id:
        result = await db.execute(
            select(EmailConfig).where(
                EmailConfig.id == config_id,
                EmailConfig.portal_user_id == portal_user_id,
                EmailConfig.is_active == True,
            )
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(status_code=404, detail="Không tìm thấy email config chỉ định")
        return cfg

    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
            EmailConfig.is_default == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if cfg:
        return cfg

    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        ).limit(1)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(
            status_code=422,
            detail="Chưa cấu hình email. Vui lòng thêm Email Config trước.",
        )
    return cfg


@router.post("/recruitment/bulk-reply", status_code=202)
async def bulk_reply(
    body: BulkReplyRequest,
    background_tasks: BackgroundTasks,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Gửi email phản hồi hàng loạt tới nhiều ứng viên.

    - Lấy danh sách candidate_ids → resolve email + tên từ CandidateEmail
    - Nếu có template_id → lấy html_snapshot làm nội dung
    - Tạo các bản ghi RecruitmentReply (pending) trước, gửi tuần tự, cập nhật status
    - Trả về kết quả { sent, failed, total, bulkId }
    """
    if not body.candidate_ids:
        raise HTTPException(status_code=422, detail="Cần ít nhất 1 ứng viên để gửi")
    if len(body.candidate_ids) > 500:
        raise HTTPException(status_code=422, detail="Tối đa 500 ứng viên mỗi lần gửi")

    cfg = await _resolve_email_config(portal_user_id, body.email_config_id, db)

    # Resolve body_html: ưu tiên template
    body_html = body.body_html
    template_id = body.template_id
    if template_id:
        tpl_result = await db.execute(
            select(Template).where(
                Template.id == template_id,
                Template.portal_user_id == portal_user_id,
                Template.is_active == True,
            )
        )
        tpl = tpl_result.scalar_one_or_none()
        if not tpl:
            raise HTTPException(status_code=404, detail="Không tìm thấy template")
        if tpl.html_snapshot:
            body_html = tpl.html_snapshot
        elif not body_html:
            raise HTTPException(status_code=422, detail="Template chưa có nội dung HTML")

    if not body_html:
        raise HTTPException(status_code=422, detail="body_html là bắt buộc")
    if not body.subject:
        raise HTTPException(status_code=422, detail="subject là bắt buộc")

    # Fetch candidate emails
    candidates_result = await db.execute(
        select(CandidateEmail).where(
            CandidateEmail.id.in_(body.candidate_ids),
            CandidateEmail.portal_user_id == portal_user_id,
        )
    )
    candidates = candidates_result.scalars().all()

    if not candidates:
        raise HTTPException(status_code=404, detail="Không tìm thấy ứng viên nào khớp")

    bulk_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Tạo reply records (pending) trước khi gửi
    reply_map: dict[int, RecruitmentReply] = {}
    for c in candidates:
        reply = RecruitmentReply(
            portal_user_id=portal_user_id,
            candidate_email_id=c.id,
            bulk_id=bulk_id,
            sent_by=portal_user_id,
            email_config_id=cfg.id,
            template_id=template_id,
            to_email=c.from_email,
            to_name=c.from_name or "",
            subject=body.subject,
            body_html=body_html,
            status="pending",
        )
        db.add(reply)
        reply_map[c.id] = reply

    await db.commit()
    for r in reply_map.values():
        await db.refresh(r)

    # Build recipients list cho service (kèm nội dung gốc để quote nếu reply/forward)
    recipients = [
        {
            "to_email": c.from_email,
            "to_name": c.from_name or "",
            "candidate_email_id": c.id,
            "message_id": c.message_id,
            "original_subject": c.subject or "",
            "original_from": c.from_name or c.from_email or "",
            "original_from_email": c.from_email or "",
            "original_received_at": c.received_at.isoformat() if c.received_at else "",
            "original_body_html": c.body_html or "",
            "original_body_text": c.body_text or "",
        }
        for c in candidates
    ]

    # Chạy gửi mail trong background để tránh timeout
    update_status = body.update_candidate_status
    bg_params = {
        "cfg_id": cfg.id,
        "portal_user_id": portal_user_id,
        "reply_ids": [r.id for r in reply_map.values()],
        "candidate_ids_map": {c.id: r.id for c, r in zip(candidates, reply_map.values())},
        "recipients": recipients,
        "subject": body.subject,
        "body_html": body_html,
        "from_name": body.from_name or cfg.sender_name or "",
        "update_candidate_status": update_status,
        "bulk_id": bulk_id,
        "reply_mode": body.reply_mode or "reply",
        "forward_to": body.forward_to or None,
    }
    background_tasks.add_task(_bulk_reply_bg, bg_params)

    return {
        "success": True,
        "data": {
            "bulkId": bulk_id,
            "sent": 0,
            "failed": 0,
            "total": len(candidates),
            "message": "Đang gửi trong nền. Kiểm tra lịch sử gửi sau vài giây.",
        },
    }


async def _bulk_reply_bg(params: dict):
    """Background task: gửi bulk reply và cập nhật status."""
    from app.db.database import AsyncSessionLocal
    from app.services.recruitment_email_service import send_bulk_replies

    portal_user_id = params["portal_user_id"]
    bulk_id = params["bulk_id"]

    async with AsyncSessionLocal() as db:
        # Load config
        cfg_result = await db.execute(
            select(EmailConfig).where(EmailConfig.id == params["cfg_id"])
        )
        cfg = cfg_result.scalar_one_or_none()
        if not cfg:
            logger.error(f"[RECRUITMENT BG] EmailConfig {params['cfg_id']} not found")
            return

        # Load replies
        reply_result = await db.execute(
            select(RecruitmentReply).where(
                RecruitmentReply.bulk_id == bulk_id,
                RecruitmentReply.portal_user_id == portal_user_id,
            )
        )
        reply_map = {r.candidate_email_id: r for r in reply_result.scalars().all()}

        # Load candidates
        cand_result = await db.execute(
            select(CandidateEmail).where(
                CandidateEmail.id.in_(list(reply_map.keys())),
                CandidateEmail.portal_user_id == portal_user_id,
            )
        )
        candidates = {c.id: c for c in cand_result.scalars().all()}

        async def on_result(candidate_email_id, status, error):
            reply = reply_map.get(candidate_email_id)
            if reply:
                reply.status = status
                reply.error_message = error
                reply.sent_at = datetime.now(timezone.utc) if status == "sent" else None
            if status == "sent" and params.get("update_candidate_status"):
                cand = candidates.get(candidate_email_id)
                if cand:
                    cand.status = params["update_candidate_status"]
            await db.commit()

        await send_bulk_replies(
            cfg=cfg,
            recipients=params["recipients"],
            subject=params["subject"],
            body_html=params["body_html"],
            from_name=params["from_name"],
            on_result=on_result,
            reply_mode=params.get("reply_mode", "reply"),
            forward_to=params.get("forward_to"),
        )
        logger.info(f"[RECRUITMENT BG] bulk_reply done: bulk_id={bulk_id}")


@router.get("/recruitment/replies")
async def list_replies(
    portal_user_id: str = Query(...),
    bulk_id: Optional[str] = Query(None),
    candidate_email_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Lịch sử các lần gửi bulk reply."""
    stmt = select(RecruitmentReply).where(
        RecruitmentReply.portal_user_id == portal_user_id,
    )
    if bulk_id:
        stmt = stmt.where(RecruitmentReply.bulk_id == bulk_id)
    if candidate_email_id:
        stmt = stmt.where(RecruitmentReply.candidate_email_id == candidate_email_id)
    if status:
        stmt = stmt.where(RecruitmentReply.status == status)

    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.order_by(RecruitmentReply.created_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    replies = result.scalars().all()

    return {
        "success": True,
        "data": [_reply_out(r) for r in replies],
        "pagination": {"total": total, "page": page, "limit": limit},
    }


@router.get("/recruitment/replies/bulk/{bulk_id}")
async def get_bulk_detail(
    bulk_id: str,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Chi tiết 1 batch gửi: danh sách từng recipient + status."""
    result = await db.execute(
        select(RecruitmentReply).where(
            RecruitmentReply.bulk_id == bulk_id,
            RecruitmentReply.portal_user_id == portal_user_id,
        ).order_by(RecruitmentReply.created_at.asc())
    )
    replies = result.scalars().all()
    if not replies:
        raise HTTPException(status_code=404, detail="Không tìm thấy bulk batch này")

    sent = sum(1 for r in replies if r.status == "sent")
    failed = sum(1 for r in replies if r.status == "failed")

    return {
        "success": True,
        "data": {
            "bulkId": bulk_id,
            "total": len(replies),
            "sent": sent,
            "failed": failed,
            "subject": replies[0].subject,
            "createdAt": replies[0].created_at.isoformat() if replies[0].created_at else None,
            "recipients": [_reply_out(r) for r in replies],
        },
    }


# ─── Auto-Reply Rule Endpoints ────────────────────────────────────

async def _get_rule_or_404(rule_id: int, portal_user_id: str, db: AsyncSession) -> RecruitmentAutoRule:
    result = await db.execute(
        select(RecruitmentAutoRule).where(
            RecruitmentAutoRule.id == rule_id,
            RecruitmentAutoRule.portal_user_id == portal_user_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Không tìm thấy auto-reply rule")
    return r


@router.get("/recruitment/auto-rules")
async def list_auto_rules(
    portal_user_id: str = Query(...),
    job_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RecruitmentAutoRule).where(
        RecruitmentAutoRule.portal_user_id == portal_user_id,
    )
    if job_id is not None:
        stmt = stmt.where(RecruitmentAutoRule.job_id == job_id)
    if is_active is not None:
        stmt = stmt.where(RecruitmentAutoRule.is_active == is_active)
    stmt = stmt.order_by(RecruitmentAutoRule.created_at.desc())
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return {"success": True, "data": [_rule_out(r) for r in rules]}


@router.post("/recruitment/auto-rules", status_code=201)
async def create_auto_rule(
    data: AutoRuleCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not data.name:
        raise HTTPException(status_code=422, detail="Tên rule là bắt buộc")
    if not data.template_id and not data.body_html:
        raise HTTPException(status_code=422, detail="Cần template_id hoặc body_html")

    r = RecruitmentAutoRule(
        portal_user_id=portal_user_id,
        name=data.name,
        job_id=data.job_id,
        trigger=data.trigger or "on_receive",
        template_id=data.template_id,
        email_config_id=data.email_config_id,
        reply_subject=data.reply_subject,
        body_html=data.body_html,
        from_name=data.from_name,
        delay_minutes=data.delay_minutes or 0,
        is_active=data.is_active if data.is_active is not None else True,
        reply_type=data.reply_type or "reply",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"success": True, "data": _rule_out(r)}


@router.get("/recruitment/auto-rules/{rule_id}")
async def get_auto_rule(
    rule_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    r = await _get_rule_or_404(rule_id, portal_user_id, db)
    return {"success": True, "data": _rule_out(r)}


@router.patch("/recruitment/auto-rules/{rule_id}")
async def update_auto_rule(
    rule_id: int,
    data: AutoRuleUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    r = await _get_rule_or_404(rule_id, portal_user_id, db)
    if data.name is not None:
        r.name = data.name
    if data.job_id is not None:
        r.job_id = data.job_id
    if data.trigger is not None:
        r.trigger = data.trigger
    if data.template_id is not None:
        r.template_id = data.template_id
    if data.email_config_id is not None:
        r.email_config_id = data.email_config_id
    if data.reply_subject is not None:
        r.reply_subject = data.reply_subject
    if data.body_html is not None:
        r.body_html = data.body_html
    if data.from_name is not None:
        r.from_name = data.from_name
    if data.delay_minutes is not None:
        r.delay_minutes = data.delay_minutes
    if data.is_active is not None:
        r.is_active = data.is_active
    if data.reply_type is not None:
        r.reply_type = data.reply_type
    await db.commit()
    await db.refresh(r)
    return {"success": True, "data": _rule_out(r)}


@router.delete("/recruitment/auto-rules/{rule_id}")
async def delete_auto_rule(
    rule_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    r = await _get_rule_or_404(rule_id, portal_user_id, db)
    await db.delete(r)
    await db.commit()
    return {"success": True}


@router.post("/recruitment/auto-rules/{rule_id}/toggle")
async def toggle_auto_rule(
    rule_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Bật/tắt nhanh 1 rule mà không cần PATCH toàn bộ."""
    r = await _get_rule_or_404(rule_id, portal_user_id, db)
    r.is_active = not r.is_active
    await db.commit()
    await db.refresh(r)
    return {"success": True, "data": {"id": r.id, "isActive": r.is_active}}
