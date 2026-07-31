"""Synchronous client for the cogmoteGO internal backup API."""

from enum import StrEnum
from types import TracebackType
from typing import Literal, Self

from httpx import URL, BaseTransport, Client, Response
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
)

from pymotego.constants import DEFAULT_INTERNAL_API_BASE_URL

BACKUPS_ENDPOINT = "backups"
_ERROR_PAYLOAD_ADAPTER = TypeAdapter(
    dict[str, object],
    config=ConfigDict(strict=True),
)


class BackupStatus(StrEnum):
    """State of a backup task."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"


class BackupPhase(StrEnum):
    """Current phase of a backup task."""

    SCANNING = "scanning"
    UPLOADING = "uploading"
    VERIFYING = "verifying"
    PUBLISHING = "publishing"
    COMPLETED = "completed"


class BackupEntryStatus(StrEnum):
    """State of an entry within a backup task."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BackupError(Exception):
    """Base exception for backup client failures."""


class BackupAPIError(BackupError):
    """Raised when the backup API returns an unsuccessful response."""

    def __init__(
        self,
        message: str,
        response: Response,
        *,
        error: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.error = error
        self.detail = detail


class BackupResponseError(BackupError):
    """Raised when a successful API response has an invalid payload."""

    def __init__(self, message: str, response: Response) -> None:
        super().__init__(message)
        self.response = response


class _BackupModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="ignore")


class BackupSource(_BackupModel):
    """Trusted source root and relative entries selected for backup."""

    root_id: str
    entries: tuple[str, ...]


class BackupDestination(_BackupModel):
    """Trusted Samba destination for a backup."""

    root_id: str
    path: str = "."
    type: Literal["samba"] = "samba"


class BackupEntry(_BackupModel):
    """Progress and outcome for one selected source entry."""

    path: str
    type: str
    status: BackupEntryStatus
    error: str | None = None


class BackupTask(_BackupModel):
    """Typed representation of a cogmoteGO backup task."""

    id: str
    status: BackupStatus
    phase: BackupPhase
    source: BackupSource
    destination: BackupDestination
    entries: tuple[BackupEntry, ...]
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    files_total: int
    files_completed: int
    bytes_total: int
    bytes_transferred: int
    current_path: str | None = None
    error: str | None = None


class BackupClient:
    """Synchronous HTTP client for cogmoteGO's loopback-only backup API."""

    def __init__(
        self,
        base_url: str | URL = DEFAULT_INTERNAL_API_BASE_URL,
        *,
        transport: BaseTransport | None = None,
    ) -> None:
        self._client = Client(
            base_url=base_url,
            http2=True,
            transport=transport,
        )

    def create(
        self,
        source: BackupSource,
        destination: BackupDestination,
    ) -> BackupTask:
        """Create and return an asynchronous backup task."""
        response = self._client.post(
            BACKUPS_ENDPOINT,
            json={
                "source": source.model_dump(mode="json"),
                "destination": destination.model_dump(mode="json"),
            },
        )
        if not response.is_success:
            _raise_api_error(response)
        return _parse_task_response(response)

    def current(self) -> BackupTask | None:
        """Return the current backup task, or ``None`` if none exists."""
        response = self._client.get(BACKUPS_ENDPOINT)
        if response.status_code == 404:
            return None
        if not response.is_success:
            _raise_api_error(response)
        return _parse_task_response(response)

    def close(self) -> None:
        """Release underlying HTTP resources."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def _parse_task_response(response: Response) -> BackupTask:
    try:
        return BackupTask.model_validate_json(response.content)
    except ValidationError as error:
        raise BackupResponseError(
            f"Invalid backup task response: {error}",
            response,
        ) from error


def _raise_api_error(response: Response) -> None:
    error_name: str | None = None
    detail: str | None = None
    try:
        payload = _ERROR_PAYLOAD_ADAPTER.validate_json(response.content)
        raw_error = payload.get("error")
        raw_detail = payload.get("detail")
        if isinstance(raw_error, str):
            error_name = raw_error
        if isinstance(raw_detail, str):
            detail = raw_detail
    except ValidationError:
        pass

    message = f"Backup API request failed: {response.status_code}"
    if error_name:
        message = f"{message} {error_name}"
    raise BackupAPIError(
        message,
        response,
        error=error_name,
        detail=detail,
    )
