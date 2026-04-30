import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sql_func
from pydantic import BaseModel

from app.db.database import get_db
from app.models.campaign_model import Campaign
from app.models.email_list_model import EmailList, Subscriber
from app.models.email_config_model import EmailConfig

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────

class SenderSchema(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    replyTo: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None


class CampaignCreate(BaseModel):
    name: str
    subject: str
    preheader: Optional[str] = None
    sender: Optional[SenderSchema] = None
    emailListIds: Optional[List[Any]] = None
    templateId: Optional[Any] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    preheader: Optional[str] = None
    sender: Optional[SenderSchema] = None
    emailListIds: Optional[List[Any]] = None
    templateId: Optional[Any] = None


class SendRequest(BaseModel):
    mode: Optional[str] = "multi"                  # "multi" | "single"
    excludedConfigIds: Optional[List[Any]] = None
    senderName: Optional[str] = None
    manualDistribution: Optional[dict] = None


class ValidateCapacityRequest(BaseModel):
    recipientCount: int
    mode: Optional[str] = "multi"
    excludedConfigIds: Optional[List[Any]] = None


# ─── Helpers ──────────────────────────────────────────────────────

def _to_response(c: Campaign) -> dict:
    sender = None
    if c.sender:
        try:
            sender = json.loads(c.sender)
        except Exception:
            sender = None

    email_list_ids = []
    if c.email_list_ids:
        try:
            email_list_ids = json.loads(c.email_list_ids)
        except Exception:
            email_list_ids = []

    recipients = []
    if c.recipients:
        try:
            recipients = json.loads(c.recipients)
        except Exception:
            recipients = []

    return {
        "_id": c.id,
        "name": c.name,
        "subject": c.subject,
        "preheader": c.preheader,
        "sender": sender,
        "emailListIds": email_list_ids,
        "templateId": c.template_id,
        "status": c.status,
        "stats": {
            "totalRecipients": len(recipients),
            "sentCount": c.sent_count,
            "openCount": c.open_count,
        },
        "resendCount": c.resend_count,
        "createdAt": c.created_at.isoformat() if c.created_at else None,
        "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
    }


async def _get_campaign_or_404(campaign_id: int, portal_user_id: str, db: AsyncSession) -> Campaign:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.portal_user_id == portal_user_id,
            Campaign.is_active == True,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Không tìm thấy campaign")
    return c


# ─── Endpoints ────────────────────────────────────────────────────

@router.get("/campaigns/dashboard")
async def get_campaign_dashboard(
    portal_user_id: str = Query(...),
    dateRange: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Thống kê tổng hợp campaigns trong khoảng thời gian dateRange ngày.
    Trả về totals + danh sách 10 campaigns gần nhất kèm open/click rate.
    """
    since = datetime.now(timezone.utc) - timedelta(days=dateRange)

    result = await db.execute(
        select(Campaign).where(
            Campaign.portal_user_id == portal_user_id,
            Campaign.is_active == True,
            Campaign.created_at >= since,
        ).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    total_campaigns = len(campaigns)
    total_sent = 0
    total_opened = 0
    total_clicked = 0   # placeholder — chưa track clicks
    total_bounced = 0   # placeholder — chưa track bounces

    recent_list = []
    for c in campaigns:
        recipients = []
        if c.recipients:
            try:
                recipients = json.loads(c.recipients)
            except Exception:
                recipients = []

        sent = c.sent_count or len(recipients)
        opened = c.open_count or sum(1 for r in recipients if r.get("opened"))
        open_rate = round(opened / sent * 100, 1) if sent > 0 else 0

        total_sent += sent
        total_opened += opened

        recent_list.append({
            "_id": c.id,
            "name": c.name,
            "status": c.status,
            "createdAt": c.created_at.isoformat() if c.created_at else None,
            "stats": {
                "totalRecipients": sent,
                "sentCount": sent,
                "openCount": opened,
                "openRate": open_rate,
                "clickRate": 0,
            },
        })

    # Tính avg open rate qua tất cả campaigns có gửi
    campaigns_with_sends = [c for c in recent_list if c["stats"]["totalRecipients"] > 0]
    avg_open_rate = (
        round(sum(c["stats"]["openRate"] for c in campaigns_with_sends) / len(campaigns_with_sends), 1)
        if campaigns_with_sends else 0
    )

    return {
        "success": True,
        "data": {
            "totals": {
                "totalCampaigns": total_campaigns,
                "totalSent": total_sent,
                "totalOpened": total_opened,
                "totalClicked": total_clicked,
                "totalBounced": total_bounced,
                "avgOpenRate": avg_open_rate,
                "avgClickRate": 0,
            },
            "recentCampaigns": recent_list[:10],
        },
    }


@router.get("/campaigns")
async def list_campaigns(
    portal_user_id: str = Query(...),
    limit: int = Query(20, ge=1, le=200),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Campaign)
        .where(Campaign.portal_user_id == portal_user_id, Campaign.is_active == True)
        .order_by(Campaign.created_at.desc())
    )

    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    campaigns = result.scalars().all()

    return {
        "success": True,
        "data": [_to_response(c) for c in campaigns],
        "pagination": {"total": total, "page": page, "limit": limit},
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)
    return {"success": True, "data": _to_response(c)}


@router.post("/campaigns", status_code=201)
async def create_campaign(
    data: CampaignCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not data.name or not data.subject:
        raise HTTPException(status_code=422, detail="Tên và tiêu đề campaign là bắt buộc")

    c = Campaign(
        portal_user_id=portal_user_id,
        name=data.name,
        subject=data.subject,
        preheader=data.preheader,
        sender=json.dumps(data.sender.dict()) if data.sender else None,
        email_list_ids=json.dumps([str(i) for i in (data.emailListIds or [])]),
        template_id=str(data.templateId) if data.templateId else None,
        status="draft",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"success": True, "data": _to_response(c)}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)

    if data.name is not None:
        c.name = data.name
    if data.subject is not None:
        c.subject = data.subject
    if data.preheader is not None:
        c.preheader = data.preheader
    if data.sender is not None:
        c.sender = json.dumps(data.sender.dict())
    if data.emailListIds is not None:
        c.email_list_ids = json.dumps([str(i) for i in data.emailListIds])
    if data.templateId is not None:
        c.template_id = str(data.templateId)

    await db.commit()
    await db.refresh(c)
    return {"success": True, "data": _to_response(c)}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)
    c.is_active = False
    await db.commit()
    return {"success": True}


@router.post("/campaigns/{campaign_id}/load-recipients")
async def load_recipients(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Thu thập danh sách người nhận từ các email lists của campaign."""
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)

    list_ids = []
    if c.email_list_ids:
        try:
            list_ids = [int(i) for i in json.loads(c.email_list_ids)]
        except Exception:
            list_ids = []

    if not list_ids:
        raise HTTPException(status_code=422, detail="Campaign không có email list nào")

    # Collect unique active subscribers
    result = await db.execute(
        select(Subscriber.email, Subscriber.name).where(
            Subscriber.list_id.in_(list_ids),
            Subscriber.is_active == True,
        ).distinct()
    )
    rows = result.all()
    recipients = [{"to": r[0], "name": r[1], "opened": False, "openCount": 0, "sentAt": None, "firstOpenedAt": None} for r in rows]

    c.recipients = json.dumps(recipients)
    await db.commit()

    return {"success": True, "data": {"recipientCount": len(recipients)}}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    body: SendRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Đánh dấu campaign là 'sending'.
    Việc gửi email thực tế được xử lý bởi enterprise-redis worker.
    """
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)

    if c.status == "sending":
        raise HTTPException(status_code=422, detail="Campaign đang được gửi")

    recipients_raw = []
    if c.recipients:
        try:
            recipients_raw = json.loads(c.recipients)
        except Exception:
            recipients_raw = []

    if not recipients_raw:
        raise HTTPException(status_code=422, detail="Chưa load recipients. Gọi /load-recipients trước.")

    c.status = "sending"
    c.resend_count = (c.resend_count or 0) + 1
    await db.commit()

    return {
        "success": True,
        "data": {
            "campaignId": c.id,
            "status": "sending",
            "recipientCount": len(recipients_raw),
            "mode": body.mode,
        },
    }


@router.get("/campaigns/{campaign_id}/tracking-data")
async def get_tracking_data(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lấy dữ liệu tracking (opened/not opened) của campaign."""
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)

    recipients = []
    if c.recipients:
        try:
            recipients = json.loads(c.recipients)
        except Exception:
            recipients = []

    return {"success": True, "data": recipients}


