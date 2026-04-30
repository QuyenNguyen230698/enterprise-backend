from contextlib import asynccontextmanager
import time
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from app.api.v1 import area_route, room_route, user_route, meeting_route, tenant_route, role_route, email_config_route, profile_route, template_route, email_list_route, campaign_route, notification_route, ticket_route, offboarding_route, asset_handover_route, job_handover_route, exit_interview_route
from app.db.database import engine
from app.db.base import Base
from sqlalchemy import text

# Import all models so metadata is populated before create_all
import app.models.area_model      # noqa
import app.models.room_model      # noqa
import app.models.user_model      # noqa
import app.models.meeting_model   # noqa
import app.models.tenant_model    # noqa
import app.models.role_model           # noqa
import app.models.email_config_model  # noqa
import app.models.template_model      # noqa
import app.models.email_list_model    # noqa
import app.models.campaign_model      # noqa
import app.models.notification_model  # noqa
import app.models.ticket_model        # noqa  (Ticket + TicketComment)
import app.models.offboarding_model   # noqa  (OffboardingProcess + OffboardingStep)
import app.models.user_signature_model  # noqa (UserSignature)
import app.models.document_approval_log_model  # noqa (DocumentApprovalLog)
import app.models.asset_handover_model          # noqa (AssetHandover + AssetHandoverStep)
import app.models.job_handover_model            # noqa (JobHandover + JobHandoverStep)
import app.models.exit_interview_model          # noqa (ExitInterview + ExitInterviewStep)

# ─── Logger setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("api.access")

# ANSI colour helpers
def _status_colour(status: int) -> str:
    if status < 300: return f"\033[32m{status}\033[0m"   # green
    if status < 400: return f"\033[33m{status}\033[0m"   # yellow
    if status < 500: return f"\033[91m{status}\033[0m"   # red
    return f"\033[35m{status}\033[0m"                     # magenta (5xx)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight schema migration for existing databases.
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS e_code VARCHAR"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS dept_code VARCHAR"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_e_code_unique ON users (e_code) WHERE e_code IS NOT NULL"))
        await conn.execute(text("UPDATE users SET dept_code = department WHERE dept_code IS NULL AND department IS NOT NULL"))
        await conn.execute(text("""
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
                FROM users
                WHERE e_code IS NULL
            )
            UPDATE users u
            SET e_code = 'EM' || LPAD(ordered.rn::text, 6, '0')
            FROM ordered
            WHERE u.id = ordered.id
        """))
        await conn.execute(text("ALTER TABLE offboarding_processes ADD COLUMN IF NOT EXISTS dept_code VARCHAR(100)"))
        await conn.execute(text("UPDATE offboarding_processes SET dept_code = department WHERE dept_code IS NULL AND department IS NOT NULL"))
        await conn.execute(text("ALTER TABLE asset_handovers ADD COLUMN IF NOT EXISTS created_by VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE document_approval_logs ADD COLUMN IF NOT EXISTS actor_title VARCHAR"))
        await conn.execute(text("""
            UPDATE document_approval_logs l
            SET
                actor_name = COALESCE(NULLIF(u.name, ''), l.actor_name),
                actor_title = COALESCE(NULLIF(u.title, ''), l.actor_title)
            FROM users u
            WHERE
                u.portal_user_id IS NOT NULL
                AND CAST(l.actor_id AS VARCHAR) = CAST(u.portal_user_id AS VARCHAR)
                AND (
                    l.actor_name IS NULL
                    OR l.actor_name = ''
                    OR LOWER(l.actor_name) = 'unknown'
                    OR l.actor_title IS NULL
                    OR l.actor_title = ''
                )
        """))
        await conn.execute(text("""
            UPDATE offboarding_steps s
            SET actor_name = COALESCE(NULLIF(u.name, ''), s.actor_name)
            FROM users u
            WHERE
                u.portal_user_id IS NOT NULL
                AND CAST(s.actor_id AS VARCHAR) = CAST(u.portal_user_id AS VARCHAR)
                AND (
                    s.actor_name IS NULL
                    OR s.actor_name = ''
                    OR LOWER(s.actor_name) = 'unknown'
                )
        """))
    yield



app = FastAPI(
    title="Enterprise Meeting — Python Service",
    description="Core business logic: Rooms, Areas, Users, Meetings & Zoom/Teams integration.",
    version="2.0.0",
    docs_url="/docs",
    lifespan=lifespan
)

Path("uploads").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# ─── Register Routers ─────────────────────────────────────────────
app.include_router(area_route.router,         prefix="/api/v1/areas",    tags=["Areas"])
app.include_router(room_route.router,         prefix="/api/v1/rooms",    tags=["Rooms"])
app.include_router(user_route.router,         prefix="/api/v1/users",    tags=["Users"])
app.include_router(meeting_route.router,      prefix="/api/v1/meetings", tags=["Meetings"])
app.include_router(tenant_route.router,       prefix="/api/v1/tenants",  tags=["Tenants"])
app.include_router(role_route.router,         prefix="/api/v1/roles",    tags=["Roles & Permissions"])
app.include_router(email_config_route.router, prefix="/api/v1",          tags=["Email Config"])
app.include_router(profile_route.router,      prefix="/api/v1",          tags=["Profile"])
app.include_router(template_route.router,     prefix="/api/v1",          tags=["Templates"])
app.include_router(email_list_route.router,   prefix="/api/v1",          tags=["Email Lists"])
app.include_router(campaign_route.router,      prefix="/api/v1",          tags=["Campaigns"])
app.include_router(notification_route.router,  prefix="/api/v1",          tags=["Notifications"])
app.include_router(ticket_route.router,        prefix="/api/v1",          tags=["Tickets Internal"])
app.include_router(offboarding_route.router,      prefix="/api/v1/internal/offboarding",  tags=["Offboarding"])
app.include_router(asset_handover_route.router,   prefix="/api/v1/asset-handover",        tags=["Asset Handover"])
app.include_router(job_handover_route.router,     prefix="/api/v1/job-handover",          tags=["Job Handover"])
app.include_router(exit_interview_route.router,   prefix="/api/v1/exit-interview",        tags=["Exit Interview"])


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Enterprise Meeting Python Service v2.0 is running.", "docs": "/docs"}