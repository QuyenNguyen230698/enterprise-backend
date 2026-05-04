import random
import string
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.database import get_db
from app.models.role_model import Permission, Role
from app.models.user_model import User
from app.services.notification_service import create_broadcast_notification

ROLE_SUPER_ADMIN = "2000000001"


async def _notify_all_superadmins(db: AsyncSession, title: str, message: str, ntype: str = "system", link: str = "/user"):
    """Gửi notification cho tất cả superAdmin trong toàn hệ thống."""
    result = await db.execute(
        select(User.portal_user_id, User.tenant_id).where(User.role == ROLE_SUPER_ADMIN)
    )
    rows = result.all()
    by_tenant: dict[str, list[str]] = defaultdict(list)
    for portal_id, tid in rows:
        if tid:
            by_tenant[tid].append(portal_id)
    for tid, ids in by_tenant.items():
        await create_broadcast_notification(db, tid, ids, title, message, ntype, link)
from app.schemas.role_schema import (
    PermissionCreate, PermissionUpdate, PermissionResponse,
    RoleCreate, RoleUpdate, RoleResponse, RoleDetailResponse,
)

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────────────

def _generate_id(length: int = 10) -> str:
    """Sinh ID số ngẫu nhiên không trùng (dạng string)."""
    return "".join(random.choices(string.digits, k=length))


async def _unique_id(db: AsyncSession, model, id_field: str, length: int = 10) -> str:
    while True:
        new_id = _generate_id(length)
        result = await db.execute(
            select(model).where(getattr(model, id_field) == new_id)
        )
        if not result.scalar_one_or_none():
            return new_id


async def _next_role_id(db: AsyncSession) -> str:
    """
    Sinh role_id tăng dần theo format 200000000n.
    Ví dụ: 2000000001 -> 2000000002, đảm bảo không trùng.
    """
    base = 2_000_000_000
    result = await db.execute(select(Role.role_id))
    role_ids = [row[0] for row in result.all() if row and row[0]]
    numeric_ids = []
    for rid in role_ids:
        if isinstance(rid, str) and rid.isdigit():
            num = int(rid)
            if num >= base:
                numeric_ids.append(num)
    existing = set(numeric_ids)
    candidate = base + 1
    while candidate in existing:
        candidate += 1
    return str(candidate)


# ─── Permissions ─────────────────────────────────────────────────

@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Permission).order_by(Permission.name))
    return result.scalars().all()


