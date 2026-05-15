import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import (
    Department,
    DepartmentConfig,
    DepartmentCredentials,
    DepartmentEmailMember,
    DepartmentOAuthToken,
    Document,
    NotificationSettings,
    PipelineRun,
    PipelineRunFile,
)
from app.services.auth.app_auth import CurrentUser, hash_password, require_super_admin

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _normalize_dist_emails(emails: list[str]) -> list[str]:
    return sorted({e.strip().lower() for e in emails if e and str(e).strip()})


def _validate_admin_email(admin_email: str | None, dist: list[str]) -> str | None:
    if not admin_email or not str(admin_email).strip():
        return None
    n = str(admin_email).strip().lower()
    if n not in set(dist):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department admin must be one of the distribution emails.",
        )
    return n


class DepartmentConfigPayload(BaseModel):
    """Pipeline folders plus automation poll interval (same semantics as dashboard /scheduler)."""

    scheduler_interval_seconds: int = Field(default=300, ge=60)
    intake_folder: str = Field(min_length=1, max_length=512)
    processed_folder: str = Field(min_length=1, max_length=512)
    output_success_folder: str = Field(min_length=1, max_length=512)
    output_failure_folder: str = Field(min_length=1, max_length=512)


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=6, max_length=256)
    distribution_emails: list[str] = Field(default_factory=list)
    admin_email: str | None = Field(default=None, max_length=320)
    config: DepartmentConfigPayload


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    username: str | None = Field(default=None, min_length=2, max_length=128)
    password: str | None = Field(default=None, min_length=6, max_length=256)
    distribution_emails: list[str] | None = None
    admin_email: str | None = Field(default=None, max_length=320)
    config: DepartmentConfigPayload | None = None


class DepartmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    dept_username: str
    admin_email: str | None
    distribution_emails: list[str]
    oauth_connected: bool
    connected_email: str | None
    scheduler_interval_seconds: int
    intake_folder: str
    processed_folder: str
    output_success_folder: str
    output_failure_folder: str


@router.get("/departments", response_model=list[DepartmentListItem])
async def list_departments(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[CurrentUser, Depends(require_super_admin)],
) -> list[DepartmentListItem]:
    rows = (
        (
            await db.execute(
                select(Department)
                .options(
                    selectinload(Department.config),
                    selectinload(Department.credentials),
                    selectinload(Department.oauth_token),
                    selectinload(Department.email_members),
                )
                .order_by(Department.name.asc())
            )
        )
        .scalars()
        .all()
    )
    out: list[DepartmentListItem] = []
    dept_ids = [str(d.id) for d in rows if d.config and d.credentials]
    settings_by_dept: dict[str, NotificationSettings] = {}
    if dept_ids:
        stmt = (
            select(NotificationSettings)
            .where(NotificationSettings.department_id.in_(dept_ids))
            .order_by(NotificationSettings.created_at.desc())
        )
        for ns in (await db.execute(stmt)).scalars().all():
            if not ns.department_id:
                continue
            key = str(ns.department_id)
            if key not in settings_by_dept:
                settings_by_dept[key] = ns
    for d in rows:
        cfg = d.config
        creds = d.credentials
        tok = d.oauth_token
        if not cfg or not creds:
            continue
        dist = sorted({m.email for m in (d.email_members or [])})
        ns = settings_by_dept.get(str(d.id))
        interval = max(60, int(getattr(ns, "scheduler_interval_seconds", 0) or 300)) if ns else 300
        out.append(
            DepartmentListItem(
                id=d.id,
                name=d.name,
                dept_username=creds.username,
                admin_email=d.admin_email or None,
                distribution_emails=dist,
                oauth_connected=bool(tok),
                connected_email=(tok.connected_email if tok else None) or None,
                scheduler_interval_seconds=interval,
                intake_folder=cfg.intake_folder,
                processed_folder=cfg.processed_folder,
                output_success_folder=cfg.output_success_folder,
                output_failure_folder=cfg.output_failure_folder,
            )
        )
    return out


