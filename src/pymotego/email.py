import base64
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from httpx import Client, Response

from pymotego.constants import DEFAULT_API_BASE_URL

EMAIL_ENDPOINT = "email"


class EmailSendError(Exception):
    """Raised when email sending fails."""

    def __init__(self, message: str, response: Response | None = None):
        super().__init__(message)
        self.response = response


@dataclass(frozen=True)
class SendResult:
    """Result of a successful email send operation."""

    message_id: str
    response: Response


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
class EmailEmbed:
    """Container for embedded images in HTML emails."""

    content_id: str
    filename: str
    content: bytes


@dataclass(frozen=True)
class EmailEmbedPayload:
    """Serialized embed ready for transport."""

    content_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class EmailPayload:
    subject: str
    html_body: str
    attachments: list[EmailAttachmentPayload] | None = None
    embeds: list[EmailEmbedPayload] | None = None
    in_reply_to: str | None = None


class EmailClient:
    """Synchronous HTTP client for cogmoteGO email API."""

    def __init__(self) -> None:
        """Configure client with HTTP/2 enabled connection pooling."""
        self._client = Client(base_url=DEFAULT_API_BASE_URL, http2=True)

    def send(
        self,
        subject: str,
        html_body: str,
        attachments: Sequence[EmailAttachment] | None = None,
        embeds: Sequence[EmailEmbed] | None = None,
        in_reply_to: str | None = None,
    ) -> SendResult:
        """Send an email payload to cogmoteGO."""
        attachments_payload = _prepare_attachments(attachments)
        embeds_payload = _prepare_embeds(embeds)
        payload = EmailPayload(
            subject=subject,
            html_body=html_body,
            attachments=attachments_payload,
            embeds=embeds_payload,
            in_reply_to=in_reply_to,
        )

        response = self._client.post(EMAIL_ENDPOINT, json=asdict(payload))

        if not response.is_success:
            raise EmailSendError(
                f"Failed to send email: {response.status_code}", response
            )

        return SendResult(
            message_id=response.json()["message_id"],
            response=response,
        )

    def send_with_files(
        self,
        subject: str,
        html_body: str,
        files: Iterable[tuple[str, str | Path]],
        embeds: Sequence[EmailEmbed] | None = None,
        in_reply_to: str | None = None,
    ) -> SendResult:
        """Send emails where attachments are described by `(filename, path)` tuples."""
        attachments = [
            EmailAttachment(filename=filename, content=_read_file_bytes(path))
            for filename, path in files
        ]
        return self.send(
            subject=subject,
            html_body=html_body,
            attachments=attachments,
            embeds=embeds,
            in_reply_to=in_reply_to,
        )

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


def _encode_attachment(content: bytes) -> str:
    """Encode raw attachment bytes to base64 for JSON transport."""
    return base64.b64encode(content).decode("ascii")


def _prepare_attachments(
    attachments: Sequence[EmailAttachment] | None,
) -> list[EmailAttachmentPayload] | None:
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


def _prepare_embeds(
    embeds: Sequence[EmailEmbed] | None,
) -> list[EmailEmbedPayload] | None:
    if not embeds:
        return None

    prepared: list[EmailEmbedPayload] = []
    for embed in embeds:
        prepared.append(
            EmailEmbedPayload(
                content_id=embed.content_id,
                filename=embed.filename,
                content=_encode_attachment(embed.content),
            )
        )
    return prepared


def _read_file_bytes(path: str | Path) -> bytes:
    return Path(path).expanduser().read_bytes()


if __name__ == "__main__":
    try:
        with EmailClient() as client:
            result = client.send(
                subject="Test Email",
                html_body="<p>Email client smoke test</p>",
                attachments=[
                    EmailAttachment(filename="hello.txt", content=b"Hello, cogmoteGO!")
                ],
            )
        print(f"Message ID: {result.message_id}")
        print(f"Status: {result.response.status_code}")
    except EmailSendError as e:
        print(f"Failed to send email: {e}")
