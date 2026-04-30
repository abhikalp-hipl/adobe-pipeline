import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

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
    Base.metadata.create_all(bind=engine)
    _ensure_user_token_columns()
    _ensure_notification_settings_columns()
    _ensure_pipeline_run_file_columns()
    ws_manager = PipelineWebSocketManager()
    ws_manager.set_event_loop(asyncio.get_running_loop())
    app.state.pipeline_ws_manager = ws_manager
    scheduler_interval = _get_persisted_scheduler_interval_seconds()
    app.state.scheduler = Scheduler(
        interval=scheduler_interval,
        status_listener=lambda payload: ws_manager.broadcast_from_thread({"type": "status", **payload})
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


def _ensure_user_token_columns() -> None:
    # Lightweight schema upgrade for existing local SQLite databases.
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(user_tokens)")).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "user_email" not in existing_columns:
            connection.execute(text("ALTER TABLE user_tokens ADD COLUMN user_email VARCHAR(320)"))
            connection.execute(text("UPDATE user_tokens SET user_email = 'unknown@example.com' WHERE user_email IS NULL"))
        if "tenant_id" not in existing_columns:
            connection.execute(text("ALTER TABLE user_tokens ADD COLUMN tenant_id VARCHAR(128)"))
            connection.execute(text("UPDATE user_tokens SET tenant_id = 'unknown-tenant' WHERE tenant_id IS NULL"))


def _ensure_pipeline_run_file_columns() -> None:
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(pipeline_run_files)")).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "output_stem" not in existing_columns:
            connection.execute(text("ALTER TABLE pipeline_run_files ADD COLUMN output_stem VARCHAR(512)"))


def _ensure_notification_settings_columns() -> None:
    # Lightweight schema upgrade for existing local SQLite databases.
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(notification_settings)")).fetchall()
        if not rows:
            return
        existing_columns = {row[1] for row in rows}
        if "scheduler_interval_seconds" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE notification_settings "
                    "ADD COLUMN scheduler_interval_seconds INTEGER NOT NULL DEFAULT 300"
                )
            )
            connection.execute(
                text(
                    "UPDATE notification_settings "
                    "SET scheduler_interval_seconds = 300 "
                    "WHERE scheduler_interval_seconds IS NULL"
                )
            )


def _get_persisted_scheduler_interval_seconds() -> int | None:
    db = SessionLocal()
    try:
        settings_row = db.query(NotificationSettings).order_by(NotificationSettings.created_at.asc()).first()
        if not settings_row:
            return None
        interval = int(getattr(settings_row, "scheduler_interval_seconds", 0) or 0)
        if interval < 60:
            return None
        return interval
    except Exception:
        logging.getLogger(__name__).exception("Failed to load persisted scheduler interval")
        return None
    finally:
        db.close()
