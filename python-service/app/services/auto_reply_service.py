"""
Auto-reply service — Phase 3.

Khi có email ứng viên mới được lưu vào DB, gọi trigger_auto_reply()
để kiểm tra có rule nào khớp không và gửi reply tự động.

Chạy hoàn toàn trong FastAPI BackgroundTasks:
  - delay_minutes == 0 → gửi ngay
  - delay_minutes > 0  → asyncio.sleep trước khi gửi
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.recruitment_model import (
    CandidateEmail,
    RecruitmentAutoRule,
    RecruitmentReply,
)
from app.models.email_config_model import EmailConfig
from app.models.template_model import Template
from app.services.recruitment_email_service import send_reply

logger = logging.getLogger(__name__)


async def _execute_rule(
    rule: RecruitmentAutoRule,
    candidate: CandidateEmail,
) -> None:
    """
    Chờ delay_minutes rồi gửi auto-reply cho 1 ứng viên theo 1 rule.
    Mở session DB riêng vì chạy trong background task (request session đã đóng).
    """
    if rule.delay_minutes and rule.delay_minutes > 0:
        await asyncio.sleep(rule.delay_minutes * 60)

    async with AsyncSessionLocal() as db:
        # Kiểm tra rule vẫn active (user có thể tắt trong lúc delay)
        rule_check = await db.execute(
            select(RecruitmentAutoRule).where(
                RecruitmentAutoRule.id == rule.id,
                RecruitmentAutoRule.is_active == True,
            )
        )
        if not rule_check.scalar_one_or_none():
            logger.info(f"[AUTO-REPLY] Rule {rule.id} đã bị tắt, bỏ qua.")
            return

        # Tránh gửi trùng: kiểm tra đã có reply nào theo rule này cho candidate chưa
        dup = await db.execute(
            select(RecruitmentReply).where(
                RecruitmentReply.candidate_email_id == candidate.id,
                RecruitmentReply.bulk_id == f"auto:{rule.id}",
            )
        )
        if dup.scalar_one_or_none():
            logger.info(f"[AUTO-REPLY] Đã reply trước đó cho candidate {candidate.id}, bỏ qua.")
            return

        # Resolve email config
        cfg = None
        if rule.email_config_id:
            cfg_result = await db.execute(
                select(EmailConfig).where(
                    EmailConfig.id == rule.email_config_id,
                    EmailConfig.is_active == True,
                )
            )
            cfg = cfg_result.scalar_one_or_none()

        if not cfg:
            cfg_result = await db.execute(
                select(EmailConfig).where(
                    EmailConfig.portal_user_id == rule.portal_user_id,
                    EmailConfig.is_active == True,
                    EmailConfig.is_default == True,
                )
            )
            cfg = cfg_result.scalar_one_or_none()

        if not cfg:
            logger.error(f"[AUTO-REPLY] Không tìm thấy email config cho rule {rule.id}")
            return

        # Resolve body HTML
        body_html = rule.body_html or ""
        if rule.template_id:
            tpl_result = await db.execute(
                select(Template).where(
                    Template.id == rule.template_id,
                    Template.is_active == True,
                )
            )
            tpl = tpl_result.scalar_one_or_none()
            if tpl and tpl.html_snapshot:
                body_html = tpl.html_snapshot

        if not body_html:
            logger.error(f"[AUTO-REPLY] Rule {rule.id} không có nội dung HTML")
            return

        # Build subject: custom hoặc tự động theo reply_type
        reply_type = rule.reply_type or "reply"
        original_subject = candidate.subject or ""
        if rule.reply_subject:
            subject = rule.reply_subject
        elif reply_type == "forward":
            subject = original_subject if original_subject.lower().startswith("fwd:") else f"Fwd: {original_subject}"
        else:
            subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

        # Tạo reply record
        reply = RecruitmentReply(
            portal_user_id=rule.portal_user_id,
            candidate_email_id=candidate.id,
            bulk_id=f"auto:{rule.id}",  # prefix "auto:" để phân biệt với bulk manual
            sent_by=rule.portal_user_id,
            email_config_id=cfg.id,
            template_id=rule.template_id,
            to_email=candidate.from_email,
            to_name=candidate.from_name or "",
            subject=subject,
            body_html=body_html,
            status="pending",
        )
        db.add(reply)
        await db.commit()
        await db.refresh(reply)

        # Gửi email
        received_at_str = candidate.received_at.isoformat() if candidate.received_at else ""
        try:
            await send_reply(
                cfg=cfg,
                from_name=rule.from_name or cfg.sender_name or "",
                to_email=candidate.from_email,
                to_name=candidate.from_name or "",
                subject=subject,
                body_html=body_html,
                reply_to_message_id=candidate.message_id,
                reply_mode=reply_type,
                original_body_html=candidate.body_html or "",
                original_body_text=candidate.body_text or "",
                original_from=candidate.from_name or "",
                original_from_email=candidate.from_email or "",
                original_subject=original_subject,
                original_received_at=received_at_str,
            )
            reply.status = "sent"
            reply.sent_at = datetime.now(timezone.utc)

            # Cập nhật status ứng viên thành "replied"
            cand = await db.get(CandidateEmail, candidate.id)
            if cand:
                cand.status = "replied"

            logger.info(f"[AUTO-REPLY] Sent → {candidate.from_email} (rule={rule.id}, candidate={candidate.id})")

        except Exception as exc:
            reply.status = "failed"
            reply.error_message = str(exc)
            logger.error(f"[AUTO-REPLY] Failed → {candidate.from_email}: {exc}")

        await db.commit()


async def trigger_auto_reply(
    portal_user_id: str,
    candidate: CandidateEmail,
    job_id: Optional[int],
) -> int:
    """
    Tìm tất cả active rules phù hợp với job_id của email ứng viên,
    schedule background task cho mỗi rule.
    Trả về số rule được trigger.
    """
    async with AsyncSessionLocal() as db:
        from sqlalchemy import or_
        result = await db.execute(
            select(RecruitmentAutoRule).where(
                RecruitmentAutoRule.portal_user_id == portal_user_id,
                RecruitmentAutoRule.trigger == "on_receive",
                RecruitmentAutoRule.is_active == True,
                or_(
                    RecruitmentAutoRule.job_id == job_id,
                    RecruitmentAutoRule.job_id == None,
                ),
            )
        )
        rules = result.scalars().all()

    for rule in rules:
        asyncio.create_task(_execute_rule(rule, candidate))

    return len(rules)
