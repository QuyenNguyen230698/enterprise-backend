"""
hrm_document_template_route.py — Internal API (node-gateway ↔ python-service)
Prefix: /api/v1/internal/hrm/document-templates  (mounted in main.py)
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.hrm_document_template_model import HrmDocumentTemplate

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(tpl: HrmDocumentTemplate) -> Dict[str, Any]:
    return {
        "id": tpl.id,
        "tenantId": tpl.tenant_id,
        "name": tpl.name,
        "code": tpl.code,
        "docType": tpl.doc_type,
        "titleVn": tpl.title_vn,
        "titleEn": tpl.title_en,
        "status": tpl.status,
        "contentBlocks": tpl.content_blocks or [],
        "signers": tpl.signers or [],
        "workflowSteps": tpl.workflow_steps or [],
        "createdBy": tpl.created_by,
        "createdAt": tpl.created_at.isoformat() if tpl.created_at else None,
        "updatedAt": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TemplateBody(BaseModel):
    name: str
    code: Optional[str] = "QF-HRM-XX"
    docType: Optional[str] = "CUSTOM"
    titleVn: Optional[str] = None
    titleEn: Optional[str] = None
    contentBlocks: Optional[List[Any]] = []
    signers: Optional[List[Any]] = []
    workflowSteps: Optional[List[Any]] = []


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_templates(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(HrmDocumentTemplate).order_by(HrmDocumentTemplate.created_at.desc())
    if tenant_id:
        q = q.where(HrmDocumentTemplate.tenant_id == tenant_id)
    if status:
        q = q.where(HrmDocumentTemplate.status == status)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [_serialize(r) for r in rows]


@router.post("", status_code=201)
async def create_template(
    body: TemplateBody,
    tenant_id: Optional[str] = Query(None),
    created_by: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    tpl = HrmDocumentTemplate(
        tenant_id=tenant_id,
        name=body.name,
        code=body.code or "QF-HRM-XX",
        doc_type=body.docType or "CUSTOM",
        title_vn=body.titleVn,
        title_en=body.titleEn,
        status="DRAFT",
        content_blocks=body.contentBlocks or [],
        signers=body.signers or [],
        workflow_steps=body.workflowSteps or [],
        created_by=created_by,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.get("/{template_id}")
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    tpl = await db.get(HrmDocumentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize(tpl)


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    body: TemplateBody,
    db: AsyncSession = Depends(get_db),
):
    tpl = await db.get(HrmDocumentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tpl.name = body.name
    tpl.code = body.code or tpl.code
    tpl.doc_type = body.docType or tpl.doc_type
    tpl.title_vn = body.titleVn
    tpl.title_en = body.titleEn
    tpl.content_blocks = body.contentBlocks or []
    tpl.signers = body.signers or []
    tpl.workflow_steps = body.workflowSteps or []
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.post("/{template_id}/publish")
async def publish_template(template_id: int, db: AsyncSession = Depends(get_db)):
    tpl = await db.get(HrmDocumentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tpl.status = "PUBLISHED"
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    tpl = await db.get(HrmDocumentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(tpl)
    await db.commit()
