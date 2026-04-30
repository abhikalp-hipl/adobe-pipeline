import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy import select

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.email_group import router as email_group_router
from app.api.routes.files import router as files_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.runs import router as runs_router
from app.api.routes.scheduler import router as scheduler_router
from app.api.routes.settings import router as settings_router
from app.db.database import Base, engine
from app.db.database import SessionLocal
from app.db.models import NotificationSettings
from app.services.pipeline_ws import PipelineWebSocketManager
from app.services.scheduler import Scheduler

app = FastAPI(title="Document Processing Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
    ws_manager = PipelineWebSocketManager()
    app.state.pipeline_ws_manager = ws_manager
    scheduler_interval = await _get_persisted_scheduler_interval_seconds()
    app.state.scheduler = Scheduler(
        interval=scheduler_interval,
        status_listener=lambda payload: asyncio.create_task(ws_manager.broadcast({"type": "status", **payload}))
    )
    app.state.scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.stop()


app.include_router(documents_router)
app.include_router(scheduler_router)
app.include_router(pipeline_router)
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(email_group_router)
app.include_router(runs_router)
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
