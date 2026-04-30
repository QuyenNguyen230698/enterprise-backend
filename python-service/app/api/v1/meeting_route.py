import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.zoom_service import create_zoom_meeting, end_zoom_meeting
from app.services.email_service import send_meeting_invite, jinja_env
from app.services.notification_service import create_broadcast_notification
from sqlalchemy import select, and_, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timezone
from app.db.database import get_db
from app.models.meeting_model import Meeting, MeetingInvite, MeetingStatus, InviteStatus
from app.models.user_model import User
from app.models.tenant_model import Tenant
from app.models.room_model import Room
from app.models.area_model import Area
from app.schemas.meeting_schema import (
    MeetingCreate, MeetingUpdate, MeetingResponse,
    MeetingInviteCreate, MeetingInviteResponse, MeetingInviteRespond
)

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────────────

async def _resolve_tenant_id(db: AsyncSession, portal_user_id: str) -> str:
    """
    Returns the tenant_id for a user:
    - If user has a tenant_id that exists in the tenants table → use it (real tenant)
    - Otherwise → return "personal_{portal_user_id}" (isolated personal space)
    """
    user_result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.tenant_id:
        return f"personal_{portal_user_id}"
    return user.tenant_id


async def _check_conflict(db: AsyncSession, room_id: int, date: str, start_time: str, end_time: str, exclude_id: Optional[int] = None):
    """Check for time-slot conflict in the same room on the same date."""
    query = select(Meeting).where(
        and_(
            Meeting.room_id == room_id,
            Meeting.date == date,
            Meeting.status.notin_([MeetingStatus.cancelled]),
            Meeting.start_time < end_time,
            Meeting.end_time > start_time
        )
    )
    if exclude_id:
        query = query.where(Meeting.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None

async def _get_room_area_names(db: AsyncSession, room_id: int) -> tuple[str, str]:
    room_result = await db.execute(select(Room).where(Room.id == room_id))
    room = room_result.scalar_one_or_none()
    if not room:
        return "N/A", "N/A"
    area_result = await db.execute(select(Area).where(Area.id == room.area_id))
    area = area_result.scalar_one_or_none()
    return room.name, (area.name if area else "N/A")


async def _get_tenant_user_ids(db: AsyncSession, tenant_id: str) -> list[str]:
    """Trả về danh sách portal_user_id của tất cả thành viên trong tenant."""
    result = await db.execute(
        select(User.portal_user_id).where(User.tenant_id == tenant_id)
    )
    return [row[0] for row in result.all()]


async def end_zoom_meeting_after(meeting_id: str, delay_seconds: float):
    """Wait until meeting end time then close the Zoom meeting."""
    await asyncio.sleep(delay_seconds)
    await end_zoom_meeting(meeting_id)

# ─── Meeting CRUD ─────────────────────────────────────────────────

@router.get("/", response_model=List[MeetingResponse])
async def list_meetings(
    portal_user_id: str = Query(..., description="portal_user_id của user đang xem lịch"),
    area_id: Optional[int] = Query(None),
    room_id: Optional[int] = Query(None),
    date: Optional[str] = Query(None, description="Filter by date YYYY-MM-DD"),
    status: Optional[str] = Query(None),
    organizer_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    List meetings filtered by tenant_id resolved from portal_user_id.
    - User có tenant thực → thấy lịch họp của cả tenant
    - User chưa có tenant thực → thấy lịch họp personal của riêng mình
    """
    tenant_id = await _resolve_tenant_id(db, portal_user_id)

    query = select(Meeting).options(selectinload(Meeting.invites)).where(
        Meeting.tenant_id == tenant_id
    )
    if area_id:
        query = query.where(Meeting.area_id == area_id)
    if room_id:
        query = query.where(Meeting.room_id == room_id)
    if date:
        query = query.where(Meeting.date == date)
    if status:
        query = query.where(Meeting.status == status)
    if organizer_id:
        query = query.where(Meeting.organizer_id == organizer_id)
    result = await db.execute(query.order_by(Meeting.date, Meeting.start_time))
    return result.scalars().all()


@router.post("/", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(payload: MeetingCreate, bg_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Create a new meeting.
    Checks for room time-slot conflicts before saving.
    """
    conflict = await _check_conflict(
        db, payload.room_id, payload.date, payload.start_time, payload.end_time
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Room is already booked for this time slot.")

    # Resolve tenant_id từ organizer — không để frontend tự set
    tenant_id = await _resolve_tenant_id(db, payload.organizer_id)
    meeting = Meeting(**payload.model_dump(), tenant_id=tenant_id)
    
    # Zoom Integration
    try:
        # Convert local time (UTC+7 for Vietnam) to UTC for Zoom API
        local_tz_offset = timedelta(hours=7)
        start_dt_local = datetime.strptime(f"{payload.date}T{payload.start_time}:00", "%Y-%m-%dT%H:%M:%S")
        start_dt_utc = start_dt_local - local_tz_offset
        zoom_start = start_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        zoom_start = f"{payload.date}T{payload.start_time}:00Z"

    zoom_data = await create_zoom_meeting(payload.title, zoom_start, 60)
    join_url_clean = zoom_data.get("join_url", "")
    if "?pwd=" in join_url_clean:
        join_url_clean = join_url_clean.split("?pwd=")[0]
    
    meeting.zoom_join_url = join_url_clean
    meeting.zoom_password = zoom_data.get("password")
    meeting.zoom_meeting_id = str(zoom_data.get("meeting_id")) if zoom_data.get("meeting_id") else None

    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)

    # Lookup Organizer Email
    organizer_result = await db.execute(select(User).where(User.portal_user_id == payload.organizer_id))
    organizer_user = organizer_result.scalar_one_or_none()
    organizer_email = organizer_user.email if organizer_user else f"{payload.organizer_id}@portal.com"

    # Lookup Attendee Emails
    attendees_result = await db.execute(select(User).where(User.portal_user_id.in_(payload.attendee_ids)))
    attendee_users = attendees_result.scalars().all()
    attendee_email_map = {user.portal_user_id: user.email for user in attendee_users}

    # Auto-create organizer invite
    organizer_invite = MeetingInvite(
        meeting_id=meeting.id,
        email=organizer_email,
        role="organizer",
        status="pending",
        token=str(uuid.uuid4())
    )
    db.add(organizer_invite)

    # Auto-create attendee invites
    for attendee_id in payload.attendee_ids:
        attendee_email = attendee_email_map.get(attendee_id, f"{attendee_id}@portal.com")
        attendee_invite = MeetingInvite(
            meeting_id=meeting.id,
            email=attendee_email,
            role="attendee",
            status="pending",
            token=str(uuid.uuid4())
        )
        db.add(attendee_invite)

    # Auto-create CC invites
    if payload.cc_emails:
        cc_list = [email.strip() for email in payload.cc_emails.split(",") if email.strip()]
        for cc_email in cc_list:
            cc_invite = MeetingInvite(
                meeting_id=meeting.id,
                email=cc_email,
                role="cc",
                status="pending",
                token=str(uuid.uuid4())
            )
            db.add(cc_invite)

    await db.commit()
    await db.refresh(meeting)

    # Build meeting_details for notifications
    _room_name, _area_name = await _get_room_area_names(db, meeting.room_id)
    meeting_details = {
        "topic": meeting.title,
        "date": meeting.date,
        "start_time": meeting.start_time,
        "end_time": meeting.end_time,
        "organizer_id": meeting.organizer_id,
        "notes": meeting.notes,
        "join_url": meeting.zoom_join_url,
        "password": meeting.zoom_password,
        "meeting_id": meeting.zoom_meeting_id,
        "room_id": meeting.room_id,
        "room_name": _room_name,
        "area_name": _area_name,
    }
    # Email invite được gửi hoàn toàn qua Redis worker (status=pending → worker poll → internal/send-invite)
    # Không gửi trực tiếp ở đây để tránh duplicate với worker

    # Thông báo cho toàn bộ thành viên trong tenant
    tenant_user_ids = await _get_tenant_user_ids(db, meeting.tenant_id)
    if tenant_user_ids:
        organizer_name = organizer_user.full_name or organizer_user.name or organizer_user.email if organizer_user else meeting.organizer_id
        organizer_email_display = organizer_user.email if organizer_user else ""
        await create_broadcast_notification(
            db=db,
            tenant_id=meeting.tenant_id,
            user_ids=tenant_user_ids,
            title="Lịch họp mới được tạo",
            message=f"{organizer_name} ({organizer_email_display}) đã tạo lịch họp \"{meeting.title}\" vào {meeting.date} lúc {meeting.start_time}–{meeting.end_time}.",
            type="info",
            link=f"/bookings",
        )

    # Schedule auto-end zoom meeting khi hết giờ (không gửi email cancellation)
    if meeting.zoom_meeting_id:
        try:
            local_tz_offset = timedelta(hours=7)
            end_dt_local = datetime.strptime(f"{payload.date}T{payload.end_time}:00", "%Y-%m-%dT%H:%M:%S")
            end_dt_utc = end_dt_local - local_tz_offset
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            delay = (end_dt_utc - now_utc).total_seconds()

            if delay > 0:
                asyncio.create_task(end_zoom_meeting_after(meeting.zoom_meeting_id, delay))
        except Exception:
            pass

    return meeting


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(meeting_id: int, db: AsyncSession = Depends(get_db)):
    """Get a meeting by ID (includes invite list)."""
    result = await db.execute(select(Meeting).options(selectinload(Meeting.invites)).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


@router.put("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(meeting_id: int, payload: MeetingUpdate, db: AsyncSession = Depends(get_db)):
    """
    Update meeting details.
    Re-checks conflict if room or time is changed.
    """
    result = await db.execute(select(Meeting).options(selectinload(Meeting.invites)).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    update_data = payload.model_dump(exclude_unset=True)

    # If time or room changes, check conflict
    new_room = update_data.get("room_id", meeting.room_id)
    new_date = update_data.get("date", meeting.date)
    new_start = update_data.get("start_time", meeting.start_time)
    new_end = update_data.get("end_time", meeting.end_time)

    if any(k in update_data for k in ("room_id", "date", "start_time", "end_time")):
        conflict = await _check_conflict(db, new_room, new_date, new_start, new_end, exclude_id=meeting_id)
        if conflict:
            raise HTTPException(status_code=409, detail="Updated time slot conflicts with an existing meeting.")

    for key, value in update_data.items():
        setattr(meeting, key, value)

    await db.commit()
    await db.refresh(meeting)

    # Thông báo cập nhật lịch họp cho toàn tenant
    tenant_user_ids = await _get_tenant_user_ids(db, meeting.tenant_id)
    if tenant_user_ids:
        organizer_result = await db.execute(select(User).where(User.portal_user_id == meeting.organizer_id))
        organizer_user = organizer_result.scalar_one_or_none()
        organizer_name = organizer_user.full_name or organizer_user.name or organizer_user.email if organizer_user else meeting.organizer_id
        organizer_email_display = organizer_user.email if organizer_user else ""
        await create_broadcast_notification(
            db=db,
            tenant_id=meeting.tenant_id,
            user_ids=tenant_user_ids,
            title="Lịch họp đã được cập nhật",
            message=f"{organizer_name} ({organizer_email_display}) đã cập nhật lịch họp \"{meeting.title}\" vào {meeting.date} lúc {meeting.start_time}–{meeting.end_time}.",
            type="warning",
            link=f"/bookings",
        )

    return meeting


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: int, db: AsyncSession = Depends(get_db)):
    """Delete (hard delete) a meeting and all associated invites."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    # Lấy thông tin trước khi xóa để dùng trong notification
    tenant_user_ids = await _get_tenant_user_ids(db, meeting.tenant_id)
    organizer_result = await db.execute(select(User).where(User.portal_user_id == meeting.organizer_id))
    organizer_user = organizer_result.scalar_one_or_none()
    organizer_name = organizer_user.full_name or organizer_user.name or organizer_user.email if organizer_user else meeting.organizer_id
    organizer_email_display = organizer_user.email if organizer_user else ""
    snapshot = {
        "tenant_id": meeting.tenant_id,
        "title": meeting.title,
        "date": meeting.date,
        "start_time": meeting.start_time,
        "end_time": meeting.end_time,
    }

    await db.delete(meeting)
    await db.commit()

    if tenant_user_ids:
        await create_broadcast_notification(
            db=db,
            tenant_id=snapshot["tenant_id"],
            user_ids=tenant_user_ids,
            title="Lịch họp đã bị xóa",
            message=f"{organizer_name} ({organizer_email_display}) đã xóa lịch họp \"{snapshot['title']}\" vào {snapshot['date']} lúc {snapshot['start_time']}–{snapshot['end_time']}.",
            type="error",
            link="/bookings",
        )


@router.patch("/{meeting_id}/cancel", response_model=MeetingResponse)
async def cancel_meeting(meeting_id: int, db: AsyncSession = Depends(get_db)):
    """Soft cancel a meeting (sets status to cancelled)."""
    result = await db.execute(select(Meeting).options(selectinload(Meeting.invites)).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    meeting.status = MeetingStatus.cancelled
    await db.commit()
    await db.refresh(meeting)

    # Thông báo hủy lịch họp cho toàn tenant
    tenant_user_ids = await _get_tenant_user_ids(db, meeting.tenant_id)
    if tenant_user_ids:
        organizer_result = await db.execute(select(User).where(User.portal_user_id == meeting.organizer_id))
        organizer_user = organizer_result.scalar_one_or_none()
        organizer_name = organizer_user.full_name or organizer_user.name or organizer_user.email if organizer_user else meeting.organizer_id
        organizer_email_display = organizer_user.email if organizer_user else ""
        await create_broadcast_notification(
            db=db,
            tenant_id=meeting.tenant_id,
            user_ids=tenant_user_ids,
            title="Lịch họp đã bị hủy",
            message=f"{organizer_name} ({organizer_email_display}) đã hủy lịch họp \"{meeting.title}\" vào {meeting.date} lúc {meeting.start_time}–{meeting.end_time}.",
            type="error",
            link="/bookings",
        )

    return meeting


# ─── Meeting Invites ──────────────────────────────────────────────

@router.get("/{meeting_id}/invites", response_model=List[MeetingInviteResponse])
async def list_invites(meeting_id: int, db: AsyncSession = Depends(get_db)):
    """List all invites for a meeting."""
    result = await db.execute(select(MeetingInvite).where(MeetingInvite.meeting_id == meeting_id))
    return result.scalars().all()


@router.post("/{meeting_id}/invites", response_model=MeetingInviteResponse, status_code=status.HTTP_201_CREATED)
async def add_invite(meeting_id: int, payload: MeetingInviteCreate, db: AsyncSession = Depends(get_db)):
    """Add an attendee or CC to an existing meeting."""
    # Ensure meeting exists
    meeting_result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    if not meeting_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Meeting not found.")

    invite = MeetingInvite(
        meeting_id=meeting_id,
        token=str(uuid.uuid4()),
        **payload.model_dump()
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@router.put("/invites/{invite_id}/respond", response_model=MeetingInviteResponse)
async def respond_to_invite(invite_id: int, payload: MeetingInviteRespond, db: AsyncSession = Depends(get_db)):
    """
    Accept or decline an invite via token.
    Used for frontend/API integration.
    """
    result = await db.execute(
        select(MeetingInvite).where(
            and_(MeetingInvite.id == invite_id, MeetingInvite.token == payload.token)
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or invalid token.")
    invite.status = payload.action
    invite.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(invite)
    return invite

@router.post("/internal/send-invite/{invite_id}", status_code=status.HTTP_200_OK)
async def internal_send_invite(invite_id: int, db: AsyncSession = Depends(get_db)):
    """
    Internal API called by the worker to trigger email sending for a specific invite.
    Uses an atomic UPDATE … WHERE status NOT IN ('sent','processing') to claim the invite,
    preventing duplicate sends when two worker retries race concurrently.
    """
    from sqlalchemy import text

    # Atomic claim:
    # - Skip if already 'sent' (done)
    # - Skip if 'processing' and updated_at within last 5 minutes (genuinely in-flight)
    # - Claim anything else: pending, enqueued, failed, or processing stuck > 5 min
    claim = await db.execute(
        text(
            "UPDATE meeting_invites SET status = 'processing', updated_at = now() "
            "WHERE id = :id "
            "  AND status != 'sent' "
            "  AND NOT (status = 'processing' AND updated_at > now() - interval '5 minutes') "
            "RETURNING id"
        ),
        {"id": invite_id},
    )
    await db.commit()
    claimed = claim.fetchone() is not None

    if not claimed:
        result = await db.execute(select(MeetingInvite).where(MeetingInvite.id == invite_id))
        invite = result.scalar_one_or_none()
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")
        return {"message": f"Already sent or in-progress for {invite.email}", "idempotent": True}

    result = await db.execute(
        select(MeetingInvite).options(selectinload(MeetingInvite.meeting)).where(MeetingInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    meeting = invite.meeting
    _room_name, _area_name = await _get_room_area_names(db, meeting.room_id)
    meeting_details = {
        "topic": meeting.title,
        "date": meeting.date,
        "start_time": meeting.start_time,
        "end_time": meeting.end_time,
        "organizer_id": meeting.organizer_id,
        "notes": meeting.notes,
        "join_url": meeting.zoom_join_url,
        "password": meeting.zoom_password,
        "meeting_id": meeting.zoom_meeting_id,
        "room_id": meeting.room_id,
        "room_name": _room_name,
        "area_name": _area_name,
    }

    # Run synchronously so exceptions surface in logs and HTTP status reflects result
    await send_meeting_invite(
        to_email=invite.email,
        cc_emails="",
        meeting_details=meeting_details,
        invite_id=invite.id,
        token=invite.token,
    )

    return {"message": f"Invite email triggered for {invite.email}"}

from fastapi.responses import HTMLResponse

@router.get("/invites/{invite_id}/respond", response_class=HTMLResponse)
async def respond_to_invite_get(invite_id: int, token: str, action: str, db: AsyncSession = Depends(get_db)):
    """
    Accept or decline an invite via GET request (from email link).
    """
    if action not in ["accepted", "declined"]:
        return HTMLResponse("<h1>Invalid action. Must be 'accepted' or 'declined'.</h1>", status_code=400)

    result = await db.execute(
        select(MeetingInvite).where(
            and_(MeetingInvite.id == invite_id, MeetingInvite.token == token)
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        return HTMLResponse("<h1>Invite not found or invalid token.</h1>", status_code=404)

    invite.status = action
    invite.responded_at = datetime.now(timezone.utc)
    await db.commit()

    # Load meeting + room + area info for the response page
    meeting_result = await db.execute(select(Meeting).where(Meeting.id == invite.meeting_id))
    meeting = meeting_result.scalar_one_or_none()

    room_name, area_name = ("N/A", "N/A")
    if meeting:
        room_name, area_name = await _get_room_area_names(db, meeting.room_id)

    ctx = {
        "topic": meeting.title if meeting else "N/A",
        "date": meeting.date if meeting else "N/A",
        "start_time": meeting.start_time if meeting else "N/A",
        "end_time": meeting.end_time if meeting else "N/A",
        "room": f"{room_name} ({area_name})",
    }

    template_name = "invite_accepted.html" if action == "accepted" else "invite_declined.html"
    html = jinja_env.get_template(template_name).render(**ctx)
    return HTMLResponse(html)
