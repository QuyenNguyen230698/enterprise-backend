from typing import Optional
import os
import uuid
import base64
import hashlib
import hmac
import random
import secrets
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete
from pydantic import BaseModel
from PIL import Image, ImageOps, ImageFilter, ImageChops

from app.db.database import get_db
from app.models.user_model import User
from app.models.tenant_model import Tenant
from app.models.user_signature_model import UserSignature
from app.models.signature_otp_model import SignatureOtp

router = APIRouter()

SIGNATURE_UPLOAD_DIR = Path(os.getenv("SIGNATURE_UPLOAD_DIR", "uploads/signhub-signatures"))
SIGNATURE_PUBLIC_PREFIX = os.getenv("SIGNATURE_PUBLIC_PREFIX", "/static/signhub-signatures")
LEGACY_SIGNATURE_UPLOAD_DIR = Path("uploads/signhub_signatures")


def _signature_base_url() -> str:
    return os.getenv("BASE_URL", "").rstrip("/")


def _migrate_legacy_signature_files() -> None:
    SIGNATURE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_SIGNATURE_UPLOAD_DIR.exists() or LEGACY_SIGNATURE_UPLOAD_DIR == SIGNATURE_UPLOAD_DIR:
        return
    for old_file in LEGACY_SIGNATURE_UPLOAD_DIR.iterdir():
        if not old_file.is_file():
            continue
        new_file = SIGNATURE_UPLOAD_DIR / old_file.name
        if not new_file.exists():
            old_file.replace(new_file)


def _store_signature_file(portal_user_id: str, content: bytes, ext: str = "png") -> str:
    SIGNATURE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_ext = (ext or "png").lower().replace(".", "")
    file_name = f"signhub_{portal_user_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{safe_ext}"
    (SIGNATURE_UPLOAD_DIR / file_name).write_bytes(content)
    # URL routed through /api/v1/profile/signature-image?path= so Cloudflare passes it
    base = _signature_base_url()
    static_path = f"{SIGNATURE_PUBLIC_PREFIX}/{file_name}"
    return f"{base}/api/v1/profile/signature-image?path={static_path}"


def _decode_data_url_to_bytes(data_url: str) -> tuple[bytes, str]:
    if not data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Invalid signature_data format")
    try:
        header, encoded = data_url.split(",", 1)
        image_type = header.split(";")[0].split("/")[-1].lower()
        content = base64.b64decode(encoded)
        return content, image_type or "png"
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 signature data") from exc


