import os
import logging
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import aiosmtplib
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings

logger = logging.getLogger(__name__)

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# Setup Jinja2 environment loading from app/templates
template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
jinja_env = Environment(loader=FileSystemLoader(template_dir))

async def send_meeting_invite(
    to_email: str,
    cc_emails: str,
    meeting_details: dict,
    invite_id: Optional[int] = None,
    token: Optional[str] = None,
):
    """
    Sends an HTML meeting invite email.
    When invite_id is provided, opens its own DB session to write 'sent' or 'failed'
    so this function is safe to run as a background task (request session is already closed).
    """
    from app.models.meeting_model import InviteStatus

    print(f"[EMAIL] send_meeting_invite called: to={to_email} invite_id={invite_id}", flush=True)

    if not EMAIL_USER or not EMAIL_PASS:
        print(f"[EMAIL] credentials missing, marking failed invite_id={invite_id}", flush=True)
        if invite_id:
            await _set_invite_status(invite_id, InviteStatus.failed)
        return

    try:
        meeting_details["to_email"] = to_email
        meeting_details["invite_id"] = invite_id
        meeting_details["token"] = token
        meeting_details["backend_url"] = settings.BACKEND_URL

        template = jinja_env.get_template("meeting_invite.html")
        html_content = template.render(**meeting_details)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MeetingRoom] {meeting_details.get('topic')}"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        if cc_emails:
            msg["Cc"] = cc_emails

        msg.attach(MIMEText(html_content, "html"))

        if meeting_details.get("date") and meeting_details.get("start_time") and meeting_details.get("end_time"):
            start_str = f"{meeting_details['date'].replace('-', '')}T{meeting_details['start_time'].replace(':', '')}00Z"
            end_str = f"{meeting_details['date'].replace('-', '')}T{meeting_details['end_time'].replace(':', '')}00Z"

            ics_content = (
                "BEGIN:VCALENDAR\r\n"
                "VERSION:2.0\r\n"
                "PRODID:-//Enterprise Meeting System//EN\r\n"
                "BEGIN:VEVENT\r\n"
                f"SUMMARY:{meeting_details.get('topic')}\r\n"
                f"DTSTART:{start_str}\r\n"
                f"DTEND:{end_str}\r\n"
                f"DESCRIPTION:Join Zoom Meeting: {meeting_details.get('join_url')} Passcode: {meeting_details.get('password')}\r\n"
                "STATUS:CONFIRMED\r\n"
                "SEQUENCE:0\r\n"
                "BEGIN:VALARM\r\n"
                "TRIGGER:-PT15M\r\n"
                "DESCRIPTION:Reminder\r\n"
                "ACTION:DISPLAY\r\n"
                "END:VALARM\r\n"
                "END:VEVENT\r\n"
                "END:VCALENDAR\r\n"
            )
            part = MIMEApplication(ics_content.encode("utf-8"), Name="invite.ics")
            part['Content-Disposition'] = 'attachment; filename="invite.ics"'
            msg.attach(part)

        logger.info(f"Sending meeting invite to {to_email} (invite_id={invite_id})")
        await aiosmtplib.send(
            msg,
            hostname=EMAIL_HOST,
            port=EMAIL_PORT,
            username=EMAIL_USER,
            password=EMAIL_PASS,
            start_tls=True,
        )
        logger.info(f"Email sent successfully to {to_email} (invite_id={invite_id})")

        if invite_id:
            await _set_invite_status(invite_id, InviteStatus.sent)

    except Exception as e:
        print(f"[EMAIL] ERROR sending to {to_email} invite_id={invite_id}: {e}", flush=True)
        logger.error(f"Error sending email to {to_email} (invite_id={invite_id}): {e}")
        if invite_id:
            await _set_invite_status(invite_id, InviteStatus.failed)


async def _set_invite_status(invite_id: int, status) -> None:
    """Opens a fresh DB session — safe to call from background tasks."""
    from app.models.meeting_model import MeetingInvite
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MeetingInvite).where(MeetingInvite.id == invite_id))
        invite = result.scalar_one_or_none()
        if invite:
            invite.status = status
            await db.commit()

async def send_meeting_cancellation(to_email: str, cc_emails: str, meeting_details: dict):
    """
    Sends an HTML meeting cancellation email.
    """
    if not EMAIL_USER or not EMAIL_PASS:
        logger.warning("Email credentials missing. Skipped sending email.")
        return

    try:
        meeting_details["to_email"] = to_email
        template = jinja_env.get_template("meeting_cancelled.html")
        html_content = template.render(**meeting_details)
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MeetingRoom] {meeting_details.get('topic')}"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        if cc_emails:
            msg["Cc"] = cc_emails

        msg.attach(MIMEText(html_content, "html"))

        logger.info(f"Sending meeting cancellation to {to_email}")
        await aiosmtplib.send(
            msg,
            hostname=EMAIL_HOST,
            port=EMAIL_PORT,
            username=EMAIL_USER,
            password=EMAIL_PASS,
            start_tls=True,
        )
        logger.info("Cancellation email sent successfully!")

    except Exception as e:
        logger.error(f"Error sending cancellation email: {e}")


async def send_offboarding_confirmation(to_email: str, process_data: dict):
    """
    Gửi email xác nhận nghỉ việc cho nhân viên sau khi GM phê duyệt (step 5 authorize).
    process_data chứa: employee_name, application_ref, resignation_date,
                       last_working_day, department, job_title, payment_date
    """
    if not EMAIL_USER or not EMAIL_PASS:
        logger.warning("[OFFBOARDING EMAIL] credentials missing, skipped.")
        return

    try:
        template = jinja_env.get_template("offboarding_confirmation.html")
        html_content = template.render(**process_data)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[HRM System] Xác nhận đơn thôi việc — {process_data.get('application_ref', '')}"
        msg["From"] = f"Enterprise Meeting HR <hr@emtools.site>"
        msg["To"] = to_email

        msg.attach(MIMEText(html_content, "html"))

        logger.info(f"[OFFBOARDING EMAIL] Sending confirmation to {to_email}")
        await aiosmtplib.send(
            msg,
            hostname=EMAIL_HOST,
            port=EMAIL_PORT,
            username=EMAIL_USER,
            password=EMAIL_PASS,
            start_tls=True,
        )
        logger.info(f"[OFFBOARDING EMAIL] Sent successfully to {to_email}")

    except Exception as e:
        logger.error(f"[OFFBOARDING EMAIL] Error sending to {to_email}: {e}")
