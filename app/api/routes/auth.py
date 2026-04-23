import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import UserToken
from app.services.auth.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.services.storage.onedrive import ensure_pipeline_folders_sync

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/login")
def microsoft_login() -> RedirectResponse:
    auth_service = MicrosoftAuthService()
    state = auth_service.generate_state()
    response = RedirectResponse(url=auth_service.build_login_url(state=state), status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="ms_oauth_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
def microsoft_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
    db: Session = Depends(get_db),
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

    auth_service = MicrosoftAuthService()
    try:
        token_payload = auth_service.exchange_code_for_tokens(code=code)
        auth_service.save_tokens(db=db, payload=token_payload)
        ensure_pipeline_folders_sync(token_payload.access_token)
        logger.info(
            "Microsoft login success: tenant_id=%s user_email=%s",
            token_payload.tenant_id,
            token_payload.user_email,
        )
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    response = RedirectResponse(url=settings.FRONTEND_DASHBOARD_URL, status_code=status.HTTP_302_FOUND)
    response.delete_cookie("ms_oauth_state")
    return response


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict[str, str | bool]:
    token_row = db.query(UserToken).order_by(UserToken.updated_at.desc()).first()
    if not token_row:
        return {"authenticated": False, "user_email": ""}
    return {"authenticated": True, "user_email": token_row.user_email}


@router.post("/logout")
def auth_logout(db: Session = Depends(get_db)) -> dict[str, str]:
    # Single-user/dev setup: clear stored delegated token(s).
    db.query(UserToken).delete()
    db.commit()
    return {"detail": "Logged out"}
