from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sql_update
from pydantic import BaseModel, EmailStr

from app.db.database import get_db
from app.models.email_config_model import EmailConfig
from app.services.crypto_service import encrypt, decrypt

router = APIRouter()


# ─── Pydantic Schemas ─────────────────────────────────────────────

class SenderSchema(BaseModel):
    name: str
    email: EmailStr
    replyTo: Optional[str] = None


class GmailSchema(BaseModel):
    appPassword: str


class SmtpSchema(BaseModel):
    host: str
    port: int
    secure: bool = False
    username: Optional[str] = None
    password: Optional[str] = None


class EmailConfigCreate(BaseModel):
    name: str
    provider: str          # "gmail" | "smtp"
    sender: SenderSchema
    isDefault: bool = False
    gmail: Optional[GmailSchema] = None
    smtp: Optional[SmtpSchema] = None


class EmailConfigUpdate(BaseModel):
    name: Optional[str] = None
    sender: Optional[SenderSchema] = None
    isDefault: Optional[bool] = None


class TestEmailRequest(BaseModel):
    testEmail: EmailStr


class SendTemplateTestRequest(BaseModel):
    to: EmailStr
    subject: Optional[str] = "Email Test"
    html: str


class PublicSendTestRequest(BaseModel):
    to: EmailStr
    subject: Optional[str] = "Email Test - Email Builder"
    html: str
    gmailEmail: EmailStr
    gmailAppPassword: str


# ─── Helpers ──────────────────────────────────────────────────────

def _to_response(cfg: EmailConfig) -> dict:
    """Serialize EmailConfig → frontend dict. Credentials never exposed."""
    result = {
        "_id": cfg.id,
        "name": cfg.name,
        "provider": cfg.provider,
        "isDefault": cfg.is_default,
        "sender": {
            "name": cfg.sender_name,
            "email": cfg.sender_email,
            "replyTo": cfg.reply_to,
        },
    }
    if cfg.provider == "smtp":
        result["smtp"] = {
            "host": cfg.smtp_host,
            "port": cfg.smtp_port,
            "secure": cfg.smtp_secure,
            "username": cfg.smtp_username,
            # password KHÔNG bao giờ trả về
        }
    return result


async def _get_smtp_params(cfg: EmailConfig) -> dict:
    """Decrypt credentials → trả về kwargs cho aiosmtplib.send()."""
    if cfg.provider == "gmail":
        return {
            "hostname": "smtp.gmail.com",
            "port": 587,
            "username": cfg.gmail_address,
            "password": decrypt(cfg.gmail_app_password_enc or ""),
            "start_tls": True,
        }

    password = decrypt(cfg.smtp_password_enc or "")
    params = {
        "hostname": cfg.smtp_host,
        "port": cfg.smtp_port,
    }
    if cfg.smtp_port == 465:
        params["use_tls"] = True
    elif cfg.smtp_port == 587:
        params["start_tls"] = True
    # Port 25 (relay) — không cần auth
    if cfg.smtp_username and cfg.smtp_port != 25:
        params["username"] = cfg.smtp_username
        params["password"] = password
    return params


async def _unset_all_defaults(portal_user_id: str, db: AsyncSession):
    """Unset is_default cho toàn bộ config của user này."""
    await db.execute(
        sql_update(EmailConfig)
        .where(EmailConfig.portal_user_id == portal_user_id)
        .values(is_default=False)
    )


# ─── Endpoints ────────────────────────────────────────────────────

@router.get("/email-config")
async def list_configs(
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lấy danh sách cấu hình email của user. Default hiển thị trên cùng."""
    result = await db.execute(
        select(EmailConfig)
        .where(
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        )
        .order_by(EmailConfig.is_default.desc(), EmailConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return {"success": True, "data": [_to_response(c) for c in configs]}


@router.post("/email-config", status_code=201)
async def create_config(
    data: EmailConfigCreate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Tạo cấu hình mới (Gmail hoặc SMTP).
    Credentials được encrypt bằng Fernet trước khi lưu DB.
    Nếu isDefault=True, unset tất cả config cũ của user trước.
    """
    if data.provider == "gmail":
        if not data.gmail or not data.gmail.appPassword:
            raise HTTPException(status_code=422, detail="Gmail App Password là bắt buộc")
    elif data.provider == "smtp":
        if not data.smtp or not data.smtp.host or not data.smtp.port:
            raise HTTPException(status_code=422, detail="SMTP host và port là bắt buộc")
        if data.smtp.port != 25 and (not data.smtp.username or not data.smtp.password):
            raise HTTPException(status_code=422, detail="Username và Password là bắt buộc cho port 587/465")
    else:
        raise HTTPException(status_code=422, detail="provider phải là 'gmail' hoặc 'smtp'")

    if data.isDefault:
        await _unset_all_defaults(portal_user_id, db)

    cfg = EmailConfig(
        portal_user_id=portal_user_id,
        name=data.name,
        provider=data.provider,
        is_default=data.isDefault,
        sender_name=data.sender.name,
        sender_email=data.sender.email,
        reply_to=data.sender.replyTo,
    )

    if data.provider == "gmail":
        cfg.gmail_address = data.sender.email
        cfg.gmail_app_password_enc = encrypt(data.gmail.appPassword)
    elif data.provider == "smtp":
        cfg.smtp_host = data.smtp.host
        cfg.smtp_port = data.smtp.port
        cfg.smtp_secure = data.smtp.secure
        cfg.smtp_username = data.smtp.username
        if data.smtp.password:
            cfg.smtp_password_enc = encrypt(data.smtp.password)

    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"success": True, "data": _to_response(cfg)}


