from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

http_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: Literal["super_admin", "dept_user"]
    department_id: str | None


def create_access_token(*, username: str, role: Literal["super_admin", "dept_user"], department_id: str | None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=max(5, settings.JWT_EXPIRE_MINUTES))
    payload = {
        "sub": username,
        "role": role,
        "department_id": department_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc
    username = str(payload.get("sub") or "")
    role = payload.get("role")
    department_id = payload.get("department_id")
    if not username or role not in ("super_admin", "dept_user"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    if role == "dept_user" and not department_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    return CurrentUser(username=username, role=role, department_id=department_id if role == "dept_user" else None)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def require_super_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required.")
    return user


async def require_dept_user(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.role != "dept_user" or not user.department_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department user access required.")
    return user