@router.get("/departments/{department_id}", response_model=DepartmentListItem)
async def get_department(
    department_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[CurrentUser, Depends(require_super_admin)],
) -> DepartmentListItem:
    dept = (
        (
            await db.execute(
                select(Department)
                .where(Department.id == department_id)
                .options(
                    selectinload(Department.config),
                    selectinload(Department.credentials),
                    selectinload(Department.oauth_token),
                    selectinload(Department.email_members),
                )
            )
        )
        .scalars()
        .first()
    )
    if not dept or not dept.config or not dept.credentials:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")
    tok = dept.oauth_token
    emails = sorted({m.email for m in (dept.email_members or [])})
    cfg = dept.config
    creds = dept.credentials
    ns = (
        (
            await db.execute(
                select(NotificationSettings)
                .where(NotificationSettings.department_id == department_id)
                .order_by(NotificationSettings.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    interval = max(60, int(getattr(ns, "scheduler_interval_seconds", 0) or 300)) if ns else 300
    return DepartmentListItem(
        id=dept.id,
        name=dept.name,
        dept_username=creds.username,
        admin_email=dept.admin_email or None,
        oauth_connected=bool(tok),
        connected_email=(tok.connected_email if tok else None) or None,
        scheduler_interval_seconds=interval,
        intake_folder=cfg.intake_folder,
        processed_folder=cfg.processed_folder,
        output_success_folder=cfg.output_success_folder,
        output_failure_folder=cfg.output_failure_folder,
        distribution_emails=emails,
    )


@router.post("/departments", response_model=DepartmentListItem, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[CurrentUser, Depends(require_super_admin)],
) -> DepartmentListItem:
    exists = (await db.execute(select(DepartmentCredentials).where(DepartmentCredentials.username == payload.username))).scalars().first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department login username already in use.")

    dist_list = _normalize_dist_emails(payload.distribution_emails)
    admin_norm = _validate_admin_email(payload.admin_email, dist_list)

    dept = Department(id=str(uuid.uuid4()), name=payload.name.strip(), admin_email=admin_norm)
    db.add(dept)
    await db.flush()

    cfg = DepartmentConfig(
        id=str(uuid.uuid4()),
        department_id=dept.id,
        schedule_enabled=True,
        schedule_time="09:00",
        intake_folder=payload.config.intake_folder.strip(),
        processed_folder=payload.config.processed_folder.strip(),
        output_success_folder=payload.config.output_success_folder.strip(),
        output_failure_folder=payload.config.output_failure_folder.strip(),
    )
    db.add(cfg)

    creds = DepartmentCredentials(
        id=str(uuid.uuid4()),
        department_id=dept.id,
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(creds)

    for email in dist_list:
        db.add(DepartmentEmailMember(id=str(uuid.uuid4()), department_id=dept.id, email=email))

    settings_row = NotificationSettings(
        id=str(uuid.uuid4()),
        department_id=dept.id,
        eod_time="18:00",
        enabled=False,
        scheduler_interval_seconds=max(60, int(payload.config.scheduler_interval_seconds)),
    )
    db.add(settings_row)

    await db.commit()
    await db.refresh(dept)
    return await get_department(department_id=dept.id, db=db, _admin=admin)


@router.put("/departments/{department_id}", response_model=DepartmentListItem)
async def update_department(
    department_id: str,
    payload: DepartmentUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_super_admin)],
) -> DepartmentListItem:
    dept = (
        (await db.execute(select(Department).where(Department.id == department_id).options(selectinload(Department.config))))
        .scalars()
        .first()
    )
    if not dept or not dept.config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")

    patch = payload.model_dump(exclude_unset=True)

    if payload.name is not None:
        dept.name = payload.name.strip()
    if payload.config is not None:
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
                    .where(NotificationSettings.department_id == department_id)
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
                department_id=department_id,
                eod_time="18:00",
                enabled=False,
                scheduler_interval_seconds=max(60, int(payload.config.scheduler_interval_seconds)),
            )
            db.add(settings_row)
        else:
            settings_row.scheduler_interval_seconds = max(60, int(payload.config.scheduler_interval_seconds))
            db.add(settings_row)

    creds = (await db.execute(select(DepartmentCredentials).where(DepartmentCredentials.department_id == department_id))).scalars().first()
    if creds:
        if payload.username is not None and payload.username.strip() != creds.username:
            clash = (
                await db.execute(select(DepartmentCredentials).where(DepartmentCredentials.username == payload.username.strip()))
            ).scalars().first()
            if clash and clash.id != creds.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already in use.")
            creds.username = payload.username.strip()
        if payload.password is not None:
            creds.password_hash = hash_password(payload.password)
        db.add(creds)

    final_dist: set[str]
    if payload.distribution_emails is not None:
        dist_list = _normalize_dist_emails(payload.distribution_emails)
        await db.execute(delete(DepartmentEmailMember).where(DepartmentEmailMember.department_id == department_id))
        for email in dist_list:
            db.add(DepartmentEmailMember(id=str(uuid.uuid4()), department_id=department_id, email=email))
        final_dist = set(dist_list)
        if dept.admin_email and dept.admin_email.lower() not in final_dist:
            dept.admin_email = None
    else:
        res = await db.execute(select(DepartmentEmailMember.email).where(DepartmentEmailMember.department_id == department_id))
        final_dist = {row[0] for row in res.all()}

    if "admin_email" in patch:
        raw = patch.get("admin_email")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            dept.admin_email = None
        else:
            n = str(raw).strip().lower()
            if n not in final_dist:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department admin must be one of the distribution emails.",
                )
            dept.admin_email = n

    db.add(dept)
    await db.commit()
    return await get_department(department_id=department_id, db=db, _admin=user)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[CurrentUser, Depends(require_super_admin)],
) -> None:
    dept = (await db.execute(select(Department).where(Department.id == department_id))).scalars().first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")

    await db.execute(delete(PipelineRunFile).where(PipelineRunFile.run_id.in_(select(PipelineRun.id).where(PipelineRun.department_id == department_id))))
    await db.execute(delete(PipelineRun).where(PipelineRun.department_id == department_id))
    await db.execute(delete(Document).where(Document.department_id == department_id))
    await db.execute(delete(NotificationSettings).where(NotificationSettings.department_id == department_id))
    await db.execute(delete(DepartmentEmailMember).where(DepartmentEmailMember.department_id == department_id))
    await db.execute(delete(DepartmentOAuthToken).where(DepartmentOAuthToken.department_id == department_id))
    await db.execute(delete(DepartmentCredentials).where(DepartmentCredentials.department_id == department_id))
    await db.execute(delete(DepartmentConfig).where(DepartmentConfig.department_id == department_id))
    await db.execute(delete(Department).where(Department.id == department_id))
    await db.commit()
