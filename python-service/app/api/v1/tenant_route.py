from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List

from app.db.database import get_db
from app.models.tenant_model import Tenant, TenantAdmin
from app.models.user_model import User
from app.models.meeting_model import Meeting
from app.schemas.tenant_schema import (
    TenantCreate, TenantUpdate, TenantResponse, TenantDetailResponse,
    TenantAdminCreate, TenantAdminUpdate, TenantAdminResponse,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════
# TENANT CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/by-domain", response_model=TenantResponse)
async def get_tenant_by_domain(
    domain: str,
    db: AsyncSession = Depends(get_db),
):
    """Lookup tenant theo email domain — dùng khi login để gán tenant_id đúng."""
    result = await db.execute(select(Tenant).where(Tenant.domain == domain, Tenant.is_active == True))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"No active tenant found for domain '{domain}'.")
    return tenant


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).order_by(Tenant.name))
    return result.scalars().all()


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Tenant).where(Tenant.tenant_id == payload.tenant_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Tenant '{payload.tenant_id}' already exists.")
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    admins_result = await db.execute(
        select(TenantAdmin).where(TenantAdmin.tenant_id == tenant_id)
    )
    admins = admins_result.scalars().all()

    response = TenantDetailResponse.model_validate(tenant)
    response.admins = [TenantAdminResponse.model_validate(a) for a in admins]
    return response


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: str, payload: TenantUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, key, value)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    await db.delete(tenant)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# TENANT ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

@router.get("/{tenant_id}/admins", response_model=List[TenantAdminResponse])
async def list_tenant_admins(tenant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenantAdmin).where(TenantAdmin.tenant_id == tenant_id)
    )
    return result.scalars().all()


@router.post("/{tenant_id}/admins", response_model=TenantAdminResponse, status_code=status.HTTP_201_CREATED)
async def add_tenant_admin(tenant_id: str, payload: TenantAdminCreate, db: AsyncSession = Depends(get_db)):
    # Verify tenant exists
    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found.")

    # Check duplicate
    existing = await db.execute(
        select(TenantAdmin).where(
            TenantAdmin.tenant_id == tenant_id,
            TenantAdmin.portal_user_id == payload.portal_user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already an admin of this tenant.")

    admin = TenantAdmin(tenant_id=tenant_id, **payload.model_dump(exclude={"tenant_id"}))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.put("/{tenant_id}/admins/{portal_user_id}", response_model=TenantAdminResponse)
async def update_tenant_admin(
    tenant_id: str, portal_user_id: str, payload: TenantAdminUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TenantAdmin).where(
            TenantAdmin.tenant_id == tenant_id,
            TenantAdmin.portal_user_id == portal_user_id,
        )
    )  # type: ignore
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin record not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(admin, key, value)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.delete("/{tenant_id}/admins/{portal_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tenant_admin(tenant_id: str, portal_user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenantAdmin).where(
            TenantAdmin.tenant_id == tenant_id,
            TenantAdmin.portal_user_id == portal_user_id,
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin record not found.")
    await db.delete(admin)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# PORTAL SUPER ADMIN — xem tất cả tenants mình quản lý
# ═══════════════════════════════════════════════════════════════════

@router.get("/by-user/{portal_user_id}/tenants", response_model=List[TenantAdminResponse])
async def get_tenants_by_user(portal_user_id: str, db: AsyncSession = Depends(get_db)):
    """Trả về danh sách tenant mà portal_user_id này có quyền admin."""
    result = await db.execute(
        select(TenantAdmin).where(
            TenantAdmin.portal_user_id == portal_user_id,
            TenantAdmin.is_active == True,
        )
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════════
# ASSIGN USER VÀO TENANT — clear personal meetings
# ═══════════════════════════════════════════════════════════════════

@router.post("/{tenant_id}/assign-user/{portal_user_id}", status_code=status.HTTP_200_OK)
async def assign_user_to_tenant(tenant_id: str, portal_user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Gán user vào một tenant thực:
    1. Kiểm tra tenant tồn tại
    2. Xóa toàn bộ meetings có tenant_id = "personal_{portal_user_id}"
    3. Cập nhật users.tenant_id = tenant_id
    """
    # 1. Verify tenant exists
    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found.")

    # 2. Verify user exists
    user_result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 3. Clear personal meetings nếu user chưa thuộc tenant thực nào
    personal_tenant_id = f"personal_{portal_user_id}"
    deleted = await db.execute(
        delete(Meeting).where(Meeting.tenant_id == personal_tenant_id)
    )
    deleted_count = deleted.rowcount

    # 4. Update user tenant_id
    user.tenant_id = tenant_id
    await db.commit()

    return {
        "status": "success",
        "portal_user_id": portal_user_id,
        "assigned_tenant_id": tenant_id,
        "personal_meetings_deleted": deleted_count,
    }
