from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from datetime import datetime, timezone
from typing import List, Optional
from app.db.database import get_db
from app.models.user_model import User
from app.schemas.user_schema import UserCreate, UserUpdate, UserResponse
from app.services.notification_service import create_notification, create_broadcast_notification

# role_id cố định từ seed data
ROLE_SUPER_ADMIN = "2000000001"
ROLE_ADMIN       = "2000000002"
ROLE_GUEST       = "2000000005"

router = APIRouter()


def _build_personal_tenant_id(email: Optional[str], portal_user_id: Optional[str] = None) -> str:
    """
    DB tenant_id is NOT NULL, so personal users must always have a fallback tenant.
    Use a single default guest tenant as requested.
    """
    return "tenant_guest"


def _normalize_joined_at(value):
    """
    Normalize joined_at to datetime for DB columns typed as timestamptz.
    Accepts ISO strings/date-only strings and returns datetime or None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    # Date-only string -> midnight UTC
    if len(raw) == 10:
        try:
            d = datetime.strptime(raw, "%Y-%m-%d")
            return d.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return value


async def _generate_next_e_code(db: AsyncSession) -> str:
    # e_code format: EM000001
    result = await db.execute(
        select(User.e_code)
        .where(User.e_code.is_not(None), User.e_code.like("EM%"))
        .order_by(User.e_code.desc())
        .limit(1)
    )
    last_code = result.scalar_one_or_none()
    next_num = 1
    if last_code and len(last_code) >= 3:
        try:
            next_num = int(last_code[2:]) + 1
        except Exception:
            next_num = 1
    return f"EM{next_num:06d}"


async def _notify_admins_in_tenant(db: AsyncSession, tenant_id: str, title: str, message: str, ntype: str, link: str):
    """Gửi notification cho admin + superAdmin trong cùng tenant."""
    result = await db.execute(
        select(User.portal_user_id).where(
            User.tenant_id == tenant_id,
            User.role.in_([ROLE_SUPER_ADMIN, ROLE_ADMIN]),
        )
    )
    admin_ids = [row[0] for row in result.all()]
    if admin_ids:
        await create_broadcast_notification(db, tenant_id, admin_ids, title, message, ntype, link)


async def _notify_all_superadmins(db: AsyncSession, title: str, message: str, ntype: str, link: str):
    """Gửi notification cho tất cả superAdmin trong toàn hệ thống."""
    result = await db.execute(
        select(User.portal_user_id, User.tenant_id).where(User.role == ROLE_SUPER_ADMIN)
    )
    rows = result.all()
    # Group theo tenant_id để gọi create_broadcast_notification
    from collections import defaultdict
    by_tenant: dict[str, list[str]] = defaultdict(list)
    for portal_id, tid in rows:
        if tid:
            by_tenant[tid].append(portal_id)
    for tid, ids in by_tenant.items():
        await create_broadcast_notification(db, tid, ids, title, message, ntype, link)


@router.get("/tenant-members", response_model=List[UserResponse])
async def list_tenant_members(
    tenant_id: str = Query(..., description="tenant_id lấy từ JWT của gateway"),
    db: AsyncSession = Depends(get_db),
):
    """Chỉ trả về users thuộc tenant_id được chỉ định — không expose toàn bộ DB."""
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
    )
    return result.scalars().all()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id"),
    db: AsyncSession = Depends(get_db),
):
    """List users. Requires tenant_id filter to avoid exposing full DB."""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id query parameter is required.")
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
    )
    return result.scalars().all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def upsert_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create or update a user. 
    If a user with the same email exists, we update their fields (including google_id/token).
    If not, we create a new user and generate a random 3-4 digit portal_user_id.
    """
    import random

    # 1. Search by email first (robust for Google/Enterprise login)
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    update_data = payload.model_dump(exclude_unset=True)
    # Accept legacy role names from old payloads and normalize to role_id.
    role_alias = {
        "superadmin": ROLE_SUPER_ADMIN,
        "admin": ROLE_ADMIN,
        "guest": ROLE_GUEST,
    }
    incoming_role = update_data.get("role")
    if isinstance(incoming_role, str):
        normalized = role_alias.get(incoming_role.strip().lower())
        if normalized:
            update_data["role"] = normalized
    update_data["last_login_at"] = datetime.now(timezone.utc)
    if "joined_at" in update_data:
        update_data["joined_at"] = _normalize_joined_at(update_data.get("joined_at"))
    if "is_tenant_admin" in update_data:
        update_data["admin_meeting_room"] = bool(update_data.pop("is_tenant_admin"))
    if update_data.get("department") and not update_data.get("dept_code"):
        update_data["dept_code"] = update_data.get("department")

    is_new_user = False
    if user:
        # Never overwrite role/portal_user_id on login.
        # role stores role_id (e.g. "2000000003") — only admin can change via PUT.
        # Only update tenant_id if user is still in personal space (no real tenant assigned yet).
        protected_fields = {"role", "portal_user_id"}
        if user.tenant_id and not user.tenant_id.startswith("personal_"):
            protected_fields.add("tenant_id")
        for key, value in update_data.items():
            if key not in protected_fields:
                setattr(user, key, value)
        if not user.e_code:
            user.e_code = await _generate_next_e_code(db)
        if not user.dept_code and user.department:
            user.dept_code = user.department
        if not user.tenant_id:
            user.tenant_id = _build_personal_tenant_id(user.email, user.portal_user_id)
    else:
        # 2. Create new user with random portal_user_id
        new_portal_id = str(random.randint(100, 9999))
        
        # Ensure uniqueness of portal_user_id
        is_unique = False
        while not is_unique:
            check_result = await db.execute(select(User).where(User.portal_user_id == new_portal_id))
            if not check_result.scalar_one_or_none():
                is_unique = True
            else:
                new_portal_id = str(random.randint(100, 9999))

        update_data["portal_user_id"] = new_portal_id
        if not update_data.get("tenant_id"):
            update_data["tenant_id"] = _build_personal_tenant_id(
                update_data.get("email"), new_portal_id
            )
        # Force default role for newly upserted users (e.g. first SSO login).
        # Existing users keep their current role in the update branch above.
        update_data["role"] = ROLE_GUEST
        update_data["e_code"] = update_data.get("e_code") or await _generate_next_e_code(db)
        if update_data.get("department") and not update_data.get("dept_code"):
            update_data["dept_code"] = update_data.get("department")
        # Final guardrail for DB NOT NULL tenant_id.
        update_data["tenant_id"] = update_data.get("tenant_id") or "tenant_guest"
        user = User(**update_data)
        db.add(user)
        is_new_user = True

    await db.commit()
    await db.refresh(user)

    # Notify admin/superAdmin khi có thành viên mới tham gia tenant
    if is_new_user and user.tenant_id and not user.tenant_id.startswith("personal_"):
        display = user.full_name or user.name or user.email
        await _notify_admins_in_tenant(
            db=db,
            tenant_id=user.tenant_id,
            title="Thành viên mới tham gia",
            message=f"{display} ({user.email}) vừa tham gia hệ thống.",
            ntype="info",
            link="/user",
        )

    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get a user by internal ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.get("/portal/{portal_user_id}", response_model=UserResponse)
