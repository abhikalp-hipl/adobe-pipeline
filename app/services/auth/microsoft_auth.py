import base64
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import requests
from requests.exceptions import RequestException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import UserToken

import logging

AUTH_BASE = "https://login.microsoftonline.com/common/oauth2/v2.0"
TOKEN_EXPIRY_BUFFER_SECONDS = 60

logger = logging.getLogger(__name__)
MS_OAUTH_SCOPE = "openid profile email offline_access Files.ReadWrite.All User.Read"


class MicrosoftAuthError(Exception):
    pass


@dataclass(frozen=True)
class MicrosoftTokenPayload:
    access_token: str
    refresh_token: str
    expires_at: datetime
    tenant_id: str
    user_email: str


class MicrosoftAuthService:
    def __init__(self) -> None:
        if not settings.MS_CLIENT_ID or not settings.MS_CLIENT_SECRET:
            raise MicrosoftAuthError("Microsoft OAuth settings are incomplete.")
        self.authority_base = AUTH_BASE

    def build_login_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": settings.MS_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": settings.MS_REDIRECT_URI,
                "response_mode": "query",
                "scope": MS_OAUTH_SCOPE,
                "state": state,
            }
        )
        return f"{self.authority_base}/authorize?{query}"

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    def exchange_code_for_tokens(self, code: str) -> MicrosoftTokenPayload:
        body = {
            "client_id": settings.MS_CLIENT_ID,
            "client_secret": settings.MS_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.MS_REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": MS_OAUTH_SCOPE,
        }
        return self._request_token(body=body, require_identity_claims=True)

    def refresh_access_token(self, refresh_token: str) -> MicrosoftTokenPayload:
        body = {
            "client_id": settings.MS_CLIENT_ID,
            "client_secret": settings.MS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": MS_OAUTH_SCOPE,
        }
        return self._request_token(body=body, require_identity_claims=False)

    def get_valid_access_token(self, db: Session) -> str:
        token_row = db.query(UserToken).order_by(UserToken.updated_at.desc()).first()
        if not token_row:
            raise MicrosoftAuthError("No Microsoft token found. Complete /auth/login first.")

        now = datetime.now(UTC)
        expires_at = self._as_utc(token_row.expires_at)
        if expires_at > (now + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)):
            return token_row.access_token

        refreshed = self.refresh_access_token(token_row.refresh_token)
        token_row.access_token = refreshed.access_token
        token_row.refresh_token = refreshed.refresh_token
        token_row.expires_at = refreshed.expires_at
        if refreshed.tenant_id:
            token_row.tenant_id = refreshed.tenant_id
        if refreshed.user_email:
            token_row.user_email = refreshed.user_email
        db.add(token_row)
        db.commit()
        db.refresh(token_row)
        return token_row.access_token

    def save_tokens(self, db: Session, payload: MicrosoftTokenPayload) -> None:
        token_row = db.query(UserToken).filter(UserToken.user_email == payload.user_email).first()
        if token_row is None:
            token_row = UserToken(
                provider="microsoft",
                user_email=payload.user_email,
                tenant_id=payload.tenant_id,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                expires_at=payload.expires_at,
            )
        else:
            token_row.provider = "microsoft"
            token_row.user_email = payload.user_email
            token_row.tenant_id = payload.tenant_id
            token_row.access_token = payload.access_token
            token_row.refresh_token = payload.refresh_token
            token_row.expires_at = payload.expires_at
        db.add(token_row)
        db.commit()

    def _request_token(self, body: dict[str, str], require_identity_claims: bool) -> MicrosoftTokenPayload:
        token_url = f"{self.authority_base}/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = requests.post(token_url, headers=headers, data=body, timeout=30)
        except RequestException as exc:
            raise MicrosoftAuthError("Failed to reach Microsoft token endpoint.") from exc

        if response.status_code >= 400:
            logger.error(
                "Microsoft token exchange failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise MicrosoftAuthError(
                f"Microsoft token exchange failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")
        id_token = payload.get("id_token")
        if not access_token or not refresh_token or not expires_in:
            raise MicrosoftAuthError("Microsoft token response missing required fields.")
        tenant_id = ""
        user_email = ""
        if id_token:
            claims = self._decode_jwt_claims(id_token)
            tenant_id = claims.get("tid", "")
            user_email = (
                claims.get("preferred_username")
                or claims.get("upn")
                or claims.get("email")
                or ""
            )
        if require_identity_claims and (not tenant_id or not user_email):
            raise MicrosoftAuthError("Microsoft id_token missing required tid/user identity claims.")

        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        return MicrosoftTokenPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            tenant_id=tenant_id,
            user_email=user_email,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _decode_jwt_claims(token: str) -> dict[str, str]:
        parts = token.split(".")
        if len(parts) != 3:
            raise MicrosoftAuthError("Invalid id_token format.")
        payload_segment = parts[1]
        padded = payload_segment + "=" * ((4 - len(payload_segment) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            claims = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise MicrosoftAuthError("Unable to decode Microsoft id_token claims.") from exc
        return claims
