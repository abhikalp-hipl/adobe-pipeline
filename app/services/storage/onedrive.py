import logging
from pathlib import Path
from urllib.parse import quote

import requests
from requests import Response
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

INTAKE_FOLDER = "AdobePipeline/intake"
PROCESSED_FOLDER = "AdobePipeline/processed"
OUTPUT_SUCCESS_FOLDER = "AdobePipeline/output/success"
OUTPUT_FAILURE_FOLDER = "AdobePipeline/output/failure"


class OneDriveError(Exception):
    pass


class OneDriveAuthError(OneDriveError):
    pass


class OneDriveNotFoundError(OneDriveError):
    pass


class OneDriveClient:
    BASE_URL = "https://graph.microsoft.com/v1.0/me/drive"

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def list_files(self, access_token: str, folder_path: str) -> list[dict]:
        encoded_folder = quote(folder_path.strip("/"), safe="/")
        endpoint = f"/root:/{encoded_folder}:/children"
        response = self._request(access_token, "GET", endpoint)
        payload = response.json()
        logger.info("OneDrive list_files response: status=%s endpoint=%s", response.status_code, endpoint)
        logger.info("OneDrive list_files payload: %s", payload)
        if isinstance(payload, dict) and payload.get("error"):
            error_message = payload.get("error", {}).get("message", "Unknown Graph API error.")
            raise OneDriveError(f"OneDrive list_files failed: {error_message}")
        files: list[dict] = []
        for item in payload.get("value", []):
            if "file" not in item:
                continue
            item_id = item.get("id")
            item_name = item.get("name")
            if item_id and item_name:
                files.append(
                    {
                        "id": item_id,
                        "name": item_name,
                        "type": "file",
                        "mime_type": item.get("file", {}).get("mimeType", "application/octet-stream"),
                        "last_modified": item.get("lastModifiedDateTime", ""),
                        "size_bytes": int(item.get("size") or 0),
                    }
                )
        return files

    def get_item_metadata(self, access_token: str, file_id: str) -> dict:
        response = self._request(access_token, "GET", f"/items/{file_id}")
        return response.json()

    def get_file_content(self, access_token: str, file_id: str) -> Response:
        return self._request(access_token, "GET", f"/items/{file_id}/content", stream=True)

    def get_file_content_as_pdf(self, access_token: str, file_id: str) -> Response:
        return self._request(
            access_token,
            "GET",
            f"/items/{file_id}/content",
            params={"format": "pdf"},
            stream=True,
        )

    def create_share_link(
        self,
        access_token: str,
        file_id: str,
        link_type: str = "view",
        scope: str = "anonymous",
    ) -> str:
        response = self._request(
            access_token,
            "POST",
            f"/items/{file_id}/createLink",
            json={"type": link_type, "scope": scope},
        )
        payload = response.json()
        web_url = payload.get("link", {}).get("webUrl")
        if not web_url:
            raise OneDriveError("Microsoft Graph createLink response missing link.webUrl.")
        return web_url

    def download_file(self, access_token: str, file_id: str, local_path: str | Path) -> Path:
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._request(access_token, "GET", f"/items/{file_id}/content", stream=True)
        try:
            with destination.open("wb") as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        target.write(chunk)
        except OSError as exc:
            raise OneDriveError(f"Failed to save downloaded file to '{destination}'.") from exc
        return destination

    def upload_file(self, access_token: str, local_path: str | Path, folder_path: str, filename: str) -> dict:
        source = Path(local_path)
        if not source.exists():
            raise OneDriveNotFoundError(f"Upload source file not found: {source}")

        encoded_folder = quote(folder_path.strip("/"), safe="/")
        encoded_filename = quote(filename)
        upload_endpoint = f"/root:/{encoded_folder}/{encoded_filename}:/content"
        try:
            with source.open("rb") as file_obj:
                response = self._request(access_token, "PUT", upload_endpoint, data=file_obj.read())
            return response.json()
        except OSError as exc:
            raise OneDriveError(f"Failed to read upload source file '{source}'.") from exc

    def delete_file(self, access_token: str, file_id: str) -> None:
        self._request(access_token, "DELETE", f"/items/{file_id}")

    def move_file(
        self,
        access_token: str,
        file_id: str,
        folder_path: str,
        filename: str | None = None,
    ) -> dict:
        encoded_folder = quote(folder_path.strip("/"), safe="/")
        payload: dict = {
            "parentReference": {
                "path": f"/drive/root:/{encoded_folder}",
            }
        }
        if filename:
            payload["name"] = filename
        response = self._request(access_token, "PATCH", f"/items/{file_id}", json=payload)
        return response.json()

    @staticmethod
    def _require_token(access_token: str | None) -> str:
        token = (access_token or "").strip()
        if not token:
            raise OneDriveAuthError("A delegated Microsoft Graph access token is required.")
        return token

    def _request(self, access_token: str, method: str, endpoint: str, **kwargs) -> Response:
        token = self._require_token(access_token)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except RequestException as exc:
            raise OneDriveError(f"Microsoft Graph request failed: {method} {url}") from exc

        if response.status_code == 404:
            raise OneDriveNotFoundError(f"OneDrive resource not found for request: {method} {endpoint}")
        if response.status_code == 401:
            raise OneDriveAuthError("Microsoft Graph token is invalid or expired.")
        if response.status_code >= 400:
            raise OneDriveError(
                f"Microsoft Graph request failed: method={method} endpoint={endpoint} "
                f"status={response.status_code} body={response.text}"
            )
        return response
