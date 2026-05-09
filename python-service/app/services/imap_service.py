"""
IMAP pull service — fetches unread candidate emails from an inbox.

Supports Gmail (IMAP with App Password) and generic SMTP/IMAP providers.
Uses aioimaplib for async operation.
"""
import asyncio
import email
import json
import logging
import quopri
import re
from datetime import datetime, timezone
from email.header import decode_header
from typing import Optional

import aioimaplib

logger = logging.getLogger(__name__)

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


def _decode_header_value(raw: str) -> str:
    """Decode RFC 2047-encoded email header to plain string."""
    parts = decode_header(raw or "")
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _extract_address(header_val: str) -> tuple[str, str]:
    """Return (name, email) from a From header like 'John Doe <john@example.com>'."""
    header_val = header_val or ""
    match = re.match(r"^(.*?)\s*<([^>]+)>$", header_val.strip())
    if match:
        name = _decode_header_value(match.group(1)).strip().strip('"')
        addr = match.group(2).strip()
        return name, addr
    return "", header_val.strip()


def _get_attachments(msg: email.message.Message) -> list[dict]:
    """Extract attachment metadata (with part index) from a multipart message."""
    attachments = []
    if not msg.is_multipart():
        return attachments
    index = 0
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        if "attachment" not in cd and "inline" not in cd:
            continue
        filename_raw = part.get_filename()
        if not filename_raw:
            continue
        filename = _decode_header_value(filename_raw)
        mime_type = part.get_content_type() or "application/octet-stream"
        payload = part.get_payload(decode=True)
        size = len(payload) if payload else 0
        attachments.append({
            "filename": filename,
            "mimeType": mime_type,
            "size": size,
            "attachmentIndex": index,
        })
        index += 1
    return attachments


async def fetch_attachment_imap(
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    message_id: str,
    attachment_index: int,
    folder: str = "INBOX",
) -> Optional[tuple]:
    """
    Fetch raw bytes of one attachment from IMAP by Message-ID and attachment index.
    Returns (data, filename, mime_type) or None if not found.
    """
    client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    await asyncio.wait_for(client.wait_hello_from_server(), timeout=30)
    login_resp = await asyncio.wait_for(client.login(username, password), timeout=15)
    if login_resp.result != "OK":
        raise RuntimeError(f"IMAP login failed: {login_resp.lines}")

    await asyncio.wait_for(client.select(folder), timeout=10)

    # Search by Message-ID header
    safe_id = message_id.replace('"', '')
    search_resp = await asyncio.wait_for(
        client.search("HEADER", "Message-ID", safe_id),
        timeout=15,
    )
    uids = _parse_uids(search_resp) if search_resp.result == "OK" else []

    if not uids:
        await client.logout()
        return None

    fetch_resp = await asyncio.wait_for(client.fetch(uids[-1], "(RFC822)"), timeout=30)
    if fetch_resp.result != "OK":
        await client.logout()
        return None

    raw_email = None
    for item in fetch_resp.lines:
        if isinstance(item, (bytes, bytearray)) and len(item) > 200:
            raw_email = item
            break

    await client.logout()
    if not raw_email:
        return None

    msg = email.message_from_bytes(raw_email)
    idx = 0
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        if "attachment" not in cd and "inline" not in cd:
            continue
        if not part.get_filename():
            continue
        if idx == attachment_index:
            data = part.get_payload(decode=True) or b""
            filename = _decode_header_value(part.get_filename())
            mime_type = part.get_content_type() or "application/octet-stream"
            return data, filename, mime_type
        idx += 1

    return None


def _get_body(msg: email.message.Message) -> tuple[str, str]:
    """Extract (text/plain, text/html) from a (possibly multipart) message."""
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not body_text:
                body_text = decoded
            elif ct == "text/html" and not body_html:
                body_html = decoded
    else:
        ct = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/html":
                body_html = decoded
            else:
                body_text = decoded
    return body_text, body_html


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_uids(search_resp) -> list[str]:
    """Trích uid list từ IMAP search response."""
    if not search_resp.lines:
        return []
    uid_line = search_resp.lines[0]
    if isinstance(uid_line, bytes):
        uid_line = uid_line.decode()
    return uid_line.strip().split()


