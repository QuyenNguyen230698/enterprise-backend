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
from app.models.template_model import Template

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

def _to_response(c: Campaign, lists_data=None, template_data=None) -> dict:
    recipients = []
    if c.recipients:
        try:
            recipients = json.loads(c.recipients)
        except Exception:
            recipients = []
            
    sender_data = None
    if c.sender:
        try:
            sender_data = json.loads(c.sender)
        except Exception:
            sender_data = None
    sent_count = c.sent_count or len(recipients)
    open_count = c.open_count or sum(1 for r in recipients if r.get("opened"))
    open_rate = round(open_count / sent_count * 100, 1) if sent_count > 0 else 0
    click_count = 0 # Not tracked yet
    click_rate = 0
    
    return {
        "_id": c.id,
        "name": c.name,
        "subject": c.subject,
        "preheader": c.preheader,
        "sender": sender_data,
        "emailListIds": lists_data if lists_data is not None else (c.email_list_ids or []),
        "templateId": template_data if template_data is not None else c.template_id,
        "status": c.status,
        "stats": {
            "totalRecipients": len(recipients),
            "sent": sent_count,
            "opened": open_count,
            "clicked": click_count,
            "openRate": open_rate,
            "clickRate": click_rate,
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
                "totalRecipients": len(recipients),
                "sent": sent,
                "opened": opened,
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
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Campaign).where(Campaign.portal_user_id == portal_user_id, Campaign.is_active == True)
    
    if search:
        stmt = stmt.where(Campaign.name.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(Campaign.status == status)

    stmt = stmt.order_by(Campaign.created_at.desc())

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
    
    lists_data = []
    if c.email_list_ids:
        list_ids = [int(i) for i in c.email_list_ids if str(i).isdigit()]
        if list_ids:
            res_lists = await db.execute(select(EmailList).where(EmailList.id.in_(list_ids)))
            for lst in res_lists.scalars().all():
                lists_data.append({
                    "_id": lst.id,
                    "name": lst.name,
                    "stats": {"activeSubscribers": getattr(lst, "member_count", 0)}
                })
                
    template_data = c.template_id
    if c.template_id and str(c.template_id).isdigit():
        res_tpl = await db.execute(select(Template).where(Template.id == int(c.template_id)))
        tpl = res_tpl.scalar_one_or_none()
        if tpl:
            template_data = {"_id": tpl.id, "name": tpl.name, "category": getattr(tpl, "category", "Mặc định")}

    return {"success": True, "data": _to_response(c, lists_data, template_data)}


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
        sender_name=data.sender.name if data.sender and data.sender.name else "No Name",
        sender_email=data.sender.email if data.sender and data.sender.email else "no-reply@example.com",
        sender=json.dumps(data.sender.dict()) if data.sender else None,
        email_list_ids=[str(i) for i in (data.emailListIds or [])],
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
        c.sender_name = data.sender.name if data.sender.name else "No Name"
        c.sender_email = data.sender.email if data.sender.email else "no-reply@example.com"
    if data.emailListIds is not None:
        c.email_list_ids = [str(i) for i in data.emailListIds]
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
        list_ids = [int(i) for i in c.email_list_ids if str(i).isdigit()]

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


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Tạm dừng campaign."""
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)
    if c.status != "sending":
        raise HTTPException(status_code=422, detail="Chỉ có thể tạm dừng campaign đang gửi")

    c.status = "paused"
    await db.commit()
    return {"success": True}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Tiếp tục campaign đã tạm dừng."""
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)
    if c.status != "paused":
        raise HTTPException(status_code=422, detail="Chỉ có thể tiếp tục campaign đang tạm dừng")

    c.status = "sending"
    await db.commit()
    return {"success": True}


@router.post("/campaigns/{campaign_id}/recalculate-stats")
async def recalculate_stats(
    campaign_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Tính toán lại các chỉ số thống kê của campaign."""
    c = await _get_campaign_or_404(campaign_id, portal_user_id, db)
    
    recipients = []
    if c.recipients:
        try:
            recipients = json.loads(c.recipients)
        except Exception:
            recipients = []

    c.sent_count = len([r for r in recipients if r.get("sentAt")])
    c.open_count = len([r for r in recipients if r.get("opened")])
    
    await db.commit()
    return {"success": True, "data": _to_response(c)}


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
