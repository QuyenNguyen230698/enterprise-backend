"""
Recruitment email sender — gửi reply hàng loạt cho ứng viên.

Tái dụng aiosmtplib giống email_service.py nhưng dùng EmailConfig
được resolve từ DB (per-user, encrypted) thay vì env vars cứng.
"""
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)


def _resolve_smtp(cfg) -> dict:
    """Return smtp kwargs dict from an EmailConfig ORM row."""
    if cfg.provider == "gmail":
        return {
            "hostname": "smtp.gmail.com",
            "port": 587,
            "username": cfg.gmail_address,
            "password": decrypt(cfg.gmail_app_password_enc) if cfg.gmail_app_password_enc else "",
            "start_tls": True,
        }
    return {
        "hostname": cfg.smtp_host or "smtp.gmail.com",
        "port": cfg.smtp_port or 587,
        "username": cfg.smtp_username,
        "password": decrypt(cfg.smtp_password_enc) if cfg.smtp_password_enc else "",
        "start_tls": not cfg.smtp_secure,
        "use_tls": bool(cfg.smtp_secure),
    }


def _build_quoted_html(
    original_body_html: str,
    original_body_text: str,
    original_from: str,
    original_from_email: str,
    original_subject: str,
    original_received_at: str,
    mode: str = "reply",
) -> str:
    """
    Tạo phần trích dẫn email gốc theo chuẩn Gmail (reply hoặc forward).
    Trả về chuỗi HTML để ghép sau body chính.
    """
    body_content = original_body_html
    if not body_content and original_body_text:
        body_content = f"<pre style='font-family:inherit;white-space:pre-wrap'>{original_body_text}</pre>"

    if not body_content:
        return ""

    from_display = f"{original_from} &lt;{original_from_email}&gt;" if original_from and original_from != original_from_email else original_from_email

    if mode == "forward":
        header = (
            "<div style='border-top:1px solid #e0e0e0;margin-top:16px;padding-top:8px'>"
            "<p style='color:#666;font-size:13px;margin:0 0 8px'>"
            "<strong>---------- Forwarded message ---------</strong><br>"
            f"<strong>From:</strong> {from_display}<br>"
            f"<strong>Subject:</strong> {original_subject}<br>"
            f"<strong>Date:</strong> {original_received_at}"
            "</p>"
            "</div>"
        )
    else:
        header = (
            f"<div style='margin-top:16px;color:#666;font-size:13px'>"
            f"On {original_received_at}, {from_display} wrote:"
            "</div>"
        )

    quote_block = (
        "<blockquote style='"
        "margin:0 0 0 8px;"
        "padding-left:12px;"
        "border-left:3px solid #ccc;"
        "color:#555;"
        "font-size:13px;"
        "'>"
        f"{body_content}"
        "</blockquote>"
    )

    return header + quote_block


async def send_reply(
    cfg,
    from_name: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    reply_to_message_id: Optional[str] = None,
    reply_mode: str = "reply",
    original_body_html: str = "",
    original_body_text: str = "",
    original_from: str = "",
    original_from_email: str = "",
    original_subject: str = "",
    original_received_at: str = "",
) -> None:
    """
    Gửi 1 email reply/forward cho ứng viên.

    Nếu reply_mode là "reply" hoặc "forward", nội dung gốc sẽ được
    tự động trích dẫn và ghép vào cuối body_html.

    Raises exception nếu thất bại — caller quyết định ghi log / update status.
    """
    sender_email = cfg.gmail_address if cfg.provider == "gmail" else cfg.smtp_username
    sender_display = from_name or cfg.sender_name or sender_email

    # Ghép quote nội dung gốc nếu là reply hoặc forward
    final_body = body_html
    if reply_mode in ("reply", "forward") and (original_body_html or original_body_text):
        quote = _build_quoted_html(
            original_body_html=original_body_html,
            original_body_text=original_body_text,
            original_from=original_from,
            original_from_email=original_from_email,
            original_subject=original_subject,
            original_received_at=original_received_at,
            mode=reply_mode,
        )
        final_body = body_html + quote

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_display} <{sender_email}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    # Headers chuẩn RFC để Gmail/Outlook nhận ra là reply trong cùng thread
    if reply_to_message_id and reply_mode in ("reply", "forward"):
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

    msg.attach(MIMEText(final_body, "html"))

    smtp_kwargs = _resolve_smtp(cfg)
    await aiosmtplib.send(msg, **smtp_kwargs)


async def send_bulk_replies(
    cfg,
    recipients: list[dict],
    subject: str,
    body_html: str,
    from_name: str,
    on_result=None,
    reply_mode: str = "reply",
    forward_to: Optional[str] = None,
) -> dict:
    """
    Gửi tuần tự đến từng địa chỉ trong recipients.

    recipients mỗi item: {
        to_email, to_name, candidate_email_id, message_id,
        original_subject, original_from, original_from_email,
        original_received_at, original_body_html, original_body_text
    }

    reply_mode: "reply" | "forward" | "new"
      - "reply"   → gửi lại cho người gửi gốc, ghép quote bên dưới
      - "forward" → gửi đến forward_to, ghép nội dung gốc theo chuẩn Fwd
      - "new"     → gửi email mới, không quote

    on_result: async callback(candidate_email_id, status, error)
    """
    sent = 0
    failed = 0

    for r in recipients:
        original_to = r.get("to_email", "")
        to_name = r.get("to_name", "")
        cid = r.get("candidate_email_id")
        msg_id = r.get("message_id")

        # Với forward: gửi đến forward_to thay vì người gửi gốc
        actual_to_email = forward_to if reply_mode == "forward" and forward_to else original_to
        actual_to_name = "" if reply_mode == "forward" and forward_to else to_name

        if not actual_to_email:
            failed += 1
            if on_result:
                await on_result(cid, "failed", "Thiếu địa chỉ email")
            continue

        try:
            await send_reply(
                cfg=cfg,
                from_name=from_name,
                to_email=actual_to_email,
                to_name=actual_to_name,
                subject=subject,
                body_html=body_html,
                reply_to_message_id=msg_id if reply_mode in ("reply", "forward") else None,
                reply_mode=reply_mode,
                original_body_html=r.get("original_body_html", ""),
                original_body_text=r.get("original_body_text", ""),
                original_from=r.get("original_from", ""),
                original_from_email=r.get("original_from_email", ""),
                original_subject=r.get("original_subject", ""),
                original_received_at=r.get("original_received_at", ""),
            )
            sent += 1
            logger.info(f"[RECRUITMENT] {reply_mode.capitalize()} sent → {actual_to_email}")
            if on_result:
                await on_result(cid, "sent", None)
        except Exception as exc:
            failed += 1
            logger.error(f"[RECRUITMENT] {reply_mode.capitalize()} failed → {actual_to_email}: {exc}")
            if on_result:
                await on_result(cid, "failed", str(exc))

    return {"sent": sent, "failed": failed, "total": len(recipients)}
