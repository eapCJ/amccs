from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amccs.adb import ADBClient, ADBError
from amccs.service import create_app


class StubADB(ADBClient):
    __slots__ = ("devices", "photo_bytes", "pull_calls", "remote_photo", "shell_calls")

    def __init__(self, *, devices: list[str], photo_bytes: bytes) -> None:
        super().__init__()
        self.devices = devices
        self.photo_bytes = photo_bytes
        self.shell_calls: list[tuple[str, str]] = []
        self.pull_calls: list[tuple[str, str, str]] = []
        self.remote_photo = "/sdcard/DCIM/latest.jpg"

    async def list_devices(self) -> list[str]:
        await asyncio.sleep(0)
        return self.devices

    async def shell(self, serial: str, command: str, *, check: bool = True) -> str:
        self.shell_calls.append((serial, command))
        await asyncio.sleep(0)
        if "ls -t" in command:
            return f"{self.remote_photo}\n"
        return "ok"

    async def pull(self, serial: str, remote: str, local: str, *, check: bool = True) -> None:
        self.pull_calls.append((serial, remote, local))
        Path(local).write_bytes(self.photo_bytes)
        await asyncio.sleep(0)


def _write_config(tmp_path: Path) -> Path:
    yaml_text = """
    settings:
      request_timeout_seconds: 3
      adb_command_timeout_seconds: 1.5
      camera_defaults:
        package: com.camera
        activity: .Main
        photo_location: /sdcard/DCIM/Camera
        zoom_point:
          x: 1
          y: 2
        delays:
          camera_open: 0
          zoom: 0
          photo_capture: 0
          photo_save: 0
    """
    path = tmp_path / "config.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


@pytest.fixture
def app(tmp_path: Path) -> Iterator[tuple[TestClient, StubADB]]:
    config_path = _write_config(tmp_path)
    adb = StubADB(devices=["SER123"], photo_bytes=b"img-bytes")
    application = create_app(config_path=str(config_path), adb_client=adb)
    with TestClient(application) as client:
        yield client, adb


def test_root_reports_service_metadata(app: tuple[TestClient, StubADB]) -> None:
    client, _ = app
    response = client.get("/")
    data = response.json()

    assert response.status_code == 200
    assert data["service"] == "amccs"
    assert data["timeout"] == 3
    assert data["auth_enabled"] is False


def test_health_lists_devices(app: tuple[TestClient, StubADB]) -> None:
    client, _ = app
    response = client.get("/health")
    data = response.json()

    assert response.status_code == 200
    assert data["service"] == "amccs"
    assert data["status"] == "healthy"
    assert len(data["devices"]) == 1
    assert data["devices"][0]["ok"] is True


def test_capture_returns_base64_payload(app: tuple[TestClient, StubADB]) -> None:
    client, adb = app
    response = client.post("/capture")
    data = response.json()

    assert response.status_code == 200
    assert data["service"] == "amccs"
    assert data["count"] == 1

    payload = data["devices"][0]
    decoded = base64.b64decode(payload["image_base64"])
    assert decoded == b"img-bytes"

    assert any("am start" in command for _, command in adb.shell_calls)
    assert adb.pull_calls


def test_prime_then_capture_reuses_prepared_state(app: tuple[TestClient, StubADB]) -> None:
    client, adb = app

    prime_response = client.post("/prime")
    assert prime_response.status_code == 200
    assert prime_response.json()["primed_devices"] == 1

    am_start_calls_after_prime = sum(1 for _, command in adb.shell_calls if "am start" in command)
    assert am_start_calls_after_prime == 1

    capture_response = client.post("/capture")
    assert capture_response.status_code == 200

    am_start_calls_after_capture = sum(1 for _, command in adb.shell_calls if "am start" in command)
    assert am_start_calls_after_capture == 1  # no additional prepare run


def test_prime_returns_400_when_no_devices(app: tuple[TestClient, StubADB]) -> None:
    client, adb = app
    adb.devices = []

    response = client.post("/prime")

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "No ADB devices detected"


def test_capture_returns_400_when_not_primed_and_no_devices(
    app: tuple[TestClient, StubADB]
) -> None:
    client, adb = app
    adb.devices = []

    response = client.post("/capture")

    assert response.status_code == 400
    assert "No ADB devices detected" in response.json()["detail"]["message"]


class ErrorADB(StubADB):
    async def shell(self, serial: str, command: str, *, check: bool = True) -> str:
        raise ADBError("boom")

    async def pull(self, serial: str, remote: str, local: str, *, check: bool = True) -> None:
        raise ADBError("boom")


def test_prime_returns_502_when_adb_fails(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    adb = ErrorADB(devices=["SER123"], photo_bytes=b"img")
    application = create_app(config_path=str(config_path), adb_client=adb)

    with TestClient(application) as client:
        response = client.post("/prime")

    assert response.status_code == 502


def test_capture_requires_token_when_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    adb = StubADB(devices=["SER123"], photo_bytes=b"img-bytes")
    token = "secret-token"  # noqa: S105 - test-only token literal
    application = create_app(config_path=str(config_path), adb_client=adb, api_token=token)

    with TestClient(application) as client:
        unauthorized = client.post("/prime")
        assert unauthorized.status_code == 401

        response = client.post("/prime", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

        capture_response = client.post("/capture", headers={"Authorization": f"Bearer {token}"})
        assert capture_response.status_code == 200
