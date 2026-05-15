from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.database import get_db
from app.db.models import DepartmentCredentials, SuperAdmin
from app.services.auth.app_auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class AppLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class AppLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    department_id: str | None = None


@router.post("/login", response_model=AppLoginResponse)
async def app_login(payload: AppLoginRequest, db: AsyncSession = Depends(get_db)) -> AppLoginResponse:
    username = payload.username.strip()
    password = payload.password

    super_row = (await db.execute(select(SuperAdmin).where(SuperAdmin.username == username))).scalars().first()
    if super_row and verify_password(password, super_row.password_hash):
        token = create_access_token(username=username, role="super_admin", department_id=None)
        return AppLoginResponse(access_token=token, role="super_admin", department_id=None)

    cred_row = (
        await db.execute(select(DepartmentCredentials).where(DepartmentCredentials.username == username))
    ).scalars().first()
    if cred_row and verify_password(password, cred_row.password_hash):
        token = create_access_token(
            username=username,
            role="dept_user",
            department_id=cred_row.department_id,
        )
        return AppLoginResponse(access_token=token, role="dept_user", department_id=cred_row.department_id)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