@router.post("/email-config/validate-capacity")
async def validate_capacity(
    body: ValidateCapacityRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Kiểm tra số lượng email config đang hoạt động có đủ capacity để gửi.
    Trả về distribution plan cho FE hiển thị.
    """
    excluded = [str(i) for i in (body.excludedConfigIds or [])]

    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        ).order_by(EmailConfig.is_default.desc())
    )
    all_configs = result.scalars().all()

    # Filter out excluded
    available_configs = [c for c in all_configs if str(c.id) not in excluded]

    if body.mode == "single":
        default_cfg = next((c for c in available_configs if c.is_default), None)
        if not default_cfg:
            default_cfg = available_configs[0] if available_configs else None
        if not default_cfg:
            return {"success": False, "message": "Không có email config mặc định"}
        available_configs = [default_cfg]

    if not available_configs:
        return {"success": False, "message": "Không có email config nào khả dụng", "shortage": 1}

    # Distribute evenly
    n = len(available_configs)
    per_config = body.recipientCount // n
    remainder = body.recipientCount % n

    distribution = []
    for i, cfg in enumerate(available_configs):
        will_send = per_config + (1 if i < remainder else 0)
        distribution.append({
            "emailConfigId": str(cfg.id),
            "name": cfg.name,
            "email": cfg.sender_email,
            "willSend": will_send,
        })

    return {
        "success": True,
        "totalRecipients": body.recipientCount,
        "availableConfigs": n,
        "distribution": distribution,
    }
