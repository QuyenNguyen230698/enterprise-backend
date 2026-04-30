from typing import Optional
import os
import uuid
import base64
from io import BytesIO
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from PIL import Image, ImageOps, ImageFilter, ImageChops

from app.db.database import get_db
from app.models.user_model import User
from app.models.tenant_model import Tenant
from app.models.user_signature_model import UserSignature

router = APIRouter()

SIGNATURE_UPLOAD_DIR = Path(os.getenv("SIGNATURE_UPLOAD_DIR", "uploads/signhub-signatures"))
SIGNATURE_PUBLIC_PREFIX = os.getenv("SIGNATURE_PUBLIC_PREFIX", "/static/signhub-signatures")
LEGACY_SIGNATURE_UPLOAD_DIR = Path("uploads/signhub_signatures")


def _signature_base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


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
    return f"{_signature_base_url()}{SIGNATURE_PUBLIC_PREFIX}/{file_name}"


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


def _delete_signature_file_by_url(signature_url: Optional[str]) -> None:
    if not signature_url:
        return
    try:
        parsed = urlparse(signature_url)
        if not parsed.path or not parsed.path.startswith(SIGNATURE_PUBLIC_PREFIX):
            return
        file_name = parsed.path[len(SIGNATURE_PUBLIC_PREFIX):].lstrip("/")
        if not file_name:
            return
        file_path = SIGNATURE_UPLOAD_DIR / file_name
        if file_path.exists():
            file_path.unlink()
    except Exception:
        # Ignore cleanup errors so they do not block API actions.
        pass


def _signature_file_exists(signature_url: Optional[str]) -> bool:
    if not signature_url:
        return False
    try:
        parsed = urlparse(signature_url)
        if not parsed.path.startswith(SIGNATURE_PUBLIC_PREFIX):
            return False
        file_name = parsed.path[len(SIGNATURE_PUBLIC_PREFIX):].lstrip("/")
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

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    avatar_url = f"{base_url}/static/avatars/{filename}"

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

    sig = await _get_signature(portal_user_id, db)
    if not sig:
        sig = UserSignature(portal_user_id=portal_user_id)
        db.add(sig)

    old_signature_url = sig.signature_image_url
    sig.signature_type = payload.signature_type
    if payload.signature_type == "uploaded":
        sig.signature_image_url = payload.signature_data
        sig.signature_data = None
    else:
        content, ext = _decode_data_url_to_bytes(payload.signature_data)
        signature_url = _store_signature_file(portal_user_id, content, ext)
        sig.signature_image_url = signature_url
        sig.signature_data = None

    if old_signature_url and old_signature_url != sig.signature_image_url:
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
