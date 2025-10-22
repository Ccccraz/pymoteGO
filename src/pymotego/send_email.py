import base64
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from httpx import Client, Response, URL

from pymotego._constants import DEFAULT_API_BASE_URL

EMAIL_ENDPOINT = "email"


@dataclass(frozen=True)
class EmailAttachment:
    """Container for email attachments."""

    filename: str
    content: bytes


@dataclass(frozen=True)
class EmailAttachmentPayload:
    """Serialized attachment ready for transport."""

    filename: str
    content: str


@dataclass(frozen=True)
class EmailPayload:
    subject: str
    html_body: str
    attachments: list[EmailAttachmentPayload] | None = None


class EmailClient:
    """Synchronous HTTP client for cogmoteGO email API."""

    def __init__(self) -> None:
        """Configure client with HTTP/2 enabled connection pooling."""
        base_url = URL(DEFAULT_API_BASE_URL)
        path = base_url.path
        if not path.endswith("/"):
            base_url = base_url.copy_with(path=path.rstrip("/") + "/")

        self._client = Client(base_url=base_url, http2=True)
        self._email_url = base_url.join(EMAIL_ENDPOINT)

    def send(
        self,
        subject: str,
        html_body: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> Response:
        """Send an email payload to cogmoteGO."""
        attachments_payload = _prepare_attachments(attachments)
        payload = EmailPayload(
            subject=subject,
            html_body=html_body,
            attachments=attachments_payload,
        )

        return self._client.post(self._email_url, json=asdict(payload))

    def send_with_files(
        self,
        subject: str,
        html_body: str,
        files: Iterable[tuple[str, str | Path]],
    ) -> Response:
        """Send emails where attachments are described by `(filename, path)` tuples."""
        attachments = [
            EmailAttachment(filename=filename, content=_read_file_bytes(path))
            for filename, path in files
        ]
        return self.send(
            subject=subject,
            html_body=html_body,
            attachments=attachments,
        )

    def close(self) -> None:
        """Release underlying HTTP resources."""
        self._client.close()

    def __enter__(self) -> "EmailClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _encode_attachment(content: bytes) -> str:
    """Encode raw attachment bytes to base64 for JSON transport."""
    return base64.b64encode(content).decode("ascii")


def _prepare_attachments(
    attachments: Sequence[EmailAttachment] | None,
) -> list["EmailAttachmentPayload"] | None:
    if not attachments:
        return None

    prepared: list[EmailAttachmentPayload] = []
    for attachment in attachments:
        prepared.append(
            EmailAttachmentPayload(
                filename=attachment.filename,
                content=_encode_attachment(attachment.content),
            )
        )
    return prepared


def _read_file_bytes(path: str | Path) -> bytes:
    return Path(path).expanduser().read_bytes()


if __name__ == "__main__":
    with EmailClient() as client:
        response = client.send(
            subject="Test Email",
            html_body="<p>Email client smoke test</p>",
            attachments=[
                EmailAttachment(filename="hello.txt", content=b"Hello, cogmoteGO!")
            ],
        )
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