def _build_signature_preview_data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _scan_signature_to_blue_png(content: bytes) -> bytes:
    try:
        image = Image.open(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Cannot read image file") from exc

    rgba = image.convert("RGBA")
    gray = ImageOps.grayscale(rgba)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))

    # Dynamic threshold from image histogram helps with photos under different lighting.
    histogram = gray.histogram()
    total_pixels = gray.width * gray.height
    cumulative = 0
    threshold = 180
    for idx, value in enumerate(histogram):
        cumulative += value
        if cumulative >= total_pixels * 0.82:
            threshold = max(120, min(210, idx))
            break

    ink_mask = gray.point(lambda p: 255 if p < threshold else 0, mode="L")
    alpha = rgba.getchannel("A")
    ink_mask = ImageChops.multiply(ink_mask, alpha)
    ink_mask = ink_mask.filter(ImageFilter.MedianFilter(size=3))
    ink_mask = ink_mask.filter(ImageFilter.GaussianBlur(radius=0.6))

    bbox = ink_mask.getbbox()
    if not bbox:
        raise HTTPException(status_code=400, detail="Không phát hiện nét chữ ký trong ảnh")

    pad = 10
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(rgba.width, bbox[2] + pad)
    bottom = min(rgba.height, bbox[3] + pad)
    cropped_mask = ink_mask.crop((left, top, right, bottom))

    non_transparent = sum(1 for px in cropped_mask.getdata() if px > 16)
    if non_transparent < 120:
        raise HTTPException(status_code=400, detail="Ảnh chữ ký quá ít nét, vui lòng chọn ảnh rõ hơn")

    result = Image.new("RGBA", cropped_mask.size, (0, 0, 0, 0))
    blue_layer = Image.new("RGBA", cropped_mask.size, (25, 60, 185, 255))
    result.paste(blue_layer, mask=cropped_mask)

    out = BytesIO()
    result.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _decode_image_payload_to_bytes(image_data: str) -> bytes:
    if not image_data:
        raise HTTPException(status_code=400, detail="image_data is required")
    try:
        if image_data.startswith("data:image/"):
            _, encoded = image_data.split(",", 1)
            return base64.b64decode(encoded)
        return base64.b64decode(image_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image_data base64 payload") from exc


async def _read_signature_upload_content(
    request: Request,
    file: Optional[UploadFile],
    max_size: int = 20 * 1024 * 1024,
) -> bytes:
    if file is not None:
        allowed = {"image/jpeg", "image/png"}
        if file.content_type not in allowed:
            raise HTTPException(status_code=400, detail="Only png, jpg, jpeg allowed")
        content = await file.read()
    else:
        try:
            payload = SignatureImagePayload(**(await request.json()))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body. Expect { image_data: base64 }") from exc
        content = _decode_image_payload_to_bytes(payload.image_data)

    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty image payload")
    return content


def _extract_signature_filename(signature_url: Optional[str]) -> Optional[str]:
    """Extract just the filename from either URL format:
    - new: https://host/api/v1/profile/signature-image?path=/static/signhub-signatures/file.png
    - legacy: https://host/static/signhub-signatures/file.png
    """
    if not signature_url:
        return None
    try:
        parsed = urlparse(signature_url)
        # New format: ?path=... query param
        qs = parse_qs(parsed.query)
        path_param = qs.get("path", [None])[0]
        if path_param:
            file_name = path_param.split("/")[-1]
            return file_name if file_name else None
        # Legacy format: path directly contains /static/signhub-signatures/
        if parsed.path.startswith(SIGNATURE_PUBLIC_PREFIX):
            file_name = parsed.path[len(SIGNATURE_PUBLIC_PREFIX):].lstrip("/")
            return file_name if file_name else None
        return None
    except Exception:
        return None


def _delete_signature_file_by_url(signature_url: Optional[str]) -> None:
    if not signature_url:
        return
    try:
        file_name = _extract_signature_filename(signature_url)
        if not file_name:
            return
        file_path = SIGNATURE_UPLOAD_DIR / file_name
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass


def _signature_file_exists(signature_url: Optional[str]) -> bool:
    if not signature_url:
        return False
    try:
        file_name = _extract_signature_filename(signature_url)
        if not file_name:
            return False
        return (SIGNATURE_UPLOAD_DIR / file_name).exists()
    except Exception:
        return False


_migrate_legacy_signature_files()


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    dept_code: Optional[str] = None
    title: Optional[str] = None
    avatar_url: Optional[str] = None

class SignatureUpdate(BaseModel):
    signature_type: str
    signature_data: str
    verify_token: str  # HMAC token issued by /profile/signature/verify-otp


class SignatureImagePayload(BaseModel):
    image_data: str


async def _get_signature(portal_user_id: str, db: AsyncSession) -> Optional[UserSignature]:
    result = await db.execute(select(UserSignature).where(UserSignature.portal_user_id == portal_user_id))
    return result.scalar_one_or_none()


def _to_profile(user: User, tenant: Optional[Tenant] = None) -> dict:
    """Map User model → camelCase response shape FE expects."""
    full_name = user.full_name or user.name or ""
    parts = full_name.strip().split(" ", 1) if full_name else ["", ""]
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""

    return {
        # Identity
        "portal_user_id": user.portal_user_id,
        "email": user.email,
        "userCode": user.e_code or user.hr_code or user.portal_user_id or "",
        "provider": "google" if user.google_id else "local",
        # Name fields — FE uses firstName/lastName/fullName
        "fullName": full_name,
        "full_name": full_name,
        "firstName": first,
        "lastName": last,
        "display_name": user.display_name or full_name,
        # Avatar — FE uses `avatar`, backend stores `avatar_url`
        "avatar": user.avatar_url or "",
        "avatar_url": user.avatar_url or "",
        # Contact / Work
        "phone": user.phone or "",
        "address": user.site or "",
        "department": user.department or "",
        "dept_code": user.dept_code or user.department or "",
        "title": user.title or "",
        "joined_at": user.joined_at or "",
        "joining_date": user.joined_at or "",
        "site": user.site or "",
        "site_country": user.site_country or "",
        "hr_code": user.hr_code or "",
        "e_code": user.e_code or user.hr_code or "",
        # Org
        "tenant_id": user.tenant_id,
        "tenant_name": tenant.name if tenant else None,
        "tenant_domain": tenant.domain if tenant else None,
        "role": user.role,
        "isActive": True,
        "roles": [user.role] if user.role else [],
        # Stub subscription/quota/usage — no payment system yet
        "subscription": {"plan": "basic", "status": "active"},
        "quota": {"imageUploadLimit": 0, "dailyEmailLimit": 50},
        "usage": {"imagesUploaded": 0, "emailsSentToday": 0},
        "preferredPaymentProvider": "payos",
        "subscriptions": {
            "email": {"plan": "basic", "status": "active"},
        },
    }


async def _get_user(portal_user_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/profile")
async def get_profile(
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(portal_user_id, db)
    sig = await _get_signature(portal_user_id, db)
    tenant = None
    if user.tenant_id:
        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
    data = _to_profile(user, tenant)
    data["has_signature"] = bool(sig and (sig.signature_data or sig.signature_image_url))
    data["signature_type"] = sig.signature_type if sig else None
    data["signature_image_url"] = sig.signature_image_url if sig else None
    return {"success": True, "data": data}


@router.put("/profile")
async def update_profile(
    data: ProfileUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(portal_user_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return {"success": True, "data": _to_profile(user)}


@router.post("/profile/upload-avatar")
async def upload_avatar(
    portal_user_id: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    ALLOWED = {"image/jpeg", "image/png", "image/gif"}
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail="Only jpeg, png, gif allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    upload_dir = Path("uploads/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    (upload_dir / filename).write_bytes(content)

    base_url = os.getenv("BASE_URL", "").rstrip("/")
    avatar_url = f"{base_url}/api/v1/profile/signature-image?path=/static/avatars/{filename}"

    user = await _get_user(portal_user_id, db)
    user.avatar_url = avatar_url
    await db.commit()

    return {"success": True, "data": {"url": avatar_url}}


@router.get("/profile/signature")
async def get_signature(
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    sig = await _get_signature(portal_user_id, db)
    if not sig:
        return {"success": True, "data": {"has_signature": False, "signature_type": None, "signature_image_url": None, "signature_data": None}}
    if sig.signature_image_url and not _signature_file_exists(sig.signature_image_url):
        # Auto-heal dangling DB URL when file no longer exists on disk.
        sig.signature_image_url = None
        sig.signature_data = None
        await db.commit()
        await db.refresh(sig)
    return {
        "success": True,
        "data": {
            "has_signature": bool(sig.signature_data or sig.signature_image_url),
            "signature_type": sig.signature_type,
            "signature_image_url": sig.signature_image_url,
            "signature_data": sig.signature_data,
        },
    }


@router.put("/profile/signature")
async def save_signature(
    payload: SignatureUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if payload.signature_type not in {"drawn", "uploaded"}:
        raise HTTPException(status_code=400, detail="signature_type must be drawn/uploaded")
    if not payload.signature_data:
        raise HTTPException(status_code=400, detail="signature_data is required")

    # Validate OTP verify_token — must be a verified, unexpired, unused token
    if not payload.verify_token:
        raise HTTPException(status_code=403, detail="Yêu cầu xác thực OTP trước khi lưu chữ ký.")
    now = datetime.now(timezone.utc)
    token_result = await db.execute(
        select(SignatureOtp).where(
            SignatureOtp.portal_user_id == portal_user_id,
            SignatureOtp.verify_token == payload.verify_token,
            SignatureOtp.verified == True,
            SignatureOtp.expires_at > now,
        )
    )
    otp_record = token_result.scalars().first()
    if not otp_record:
        raise HTTPException(status_code=403, detail="Token xác thực OTP không hợp lệ hoặc đã hết hạn.")
    # Consume token — one-time use
    await db.delete(otp_record)
    await db.flush()

    # Resolve new values before touching DB to avoid partial/empty records on error
    if payload.signature_type == "uploaded":
        new_image_url = payload.signature_data
    else:
        content, ext = _decode_data_url_to_bytes(payload.signature_data)
        new_image_url = _store_signature_file(portal_user_id, content, ext)

    sig = await _get_signature(portal_user_id, db)
    old_signature_url = sig.signature_image_url if sig else None
    if not sig:
        sig = UserSignature(portal_user_id=portal_user_id)
        db.add(sig)

    sig.signature_type = payload.signature_type
    sig.signature_image_url = new_image_url
    sig.signature_data = None

    if old_signature_url and old_signature_url != new_image_url:
        _delete_signature_file_by_url(old_signature_url)

    await db.commit()
    await db.refresh(sig)
    return {
        "success": True,
        "data": {
            "has_signature": True,
            "signature_type": sig.signature_type,
            "signature_image_url": sig.signature_image_url,
            "signature_data": sig.signature_data,
        },
    }


@router.delete("/profile/signatures/purge-all")
async def purge_all_signatures(db: AsyncSession = Depends(get_db)):
    """Hard-reset: xoá toàn bộ file vật lý + truncate bảng user_signatures."""
    deleted_files = 0
    if SIGNATURE_UPLOAD_DIR.exists():
        for f in SIGNATURE_UPLOAD_DIR.iterdir():
            if f.is_file():
                f.unlink()
                deleted_files += 1
    result = await db.execute(sql_delete(UserSignature))
    await db.commit()
    return {
        "success": True,
        "deleted_files": deleted_files,
        "deleted_records": result.rowcount,
    }


@router.post("/profile/upload-signature")
async def upload_signature(
    request: Request,
    portal_user_id: str = Query(...),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    content = await _read_signature_upload_content(request, file)

    scanned_png = _scan_signature_to_blue_png(content)

    sig = await _get_signature(portal_user_id, db)
    old_signature_url = sig.signature_image_url if sig else None
    signature_url = _store_signature_file(portal_user_id, scanned_png, "png")

    if not sig:
        sig = UserSignature(portal_user_id=portal_user_id)
        db.add(sig)
    sig.signature_type = "uploaded"
    sig.signature_image_url = signature_url
    sig.signature_data = None
    await db.commit()

    if old_signature_url and old_signature_url != signature_url:
        _delete_signature_file_by_url(old_signature_url)

    return {
        "success": True,
        "data": {
            "url": signature_url,
            "preview_data_url": _build_signature_preview_data_url(scanned_png),
        },
    }


@router.post("/profile/scan-signature")
async def scan_signature_preview(
    request: Request,
    file: Optional[UploadFile] = File(None),
):
    content = await _read_signature_upload_content(request, file)

    scanned_png = _scan_signature_to_blue_png(content)
    return {
        "success": True,
        "data": {
            "preview_data_url": _build_signature_preview_data_url(scanned_png),
        },
    }


@router.delete("/profile/signature")
async def delete_signature(
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    sig = await _get_signature(portal_user_id, db)
    if not sig:
        return {"success": True, "data": {"deleted": False, "message": "No signature found"}}

    _delete_signature_file_by_url(sig.signature_image_url)
    await db.delete(sig)
    await db.commit()
    return {"success": True, "data": {"deleted": True}}


# ─── SignHub OTP ───────────────────────────────────────────────────
# Luật GDDT 2023 / NĐ 13/2023 — Mức A: xác thực danh tính người ký
# SHA-256 hash · max 5 attempts · rate-limit 60s · verify_token HMAC

_OTP_TTL_SECONDS   = 300   # OTP hết hạn sau 5 phút
_OTP_RATE_LIMIT_S  = 60    # Không cho gửi lại trước 60s
_OTP_MAX_ATTEMPTS  = 5
_OTP_HMAC_SECRET   = os.getenv("JWT_SECRET", "fallback-secret")


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _make_verify_token(portal_user_id: str, otp_id: int) -> str:
    msg = f"{portal_user_id}:{otp_id}:{secrets.token_hex(16)}"
    return hmac.new(_OTP_HMAC_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


async def _get_active_otp(portal_user_id: str, db: AsyncSession) -> Optional[SignatureOtp]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SignatureOtp)
        .where(
            SignatureOtp.portal_user_id == portal_user_id,
            SignatureOtp.expires_at > now,
            SignatureOtp.verified == False,
        )
        .order_by(SignatureOtp.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _send_otp_email(to_email: str, otp_code: str, user_name: str, db: AsyncSession) -> None:
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from app.models.email_config_model import EmailConfig
    from app.api.v1.email_config_route import _get_smtp_params

    result = await db.execute(
        select(EmailConfig)
        .where(EmailConfig.portal_user_id != None, EmailConfig.is_active == True)
        .order_by(EmailConfig.is_default.desc(), EmailConfig.created_at.desc())
        .limit(1)
    )
    cfg = result.scalars().first()

    html_body = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#fff;border-radius:12px;border:1px solid #e5e7eb">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px">
        <div style="width:36px;height:36px;border-radius:8px;background:#1d4ed8;display:flex;align-items:center;justify-content:center">
          <span style="color:#fff;font-size:18px">✍</span>
        </div>
        <span style="font-size:16px;font-weight:800;color:#111827">SignHub</span>
      </div>
      <h2 style="font-size:20px;font-weight:800;color:#111827;margin:0 0 8px">Xác thực chữ ký điện tử</h2>
      <p style="font-size:14px;color:#6b7280;margin:0 0 24px">
        Xin chào <strong>{user_name}</strong>, mã OTP để thiết lập chữ ký SignHub của bạn là:
      </p>
      <div style="text-align:center;margin:0 0 24px">
        <div style="display:inline-block;background:#eff6ff;border:2px solid #bfdbfe;border-radius:12px;padding:20px 40px">
          <span style="font-size:40px;font-weight:900;letter-spacing:12px;color:#1d4ed8;font-family:monospace">{otp_code}</span>
        </div>
      </div>
      <p style="font-size:12px;color:#9ca3af;margin:0 0 4px">⏱ Mã có hiệu lực trong <strong>5 phút</strong>.</p>
      <p style="font-size:12px;color:#9ca3af;margin:0 0 4px">🔒 Không chia sẻ mã này với bất kỳ ai.</p>
      <p style="font-size:12px;color:#9ca3af;margin:0">📋 Cơ sở pháp lý: Luật GDDT 2023 (20/2023/QH15) · NĐ 13/2023/NĐ-CP · Mức A nội bộ.</p>
      <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0">
      <p style="font-size:11px;color:#d1d5db;margin:0;text-align:center">Enterprise SignHub — Chữ ký điện tử nội bộ</p>
    </div>
    """

    if cfg:
        smtp_params = await _get_smtp_params(cfg)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[SignHub] Mã OTP xác thực chữ ký: {otp_code}"
        msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
        msg["To"] = to_email
        # Web OTP API hint — browser/mobile email client dùng để autocomplete
        msg["X-OTP-Code"] = otp_code
        msg.attach(MIMEText(html_body, "html"))
        try:
            await aiosmtplib.send(msg, **smtp_params)
            return
        except Exception:
            pass  # fallback: log nhưng không block — OTP vẫn được tạo

    # Fallback: log ra console (development / chưa có email config)
    import logging
    logging.getLogger("api.access").warning(
        f"[SignHub OTP] No email config — OTP for {to_email}: {otp_code}"
    )


class OtpSendRequest(BaseModel):
    portal_user_id: str


class OtpVerifyRequest(BaseModel):
    portal_user_id: str
    otp_code: str


@router.post("/profile/signature/send-otp")
async def send_signature_otp(
    payload: OtpSendRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Gửi OTP 6 số đến email của user để xác thực trước khi lưu chữ ký.
    Rate-limit: không gửi lại trong vòng 60s nếu OTP cũ còn hiệu lực.
    """
    # Lấy user để lấy email
    result = await db.execute(
        select(User).where(User.portal_user_id == payload.portal_user_id)
    )
    user = result.scalars().first()
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

    now = datetime.now(timezone.utc)

    # Rate-limit: kiểm tra OTP cũ còn trong 60s đầu
    active = await _get_active_otp(payload.portal_user_id, db)
    if active:
        elapsed = (now - active.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < _OTP_RATE_LIMIT_S:
            wait = int(_OTP_RATE_LIMIT_S - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Vui lòng chờ {wait} giây trước khi gửi lại OTP."
            )
        # OTP cũ đã qua 60s — xoá để tạo mới
        await db.execute(
            sql_delete(SignatureOtp).where(
                SignatureOtp.portal_user_id == payload.portal_user_id,
                SignatureOtp.verified == False,
            )
        )

    # Tạo OTP 6 số cryptographically secure
    otp_code = f"{random.SystemRandom().randint(0, 999999):06d}"
    otp_record = SignatureOtp(
        portal_user_id=payload.portal_user_id,
        otp_hash=_hash_otp(otp_code),
        attempts=0,
        verified=False,
        expires_at=now + timedelta(seconds=_OTP_TTL_SECONDS),
    )
    db.add(otp_record)
    await db.commit()
    await db.refresh(otp_record)

    # Gửi email
    user_name = user.display_name or user.full_name or user.name or user.email.split("@")[0]
    await _send_otp_email(user.email, otp_code, user_name, db)

    # Trả về masked email để frontend hiển thị "OTP đã gửi đến ****@..."
    parts = user.email.split("@")
    masked = parts[0][:2] + "***@" + parts[1] if len(parts) == 2 else "****"
    return {
        "success": True,
        "data": {
            "masked_email": masked,
            "expires_in": _OTP_TTL_SECONDS,
            "rate_limit_seconds": _OTP_RATE_LIMIT_S,
        },
    }


@router.post("/profile/signature/verify-otp")
async def verify_signature_otp(
    payload: OtpVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Xác thực OTP. Trả về verify_token (HMAC) dùng một lần để PUT /profile/signature.
    SHA-256 timing-safe compare · max 5 attempts · tự xoá sau khi verified.
    """
    if not payload.otp_code or len(payload.otp_code) != 6 or not payload.otp_code.isdigit():
        raise HTTPException(status_code=400, detail="OTP phải là 6 chữ số.")

    active = await _get_active_otp(payload.portal_user_id, db)
    if not active:
        raise HTTPException(status_code=400, detail="Mã OTP đã hết hạn hoặc không tồn tại. Vui lòng yêu cầu mã mới.")

    if active.attempts >= _OTP_MAX_ATTEMPTS:
        await db.delete(active)
        await db.commit()
        raise HTTPException(status_code=400, detail="Đã nhập sai quá 5 lần. Vui lòng yêu cầu mã OTP mới.")

    # Timing-safe compare
    incoming_hash = _hash_otp(payload.otp_code)
    if not hmac.compare_digest(incoming_hash, active.otp_hash):
        active.attempts += 1
        remaining = _OTP_MAX_ATTEMPTS - active.attempts
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Mã OTP không đúng. Còn {remaining} lần thử." if remaining > 0
                   else "Đã hết lượt thử. Vui lòng yêu cầu mã mới."
        )

    # OTP đúng — phát verify_token một lần
    verify_token = _make_verify_token(payload.portal_user_id, active.id)
    active.verified = True
    active.verify_token = verify_token
    # Đặt expires_at còn 10 phút để dùng token lưu chữ ký
    active.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.commit()

    return {
        "success": True,
        "data": {
            "verify_token": verify_token,
            "expires_in": 600,
        },
    }


# ─── Stub endpoints — FE calls these but no payment system yet ────

@router.get("/subscriptions/my-subscription")
async def my_subscription(portal_user_id: str = Query(...)):
    return {"result": False, "data": None}


@router.get("/subscriptions/saved-cards")
async def saved_cards(portal_user_id: str = Query(...)):
    return {"result": True, "data": []}


@router.get("/subscriptions/history")
async def subscription_history(portal_user_id: str = Query(...)):
    return {"success": True, "data": []}


@router.get("/subscriptions/current")
async def subscription_current(
    portal_user_id: str = Query(...),
    type: Optional[str] = Query(None),
):
    return {"result": False, "data": None}


@router.get("/products/public")
async def products_public(type: Optional[str] = Query(None)):
    return {"success": True, "data": []}
