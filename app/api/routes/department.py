import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Department, DepartmentConfig, DepartmentEmailMember, DepartmentOAuthToken, NotificationSettings
from app.services.auth.app_auth import CurrentUser, require_dept_user

router = APIRouter(prefix="/departments", tags=["departments"])
logger = logging.getLogger(__name__)


class DepartmentConfigPayload(BaseModel):
    """Folders plus automation poll interval (same as dashboard /scheduler interval)."""

    scheduler_interval_seconds: int = Field(default=300, ge=60)
    intake_folder: str = Field(min_length=1, max_length=512)
    processed_folder: str = Field(min_length=1, max_length=512)
    output_success_folder: str = Field(min_length=1, max_length=512)
    output_failure_folder: str = Field(min_length=1, max_length=512)


class DepartmentMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    admin_email: str | None = None
    scheduler_interval_seconds: int
    intake_folder: str
    processed_folder: str
    output_success_folder: str
    output_failure_folder: str
    distribution_emails: list[str]


class DepartmentMeUpdateRequest(BaseModel):
    config: DepartmentConfigPayload
    distribution_emails: list[str] = Field(default_factory=list)


class DepartmentMicrosoftStatusResponse(BaseModel):
    connected: bool
    connected_email: str | None = None


@router.get("/me/microsoft-status", response_model=DepartmentMicrosoftStatusResponse)
async def get_my_microsoft_status(
    user: Annotated[CurrentUser, Depends(require_dept_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentMicrosoftStatusResponse:
    assert user.department_id
    tok = (
        (await db.execute(select(DepartmentOAuthToken).where(DepartmentOAuthToken.department_id == user.department_id)))
        .scalars()
        .first()
    )
    if not tok:
        return DepartmentMicrosoftStatusResponse(connected=False, connected_email=None)
    return DepartmentMicrosoftStatusResponse(
        connected=True,
        connected_email=tok.connected_email or None,
    )


@router.get("/me", response_model=DepartmentMeResponse)
async def get_my_department(
    user: Annotated[CurrentUser, Depends(require_dept_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentMeResponse:
    assert user.department_id
    dept = (
        (
            await db.execute(
                select(Department)
                .where(Department.id == user.department_id)
                .options(selectinload(Department.config), selectinload(Department.email_members))
            )
        )
        .scalars()
        .first()
    )
    if not dept or not dept.config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")
    cfg = dept.config
    emails = sorted({m.email for m in (dept.email_members or [])})
    ns = (
        (
            await db.execute(
                select(NotificationSettings)
                .where(NotificationSettings.department_id == user.department_id)
                .order_by(NotificationSettings.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    interval = max(60, int(getattr(ns, "scheduler_interval_seconds", 0) or 300)) if ns else 300
    return DepartmentMeResponse(
        id=dept.id,
        name=dept.name,
        admin_email=dept.admin_email or None,
        scheduler_interval_seconds=interval,
        intake_folder=cfg.intake_folder,
        processed_folder=cfg.processed_folder,
        output_success_folder=cfg.output_success_folder,
        output_failure_folder=cfg.output_failure_folder,
        distribution_emails=emails,
    )


@router.put("/me", response_model=DepartmentMeResponse)
async def update_my_department(
    payload: DepartmentMeUpdateRequest,
    user: Annotated[CurrentUser, Depends(require_dept_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentMeResponse:
    assert user.department_id
    dept = (
        (await db.execute(select(Department).where(Department.id == user.department_id).options(selectinload(Department.config))))
        .scalars()
        .first()
    )
    if not dept or not dept.config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")
    cfg = dept.config
    cfg.intake_folder = payload.config.intake_folder.strip()
    cfg.processed_folder = payload.config.processed_folder.strip()
    cfg.output_success_folder = payload.config.output_success_folder.strip()
    cfg.output_failure_folder = payload.config.output_failure_folder.strip()
    db.add(cfg)

    settings_row = (
        (
            await db.execute(
                select(NotificationSettings)
                .where(NotificationSettings.department_id == user.department_id)
                .order_by(NotificationSettings.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if not settings_row:
        settings_row = NotificationSettings(
            id=str(uuid.uuid4()),
            department_id=user.department_id,
            eod_time="18:00",
            enabled=False,
            scheduler_interval_seconds=max(60, int(payload.config.scheduler_interval_seconds)),
        )
        db.add(settings_row)
    else:
        settings_row.scheduler_interval_seconds = max(60, int(payload.config.scheduler_interval_seconds))
        db.add(settings_row)

    admin_before = (dept.admin_email or "").strip().lower() or None
    await db.execute(delete(DepartmentEmailMember).where(DepartmentEmailMember.department_id == user.department_id))
    new_set: set[str] = set()
    for email in payload.distribution_emails:
        normalized = email.strip().lower()
        if normalized:
            new_set.add(normalized)
            db.add(
                DepartmentEmailMember(
                    id=str(uuid.uuid4()),
                    department_id=user.department_id,
                    email=normalized,
                )
            )
    if admin_before and admin_before not in new_set:
        dept.admin_email = None
        db.add(dept)

    await db.commit()
    return await get_my_department(db=db, user=user)
