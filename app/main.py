import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.files import router as files_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.scheduler import router as scheduler_router
from app.db.database import Base, engine
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
def on_startup() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger(__name__).info("Application startup: initializing database metadata")
    Base.metadata.create_all(bind=engine)
    _ensure_user_token_columns()
    app.state.scheduler = Scheduler()
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
