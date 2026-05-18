import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select, update

from app.api.routes.accessibility import router as accessibility_router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.department import router as department_router
from app.api.routes.dept_auth import router as dept_auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.email_group import router as email_group_router
from app.api.routes.files import router as files_router
from app.api.routes.runs import router as runs_router
from app.api.routes.scheduler import router as scheduler_router
from app.api.routes.settings import router as settings_router
from app.db.database import Base, engine
from app.db.database import SessionLocal
from app.db.models import (
    Department,
    DepartmentConfig,
    DepartmentCredentials,
    DepartmentEmailMember,
    DepartmentOAuthToken,
    Document,
    EmailGroup,
    NotificationSettings,
    PipelineRun,
    SuperAdmin,
    UserToken,
)
from app.core.config import settings as app_settings
from app.services.auth.app_auth import hash_password
from app.services.scheduler import Scheduler

app = FastAPI(title="Document Processing Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger(__name__).info("Application startup: initializing database metadata")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _ensure_user_token_columns()
    await _ensure_notification_settings_columns()
    await _ensure_pipeline_run_file_columns()
    await _ensure_multidepartment_columns()
    await _ensure_document_filename_dept_unique()
    await _bootstrap_multidepartment_data()
    scheduler_interval = await _get_persisted_scheduler_interval_seconds()
    app.state.scheduler = Scheduler(interval=scheduler_interval)
    app.state.scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.stop()


app.include_router(documents_router)
app.include_router(scheduler_router)
app.include_router(dept_auth_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(department_router)
app.include_router(files_router)
app.include_router(email_group_router)
app.include_router(runs_router)
app.include_router(accessibility_router)
app.include_router(settings_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def _ensure_user_token_columns() -> None:
    # Lightweight schema upgrade for existing local SQLite databases.
    async with engine.begin() as connection:
        rows = (await connection.execute(text("PRAGMA table_info(user_tokens)"))).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "user_email" not in existing_columns:
            await connection.execute(text("ALTER TABLE user_tokens ADD COLUMN user_email VARCHAR(320)"))
            await connection.execute(text("UPDATE user_tokens SET user_email = 'unknown@example.com' WHERE user_email IS NULL"))
        if "tenant_id" not in existing_columns:
            await connection.execute(text("ALTER TABLE user_tokens ADD COLUMN tenant_id VARCHAR(128)"))
            await connection.execute(text("UPDATE user_tokens SET tenant_id = 'unknown-tenant' WHERE tenant_id IS NULL"))


async def _ensure_pipeline_run_file_columns() -> None:
    async with engine.begin() as connection:
        rows = (await connection.execute(text("PRAGMA table_info(pipeline_run_files)"))).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "output_stem" not in existing_columns:
            await connection.execute(text("ALTER TABLE pipeline_run_files ADD COLUMN output_stem VARCHAR(512)"))
        if "accessibility_passed" not in existing_columns:
            await connection.execute(
                text("ALTER TABLE pipeline_run_files ADD COLUMN accessibility_passed INTEGER NOT NULL DEFAULT 0")
            )
        if "accessibility_failed" not in existing_columns:
            await connection.execute(
                text("ALTER TABLE pipeline_run_files ADD COLUMN accessibility_failed INTEGER NOT NULL DEFAULT 0")
            )
        if "accessibility_manual" not in existing_columns:
            await connection.execute(
                text("ALTER TABLE pipeline_run_files ADD COLUMN accessibility_manual INTEGER NOT NULL DEFAULT 0")
            )


async def _ensure_notification_settings_columns() -> None:
    # Lightweight schema upgrade for existing local SQLite databases.
    async with engine.begin() as connection:
        rows = (await connection.execute(text("PRAGMA table_info(notification_settings)"))).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "scheduler_interval_seconds" not in existing_columns:
            await connection.execute(
                text(
                    "ALTER TABLE notification_settings "
                    "ADD COLUMN scheduler_interval_seconds INTEGER NOT NULL DEFAULT 300"
                )
            )
            await connection.execute(
                text(
                    "UPDATE notification_settings "
                    "SET scheduler_interval_seconds = 300 "
                    "WHERE scheduler_interval_seconds IS NULL"
                )
            )


async def _get_persisted_scheduler_interval_seconds() -> int | None:
    try:
        async with SessionLocal() as db:
            settings_row = (await db.execute(select(NotificationSettings).order_by(NotificationSettings.created_at.asc()))).scalars().first()
            if not settings_row:
                return None
            interval = int(getattr(settings_row, "scheduler_interval_seconds", 0) or 0)
            if interval < 60:
                return None
            return interval
    except Exception:
        logging.getLogger(__name__).exception("Failed to load persisted scheduler interval")
        return None


async def _ensure_multidepartment_columns() -> None:
    async with engine.begin() as connection:
        for table, column, ddl in (
            ("documents", "department_id", "ALTER TABLE documents ADD COLUMN department_id VARCHAR(36)"),
            ("pipeline_runs", "department_id", "ALTER TABLE pipeline_runs ADD COLUMN department_id VARCHAR(36)"),
            ("notification_settings", "department_id", "ALTER TABLE notification_settings ADD COLUMN department_id VARCHAR(36)"),
            ("departments", "admin_email", "ALTER TABLE departments ADD COLUMN admin_email VARCHAR(320)"),
        ):
            rows = (await connection.execute(text(f"PRAGMA table_info({table})"))).fetchall()
            if not rows:
                continue
            existing = {row[1] for row in rows}
            if column not in existing:
                await connection.execute(text(ddl))


async def _ensure_document_filename_dept_unique() -> None:
    """Replace global unique(filename) with composite unique(filename, department_id)."""
    async with engine.begin() as connection:
        rows = (await connection.execute(text("PRAGMA table_info(documents)"))).fetchall()
        if not rows:
            return
        indexes = (await connection.execute(text("PRAGMA index_list(documents)"))).fetchall()
        index_names = {row[1] for row in indexes}
        if "uq_document_filename_dept" in index_names:
            return
        await connection.execute(
            text(
                """
                CREATE TABLE documents_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    department_id VARCHAR(36),
                    filename VARCHAR(512) NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(department_id) REFERENCES departments (id),
                    CONSTRAINT uq_document_filename_dept UNIQUE (filename, department_id)
                )
                """
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO documents_new (id, department_id, filename, status, created_at, updated_at)
                SELECT id, department_id, filename, status, created_at, updated_at FROM documents
                """
            )
        )
        await connection.execute(text("DROP TABLE documents"))
        await connection.execute(text("ALTER TABLE documents_new RENAME TO documents"))
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_documents_department_id ON documents (department_id)")
        )


async def _bootstrap_multidepartment_data() -> None:
    import uuid

    log = logging.getLogger(__name__)
    async with SessionLocal() as db:
        try:
            super_row = (await db.execute(select(SuperAdmin))).scalars().first()
            if not super_row:
                uname = (app_settings.SUPER_ADMIN_USERNAME or "admin").strip()
                pwd = app_settings.SUPER_ADMIN_PASSWORD or "changeme"
                db.add(
                    SuperAdmin(
                        id=str(uuid.uuid4()),
                        username=uname,
                        password_hash=hash_password(pwd),
                    )
                )
                await db.commit()
                log.info("Created initial super admin user: username=%s", uname)

            dept = (await db.execute(select(Department).order_by(Department.created_at.asc()))).scalars().first()
            if not dept:
                dept = Department(id=str(uuid.uuid4()), name="Default")
                db.add(dept)
                await db.flush()
                db.add(
                    DepartmentConfig(
                        id=str(uuid.uuid4()),
                        department_id=dept.id,
                    )
                )
                db.add(
                    DepartmentCredentials(
                        id=str(uuid.uuid4()),
                        department_id=dept.id,
                        username="default_dept",
                        password_hash=hash_password("changeme"),
                    )
                )
                db.add(
                    NotificationSettings(
                        id=str(uuid.uuid4()),
                        department_id=dept.id,
                        eod_time="18:00",
                        enabled=False,
                        scheduler_interval_seconds=300,
                    )
                )
                await db.commit()
                log.info(
                    "Created default department: id=%s — shared login username=default_dept password=changeme (change immediately).",
                    dept.id,
                )

            dept = (await db.execute(select(Department).order_by(Department.created_at.asc()))).scalars().first()
            if not dept:
                return

            await db.execute(update(Document).where(Document.department_id.is_(None)).values(department_id=dept.id))
            await db.execute(update(PipelineRun).where(PipelineRun.department_id.is_(None)).values(department_id=dept.id))
            await db.execute(
                update(NotificationSettings).where(NotificationSettings.department_id.is_(None)).values(department_id=dept.id)
            )

            for eg in (await db.execute(select(EmailGroup))).scalars().all():
                exists = (
                    await db.execute(
                        select(DepartmentEmailMember).where(
                            DepartmentEmailMember.department_id == dept.id,
                            DepartmentEmailMember.email == eg.email,
                        )
                    )
                ).scalars().first()
                if not exists:
                    db.add(DepartmentEmailMember(id=str(uuid.uuid4()), department_id=dept.id, email=eg.email))

            ut = (await db.execute(select(UserToken).order_by(UserToken.updated_at.desc()))).scalars().first()
            dot = (
                (await db.execute(select(DepartmentOAuthToken).where(DepartmentOAuthToken.department_id == dept.id)))
                .scalars()
                .first()
            )
            if ut and not dot:
                db.add(
                    DepartmentOAuthToken(
                        id=str(uuid.uuid4()),
                        department_id=dept.id,
                        provider=ut.provider,
                        connected_email=ut.user_email,
                        tenant_id=ut.tenant_id,
                        access_token=ut.access_token,
                        refresh_token=ut.refresh_token,
                        expires_at=ut.expires_at,
                    )
                )

            await db.commit()
        except Exception:
            await db.rollback()
            log.exception("Multi-department bootstrap failed")
