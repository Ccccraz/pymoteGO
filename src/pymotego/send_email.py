import base64
from dataclasses import dataclass
from typing import Iterable, Sequence

from httpx import Client, Response, URL

from pymotego._constants import DEFAULT_API_BASE_URL

EMAIL_ENDPOINT = "email"


@dataclass(frozen=True)
class EmailAttachment:
    """Container for email attachments."""

    filename: str
    content: bytes


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
        payload: dict[str, object] = {
            "subject": subject,
            "html_body": html_body,
        }

        if attachments:
            payload["attachments"] = [
                {
                    "filename": attachment.filename,
                    "content": _encode_attachment(attachment.content),
                }
                for attachment in attachments
            ]

        return self._client.post(self._email_url, json=payload)

    def send_with_files(
        self,
        subject: str,
        html_body: str,
        files: Iterable[tuple[str, bytes]],
    ) -> Response:
        """Helper for sending emails where attachments are provided as `(filename, content)` tuples."""
        attachments = [
            EmailAttachment(filename=filename, content=content)
            for filename, content in files
        ]
        return self.send(subject=subject, html_body=html_body, attachments=attachments)

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


if __name__ == "__main__":
    attachment = EmailAttachment(filename="hello.txt", content=b"Hello, cogmoteGO!")
    with EmailClient() as client:
        response = client.send(
            subject="Test Email",
            html_body="<p>Email client smoke test</p>",
            attachments=[attachment],
        )
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")