async def pull_emails_imap(
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    folder: str = "INBOX",
    max_fetch: int = 50,
) -> list[dict]:
    """
    Kết nối IMAP và kéo tối đa max_fetch email gần nhất.

    Gmail: dùng X-GM-RAW "category:primary" để chỉ lấy tab Primary.
           search() nhận variadic args — truyền từng token riêng.
           Lấy ALL (cả đã đọc) vì dedup theo message_id đã có ở tầng DB.
    IMAP khác: lấy UNSEEN.
    """
    client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    await asyncio.wait_for(client.wait_hello_from_server(), timeout=30)

    login_resp = await asyncio.wait_for(client.login(username, password), timeout=15)
    if login_resp.result != "OK":
        raise RuntimeError(f"IMAP login failed: {login_resp.lines}")

    await asyncio.wait_for(client.select(folder), timeout=10)

    is_gmail = imap_host == GMAIL_IMAP_HOST
    uids = []

    # Map folder value từ frontend sang Gmail X-GM-RAW category
    GMAIL_CATEGORY_MAP = {
        "INBOX":            "category:primary",
        "INBOX_PROMOTIONS": "category:promotions",
        "INBOX_SOCIAL":     "category:social",
        "INBOX_UPDATES":    "category:updates",
        "INBOX_ALL":        None,   # None = lấy toàn bộ INBOX, không filter category
    }

    if is_gmail and folder in GMAIL_CATEGORY_MAP:
        category = GMAIL_CATEGORY_MAP[folder]
        if category:
            # Dùng X-GM-RAW để filter đúng tab Gmail
            try:
                search_resp = await asyncio.wait_for(
                    client.search("X-GM-RAW", f'"{category}"'),
                    timeout=30,
                )
                if search_resp.result == "OK":
                    uids = _parse_uids(search_resp)
                    logger.info(f"[IMAP] Gmail {folder} X-GM-RAW: {len(uids)} emails found")
                else:
                    logger.warning(f"[IMAP] X-GM-RAW not OK for {folder}, fallback to ALL")
            except Exception as exc:
                logger.warning(f"[IMAP] X-GM-RAW failed ({exc}), fallback to ALL")

        if not uids:
            # INBOX_ALL hoặc fallback: lấy toàn bộ — dedup bằng message_id trong DB
            search_resp = await asyncio.wait_for(client.search("ALL"), timeout=30)
            if search_resp.result == "OK":
                uids = _parse_uids(search_resp)
    else:
        # IMAP thường hoặc folder tùy chỉnh: lấy UNSEEN
        search_resp = await asyncio.wait_for(client.search("UNSEEN"), timeout=30)
        if search_resp.result == "OK":
            uids = _parse_uids(search_resp)

    uids = uids[-max_fetch:]  # lấy N email gần nhất

    parsed = []
    for uid in uids:
        try:
            fetch_resp = await asyncio.wait_for(client.fetch(uid, "(RFC822)"), timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"[IMAP] Timeout fetching uid {uid}, skipping")
            continue
        if fetch_resp.result != "OK":
            continue

        raw_email = None
        for item in fetch_resp.lines:
            if isinstance(item, (bytes, bytearray)) and len(item) > 200:
                raw_email = item
                break

        if not raw_email:
            continue

        msg = email.message_from_bytes(raw_email)

        message_id = msg.get("Message-ID", "").strip()
        from_raw = _decode_header_value(msg.get("From", ""))
        from_name, from_email = _extract_address(from_raw)
        subject = _decode_header_value(msg.get("Subject", ""))
        date_str = msg.get("Date")
        received_at = _parse_date(date_str)
        thread_id = msg.get("Thread-Index") or msg.get("References", "").split()[-1] if msg.get("References") else message_id

        body_text, body_html = _get_body(msg)
        attachments = _get_attachments(msg)

        parsed.append({
            "message_id": message_id or None,
            "from_email": from_email,
            "from_name": from_name,
            "subject": subject,
            "body_text": body_text[:20000],
            "body_html": body_html[:50000],
            "received_at": received_at,
            "thread_id": thread_id or None,
            "attachments": json.dumps(attachments, ensure_ascii=False),
            "_imap_uid": uid,
        })

    await client.logout()
    return parsed


async def delete_email_imap(
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    message_id: str,
    folder: str = "INBOX",
) -> bool:
    """
    Tìm email theo Message-ID trong folder và xóa (move to Trash trên Gmail, delete trên IMAP thường).
    Trả về True nếu xóa thành công, False nếu không tìm thấy.
    """
    client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    try:
        await asyncio.wait_for(client.wait_hello_from_server(), timeout=20)
        login_resp = await asyncio.wait_for(client.login(username, password), timeout=15)
        if login_resp.result != "OK":
            raise RuntimeError(f"IMAP login failed")

        await asyncio.wait_for(client.select(folder), timeout=10)

        # Search by Message-ID header
        search_resp = await asyncio.wait_for(
            client.search(f'HEADER Message-ID "{message_id}"'), timeout=15
        )
        if search_resp.result != "OK":
            await client.logout()
            return False

        uid_line = search_resp.lines[0]
        if isinstance(uid_line, bytes):
            uid_line = uid_line.decode()
        uids = uid_line.strip().split()
        if not uids:
            await client.logout()
            return False

        is_gmail = "gmail" in imap_host.lower()
        for uid in uids:
            if is_gmail:
                # Gmail: move to [Gmail]/Trash
                await asyncio.wait_for(
                    client.copy(uid, "[Gmail]/Trash"), timeout=10
                )
            # Mark as deleted
            await asyncio.wait_for(
                client.store(uid, "+FLAGS", "\\Deleted"), timeout=10
            )

        await asyncio.wait_for(client.expunge(), timeout=10)
        await client.logout()
        return True
    except Exception as exc:
        logger.error(f"[IMAP] delete_email_imap failed: {exc}")
        try:
            await client.logout()
        except Exception:
            pass
        return False


async def pull_gmail(gmail_address: str, app_password: str, max_fetch: int = 50) -> list[dict]:
    """Convenience wrapper for Gmail IMAP using App Password."""
    return await pull_emails_imap(
        imap_host=GMAIL_IMAP_HOST,
        imap_port=GMAIL_IMAP_PORT,
        username=gmail_address,
        password=app_password,
        max_fetch=max_fetch,
    )