async def get_user_by_portal_id(portal_user_id: str, db: AsyncSession = Depends(get_db)):
    """Get a user by their Portal system user ID."""
    result = await db.execute(select(User).where(User.portal_user_id == portal_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.get("/by-role/{role_id}", response_model=List[UserResponse])
async def list_users_by_role(role_id: str, db: AsyncSession = Depends(get_db)):
    """Trả về users có role = role_id (dùng cho admin panel)."""
    result = await db.execute(
        select(User).where(User.role == role_id).order_by(User.full_name)
    )
    return result.scalars().all()


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Partially update a user's profile (admin action)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if "joined_at" in update_data:
        update_data["joined_at"] = _normalize_joined_at(update_data.get("joined_at"))
    if "is_tenant_admin" in update_data:
        update_data["admin_meeting_room"] = bool(update_data.pop("is_tenant_admin"))
    if "department" in update_data and "dept_code" not in update_data:
        update_data["dept_code"] = update_data.get("department")
    old_role = user.role
    role_changed = "role" in update_data and update_data["role"] != old_role

    for key, value in update_data.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)

    display = user.full_name or user.name or user.email
    tenant_id = user.tenant_id

    if tenant_id and not tenant_id.startswith("personal_"):
        if role_changed:
            # Thông báo đổi role → notify admin/superAdmin trong tenant
            await _notify_admins_in_tenant(
                db=db,
                tenant_id=tenant_id,
                title="Quyền người dùng đã thay đổi",
                message=f"Tài khoản {display} ({user.email}) vừa được cập nhật quyền trong hệ thống.",
                ntype="warning",
                link="/user",
            )
            # SuperAdmin toàn hệ thống cũng được báo
            await _notify_all_superadmins(
                db=db,
                title="Quyền người dùng đã thay đổi",
                message=f"Tài khoản {display} ({user.email}) vừa được cập nhật quyền (tenant: {tenant_id}).",
                ntype="warning",
                link="/user",
            )
        else:
            # Cập nhật thông tin thường → chỉ notify admin/superAdmin trong tenant
            await _notify_admins_in_tenant(
                db=db,
                tenant_id=tenant_id,
                title="Thông tin người dùng được cập nhật",
                message=f"Tài khoản {display} ({user.email}) vừa được cập nhật thông tin.",
                ntype="info",
                link="/user",
            )

    return user
