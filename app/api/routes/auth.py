import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Department
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.storage.onedrive import ensure_pipeline_folders

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/dept/{department_id}/login")
async def department_microsoft_login(
    department_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    dept = (await db.execute(select(Department).where(Department.id == department_id))).scalars().first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found.")
    auth_service = MicrosoftAuthService()
    state = auth_service.generate_state()
    login_hint = (dept.admin_email or "").strip() or None
    # Do not silently reuse the browser's Microsoft session for the wrong account (see settings.MS_DEPT_OAUTH_PROMPT).
    dept_auth_url = auth_service.build_login_url(
        state=state,
        prompt=settings.MS_DEPT_OAUTH_PROMPT,
        login_hint=login_hint,
    )
    response = RedirectResponse(url=dept_auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="ms_oauth_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
    )
    response.set_cookie(
        key="ms_oauth_department_id",
        value=department_id,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
async def microsoft_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Microsoft authorization failed: {error} {error_description}".strip(),
        )
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code is missing.")
    expected_state = request.cookies.get("ms_oauth_state", "")
    if not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state.")

    dept_id = request.cookies.get("ms_oauth_department_id", "").strip()

    auth_service = MicrosoftAuthService()
    try:
        token_payload = await auth_service.exchange_code_for_tokens(code=code)
        if not dept_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department context missing. Start Microsoft sign-in from the admin panel.",
            )
        await auth_service.save_tokens_for_department(db=db, department_id=dept_id, payload=token_payload)
        dept = (
            (
                await db.execute(
                    select(Department)
                    .where(Department.id == dept_id)
                    .options(selectinload(Department.config))
                )
            )
            .scalars()
            .first()
        )
        cfg = dept.config if dept else None
        await ensure_pipeline_folders(
            token_payload.access_token,
            intake_folder=cfg.intake_folder if cfg else None,
            processed_folder=cfg.processed_folder if cfg else None,
            output_success_folder=cfg.output_success_folder if cfg else None,
            output_failure_folder=cfg.output_failure_folder if cfg else None,
        )
        logger.info(
            "Microsoft dept OAuth success: department_id=%s tenant_id=%s user_email=%s",
            dept_id,
            token_payload.tenant_id,
            token_payload.user_email,
        )
        admin_url = settings.FRONTEND_ADMIN_URL.rstrip("/")
        redirect_url = (
            f"{admin_url}&dept_oauth=success"
            if "?" in admin_url
            else f"{admin_url}?dept_oauth=success"
        )
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    response.delete_cookie("ms_oauth_state")
    response.delete_cookie("ms_oauth_department_id")
    return response