@router.put("/email-config/{config_id}")
async def update_config(
    config_id: int,
    data: EmailConfigUpdate,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Cập nhật cấu hình: chỉ name, sender, isDefault.
    Credentials (password / appPassword) KHÔNG được cập nhật ở đây.
    """
    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.id == config_id,
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình")

    if data.name is not None:
        cfg.name = data.name
    if data.sender is not None:
        cfg.sender_name = data.sender.name
        cfg.sender_email = data.sender.email
        cfg.reply_to = data.sender.replyTo
    if data.isDefault is not None:
        if data.isDefault:
            await _unset_all_defaults(portal_user_id, db)
        cfg.is_default = data.isDefault

    await db.commit()
    await db.refresh(cfg)
    return {"success": True, "data": _to_response(cfg)}


@router.delete("/email-config/{config_id}")
async def delete_config(
    config_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete — đánh dấu is_active=False, không xóa record khỏi DB."""
    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.id == config_id,
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình")

    cfg.is_active = False
    await db.commit()
    return {"success": True}


@router.post("/email-config/{config_id}/set-default")
async def set_default(
    config_id: int,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Đặt một config làm mặc định.
    Unset toàn bộ config cũ → set config này is_default=True.
    """
    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.id == config_id,
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình")

    await _unset_all_defaults(portal_user_id, db)
    cfg.is_default = True
    await db.commit()
    await db.refresh(cfg)
    return {"success": True, "data": _to_response(cfg)}


@router.post("/email-config/{config_id}/test")
async def test_config(
    config_id: int,
    body: TestEmailRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Gửi email test để kiểm tra cấu hình.
    Decrypt credentials → kết nối SMTP/Gmail → gửi HTML email.
    """
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    result = await db.execute(
        select(EmailConfig).where(
            EmailConfig.id == config_id,
            EmailConfig.portal_user_id == portal_user_id,
            EmailConfig.is_active == True,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình")

    try:
        smtp_params = await _get_smtp_params(cfg)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ Test Email — Cấu hình hoạt động tốt"
        msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
        msg["To"] = body.testEmail

        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:40px auto;padding:32px;
                    background:#f8fafc;border-radius:16px;border:1px solid #e2e8f0">
          <h2 style="color:#4f46e5;margin-top:0">Email test thành công! 🎉</h2>
          <p style="color:#475569">
            Cấu hình <strong>{cfg.name}</strong> đang hoạt động bình thường.
          </p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0" />
          <p style="color:#94a3b8;font-size:12px;margin:0">
            Provider: {cfg.provider.upper()} · Gửi từ: {cfg.sender_email}
          </p>
        </div>"""
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(msg, **smtp_params)
        return {"success": True, "message": "Email test đã được gửi thành công"}

    except aiosmtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="Xác thực thất bại — kiểm tra lại email/App Password")
    except aiosmtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail="Không thể kết nối SMTP server — kiểm tra host/port")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gửi thất bại: {str(e)}")


@router.post("/admin/system-email-config/send-template-test")
async def send_template_test(
    body: SendTemplateTestRequest,
    portal_user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Gửi email test với HTML tùy chỉnh từ editor/preview.
    Dùng email config default của user để gửi.
    """
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # Lấy config default, fallback về config mới nhất nếu không có default
    result = await db.execute(
        select(EmailConfig)
        .where(EmailConfig.portal_user_id == portal_user_id, EmailConfig.is_active == True)
        .order_by(EmailConfig.is_default.desc(), EmailConfig.created_at.desc())
    )
    cfg = result.scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Chưa có cấu hình email nào. Vui lòng thiết lập email config trước.")

    try:
        smtp_params = await _get_smtp_params(cfg)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = body.subject
        msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
        msg["To"] = body.to

        msg.attach(MIMEText(body.html, "html"))

        await aiosmtplib.send(msg, **smtp_params)
        return {"success": True, "message": "Email đã được gửi thành công!"}

    except aiosmtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="Xác thực thất bại — kiểm tra lại email/App Password")
    except aiosmtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail="Không thể kết nối SMTP server — kiểm tra host/port")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gửi thất bại: {str(e)}")


@router.post("/public/email/send-test")
async def public_send_test(body: PublicSendTestRequest):
    """
    Public endpoint (không cần auth) — dùng Gmail + App Password do user cung cấp để gửi email test từ editor.
    """
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = body.subject
        msg["From"] = body.gmailEmail
        msg["To"] = body.to
        msg.attach(MIMEText(body.html, "html"))

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            username=body.gmailEmail,
            password=body.gmailAppPassword,
            start_tls=True,
        )
        return {"success": True, "message": "Email đã được gửi thành công!"}

    except aiosmtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="Xác thực Gmail thất bại — kiểm tra lại Gmail và App Password")
    except aiosmtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail="Không thể kết nối Gmail SMTP")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gửi thất bại: {str(e)}")
