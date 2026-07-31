import json
import unittest
from datetime import UTC

from httpx import MockTransport, Request, Response
from pydantic import ValidationError

from pymotego import (
    BackupAPIError,
    BackupClient,
    BackupDestination,
    BackupEntryStatus,
    BackupPhase,
    BackupResponseError,
    BackupSource,
    BackupStatus,
)


class TrackingTransport(MockTransport):
    closed: bool

    def __init__(self) -> None:
        super().__init__(lambda request: Response(404, json={}))
        self.closed = False

    def close(self) -> None:
        self.closed = True
        super().close()


def task_payload() -> dict[str, object]:
    return {
        "id": "task-123",
        "status": "running",
        "phase": "uploading",
        "source": {
            "root_id": "project-data",
            "entries": ["run-01", "run-02/result.jsonl"],
        },
        "destination": {
            "type": "samba",
            "root_id": "lab-nas",
            "path": "experiments/project/data",
        },
        "entries": [
            {
                "path": "run-01",
                "type": "directory",
                "status": "running",
            },
            {
                "path": "run-02/result.jsonl",
                "type": "file",
                "status": "pending",
            },
        ],
        "created_at": "2026-07-30T12:34:56.123456789Z",
        "started_at": "2026-07-30T12:34:56.123456789Z",
        "files_total": 8,
        "files_completed": 3,
        "bytes_total": 4096,
        "bytes_transferred": 1024,
        "current_path": "run-01/data.bin",
    }


class BackupClientTests(unittest.TestCase):
    def test_create_sends_payload_and_parses_task(self) -> None:
        def handler(request: Request) -> Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                str(request.url),
                "http://127.0.0.1:9011/api/backups",
            )
            self.assertEqual(
                json.loads(request.content),
                {
                    "source": {
                        "root_id": "project-data",
                        "entries": ["run-01", "run-02/result.jsonl"],
                    },
                    "destination": {
                        "type": "samba",
                        "root_id": "lab-nas",
                        "path": "experiments/project/data",
                    },
                },
            )
            return Response(202, json=task_payload())

        source = BackupSource(
            root_id="project-data",
            entries=("run-01", "run-02/result.jsonl"),
        )
        destination = BackupDestination(
            root_id="lab-nas",
            path="experiments/project/data",
        )

        with BackupClient(transport=MockTransport(handler)) as client:
            task = client.create(source, destination)

        self.assertEqual(source.entries, ("run-01", "run-02/result.jsonl"))
        self.assertEqual(task.id, "task-123")
        self.assertIs(task.status, BackupStatus.RUNNING)
        self.assertIs(task.phase, BackupPhase.UPLOADING)
        self.assertEqual(task.source, source)
        self.assertEqual(task.destination, destination)
        self.assertIs(task.entries[0].status, BackupEntryStatus.RUNNING)
        self.assertIs(task.entries[1].status, BackupEntryStatus.PENDING)
        self.assertEqual(task.created_at.tzinfo, UTC)
        self.assertEqual(task.created_at.microsecond, 123456)
        self.assertIsNone(task.finished_at)
        self.assertEqual(task.files_total, 8)
        self.assertEqual(task.bytes_transferred, 1024)

    def test_current_returns_task(self) -> None:
        def handler(request: Request) -> Response:
            self.assertEqual(request.method, "GET")
            return Response(200, json=task_payload())

        with BackupClient(
            base_url="http://localhost:9999/internal/api",
            transport=MockTransport(handler),
        ) as client:
            task = client.current()

        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.current_path, "run-01/data.bin")

    def test_current_returns_none_for_not_found(self) -> None:
        transport = MockTransport(
            lambda request: Response(
                404,
                json={"error": "backup task not found", "detail": ""},
            )
        )

        with BackupClient(transport=transport) as client:
            self.assertIsNone(client.current())

    def test_api_error_preserves_response_details(self) -> None:
        for status_code, error_name in (
            (400, "failed to create backup task"),
            (409, "backup already running"),
        ):
            with self.subTest(status_code=status_code):

                def handler(
                    request: Request,
                    response_status: int = status_code,
                    response_error: str = error_name,
                ) -> Response:
                    return Response(
                        response_status,
                        json={
                            "error": response_error,
                            "detail": "task task-123 is currently running",
                        },
                    )

                transport = MockTransport(handler)

                with (
                    BackupClient(transport=transport) as client,
                    self.assertRaises(BackupAPIError) as raised,
                ):
                    client.create(
                        BackupSource(
                            root_id="project-data",
                            entries=("run-01",),
                        ),
                        BackupDestination(
                            root_id="lab-nas",
                            path="experiments/project/data",
                        ),
                    )

            self.assertEqual(
                raised.exception.response.status_code,
                status_code,
            )
            self.assertEqual(raised.exception.error, error_name)
            self.assertEqual(
                raised.exception.detail,
                "task task-123 is currently running",
            )

    def test_response_error_for_invalid_success_payload(self) -> None:
        invalid_responses = (
            Response(200, json={"id": "incomplete"}),
            Response(200, json=_task_payload_with(files_total=True)),
            Response(200, json=_task_payload_with(status="unknown")),
            Response(200, json=_task_payload_with(source=[])),
            Response(
                200,
                json=_task_payload_with(created_at="2026-07-30T12:34:56"),
            ),
            Response(200, content=b"{"),
        )

        for response in invalid_responses:
            with self.subTest(content=response.content):
                transport = MockTransport(lambda request, current=response: current)
                with (
                    BackupClient(transport=transport) as client,
                    self.assertRaises(BackupResponseError) as raised,
                ):
                    client.current()

                self.assertEqual(raised.exception.response.status_code, 200)

    def test_response_ignores_extra_fields(self) -> None:
        transport = MockTransport(
            lambda request: Response(
                200,
                json=_task_payload_with(future_field={"enabled": True}),
            )
        )

        with BackupClient(transport=transport) as client:
            task = client.current()

        self.assertIsNotNone(task)

    def test_api_error_fields_are_parsed_independently(self) -> None:
        transport = MockTransport(
            lambda request: Response(
                400,
                json={
                    "error": 42,
                    "detail": "valid detail",
                },
            )
        )

        with (
            BackupClient(transport=transport) as client,
            self.assertRaises(BackupAPIError) as raised,
        ):
            client.create(
                BackupSource(root_id="project-data", entries=("run-01",)),
                BackupDestination(
                    root_id="lab-nas",
                    path="experiments/project/data",
                ),
            )

        self.assertIsNone(raised.exception.error)
        self.assertEqual(raised.exception.detail, "valid detail")

    def test_backup_models_are_frozen(self) -> None:
        source = BackupSource(
            root_id="project-data",
            entries=("run-01",),
        )
        field_name = "root_id"

        with self.assertRaises(ValidationError):
            setattr(source, field_name, "other")

    def test_context_manager_closes_client(self) -> None:
        transport = TrackingTransport()
        client = BackupClient(transport=transport)

        with client:
            self.assertFalse(transport.closed)

        self.assertTrue(transport.closed)


def _task_payload_with(**updates: object) -> dict[str, object]:
    payload = task_payload()
    payload.update(updates)
    return payload


if __name__ == "__main__":
    unittest.main()