@router.post("/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(payload: PermissionCreate, db: AsyncSession = Depends(get_db)):
    # Check duplicate name
    existing = await db.execute(select(Permission).where(Permission.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Permission '{payload.name}' already exists.")

    pid = payload.permission_id or await _unique_id(db, Permission, "permission_id")
    perm = Permission(
        permission_id=pid,
        name=payload.name,
        description=payload.description,
        app_path=payload.app_path,
        app_icon=payload.app_icon,
        app_group=payload.app_group,
        parent_name=payload.parent_name,
    )
    db.add(perm)
    await db.commit()
    await db.refresh(perm)

    await _notify_all_superadmins(
        db=db,
        title="Quyền mới được tạo",
        message=f"Permission \"{perm.name}\" ({perm.description or ''}) vừa được thêm vào hệ thống.",
        ntype="system",
        link="/user",
    )
    return perm


@router.put("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission(permission_id: str, payload: PermissionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Permission).where(Permission.permission_id == permission_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found.")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(perm, key, value)
    await db.commit()
    await db.refresh(perm)

    await _notify_all_superadmins(
        db=db,
        title="Quyền đã được cập nhật",
        message=f"Permission \"{perm.name}\" vừa được chỉnh sửa.",
        ntype="warning",
        link="/user",
    )
    return perm


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(permission_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Permission).where(Permission.permission_id == permission_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found.")

    perm_name = perm.name
    await db.delete(perm)
    await db.commit()

    await _notify_all_superadmins(
        db=db,
        title="Quyền đã bị xóa",
        message=f"Permission \"{perm_name}\" đã bị xóa khỏi hệ thống.",
        ntype="error",
        link="/user",
    )


# ─── Roles ───────────────────────────────────────────────────────

@router.get("/", response_model=List[RoleResponse])
async def list_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).order_by(Role.name))
    return result.scalars().all()


@router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role(role_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    # Fetch full permission objects
    perm_result = await db.execute(
        select(Permission).where(Permission.permission_id.in_(role.permissions or []))
    )
    perms = perm_result.scalars().all()

    return RoleDetailResponse(
        role_id=role.role_id,
        name=role.name,
        description=role.description,
        permissions=role.permissions or [],
        created_at=role.created_at,
        updated_at=role.updated_at,
        permission_objects=perms,
    )


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(payload: RoleCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Role).where(Role.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Role '{payload.name}' already exists.")

    if payload.role_id:
        existing_id = await db.execute(select(Role).where(Role.role_id == payload.role_id))
        if existing_id.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Role ID '{payload.role_id}' already exists.")
        rid = payload.role_id
    else:
        rid = await _next_role_id(db)
    role = Role(
        role_id=rid,
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    await _notify_all_superadmins(
        db=db,
        title="Role mới được tạo",
        message=f"Role \"{role.name}\" ({role.description or ''}) vừa được thêm vào hệ thống.",
        ntype="system",
        link="/user",
    )
    return role


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(role_id: str, payload: RoleUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(role, key, value)
    await db.commit()
    await db.refresh(role)

    await _notify_all_superadmins(
        db=db,
        title="Role đã được cập nhật",
        message=f"Role \"{role.name}\" vừa được chỉnh sửa (quyền hạn hoặc mô tả thay đổi).",
        ntype="warning",
        link="/user",
    )
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role).where(Role.role_id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    role_name = role.name
    await db.delete(role)
    await db.commit()

    await _notify_all_superadmins(
        db=db,
        title="Role đã bị xóa",
        message=f"Role \"{role_name}\" đã bị xóa khỏi hệ thống.",
        ntype="error",
        link="/user",
    )


# ─── Seed endpoint (idempotent) ───────────────────────────────────

DEFAULT_PERMISSIONS = [
    {
        "permission_id": "1000000001",
        "name": "bookings",
        "description": "Quản lý đặt phòng họp",
        "app_path": "/bookings",
        "app_icon": "bi bi-calendar-check",
        "app_group": "admin",
        "parent_name": None,
    },
    {
        "permission_id": "1000000002",
        "name": "editor",
        "description": "Thiết kế email",
        "app_path": "/editor",
        "app_icon": "bi bi-pencil-square",
        "app_group": "email",
        "parent_name": None,
    },
    {
        "permission_id": "1000000003",
        "name": "email-lists",
        "description": "Danh sách khách hàng",
        "app_path": "/email-lists",
        "app_icon": "bi bi-person-lines-fill",
        "app_group": "email",
        "parent_name": None,
    },
    {
        "permission_id": "1000000004",
        "name": "templates",
        "description": "Mẫu email",
        "app_path": "/templates",
        "app_icon": "bi bi-layout-text-window-reverse",
        "app_group": "email",
        "parent_name": None,
    },
    {
        "permission_id": "1000000005",
        "name": "notifications",
        "description": "Thông báo hệ thống",
        "app_path": "/notifications",
        "app_icon": "bi bi-bell",
        "app_group": "system",
        "parent_name": None,
    },
    {
        "permission_id": "1000000006",
        "name": "settings",
        "description": "Cài đặt hệ thống",
        "app_path": "/settings",
        "app_icon": "bi bi-gear",
        "app_group": "settings",
        "parent_name": None,
    },
    {
        "permission_id": "1000000007",
        "name": "user",
        "description": "Quản lý người dùng",
        "app_path": "/user",
        "app_icon": "bi bi-people",
        "app_group": "system",
        "parent_name": None,
    },
    {
        "permission_id": "1000000008",
        "name": "dashboard",
        "description": "Dashboard tổng quan",
        "app_path": "/dashboard",
        "app_icon": "bi bi-speedometer2",
        "app_group": "admin",
        "parent_name": None,
    },
    {
        "permission_id": "1000000009",
        "name": "email-config",
        "description": "Cấu hình email server",
        "app_path": "/settings/email-config",
        "app_icon": "bi bi-gear-wide-connected",
        "app_group": "settings",
        "parent_name": "settings",
    },
    {
        "permission_id": "1000000010",
        "name": "sign-hub",
        "description": "Trung tâm ký duyệt văn bản HRM",
        "app_path": "/sign-hub",
        "app_icon": "bi bi-pen-fill",
        "app_group": "hrm",
        "parent_name": "offboarding",
    },
]

DEFAULT_ROLES = [
    {
        "role_id": "2000000001",
        "name": "superAdmin",
        "description": "Quản trị toàn hệ thống",
        "permissions": [
            "1000000001","1000000002","1000000003","1000000004",
            "1000000005","1000000006","1000000007","1000000008","1000000009","1000000010",
        ],
    },
    {
        "role_id": "2000000002",
        "name": "admin",
        "description": "Quản trị tenant",
        "permissions": [
            "1000000001","1000000002","1000000003","1000000004",
            "1000000005","1000000007","1000000008","1000000010",
        ],
    },
    {
        "role_id": "2000000003",
        "name": "member",
        "description": "Thành viên",
        "permissions": ["1000000001","1000000002","1000000003","1000000008"],
    },
]


@router.post("/seed", status_code=status.HTTP_200_OK)
async def seed_defaults(db: AsyncSession = Depends(get_db)):
    """Upsert: insert nếu chưa tồn tại, patch metadata nếu đã có."""
    created = {"permissions": [], "roles": [], "updated": {"permissions": [], "roles": []}}

    for p in DEFAULT_PERMISSIONS:
        result = await db.execute(
            select(Permission).where(Permission.permission_id == p["permission_id"])
        )
        existing = result.scalar_one_or_none()
        if not existing:
            db.add(Permission(**p))
            created["permissions"].append(p["name"])
        else:
            # Patch metadata fields mà không ghi đè name/description nếu đã custom
            changed = False
            for field in ("app_path", "app_icon", "app_group", "parent_name"):
                if getattr(existing, field) != p.get(field):
                    setattr(existing, field, p.get(field))
                    changed = True
            if changed:
                created["updated"]["permissions"].append(p["name"])

    for r in DEFAULT_ROLES:
        result = await db.execute(
            select(Role).where(Role.role_id == r["role_id"])
        )
        existing = result.scalar_one_or_none()
        if not existing:
            db.add(Role(**r))
            created["roles"].append(r["name"])
        else:
            # Sync permissions array để đảm bảo email-config (1000000009) được thêm vào superAdmin
            if existing.permissions != r["permissions"]:
                existing.permissions = r["permissions"]
                created["updated"]["roles"].append(r["name"])

    await db.commit()
    return {"message": "Seed completed.", "created": created}
