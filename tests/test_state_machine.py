from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from amccs.adb import ADBClient
from amccs.config import CaptureDefaults, DelaySettings, ZoomPoint
from amccs.state_machine import CameraStateMachine, CapturePhase


class RecordingADB(ADBClient):
    __slots__ = ("photo_bytes", "pull_calls", "remote_photo", "shell_calls")

    def __init__(self, photo_bytes: bytes) -> None:
        super().__init__()
        self.photo_bytes = photo_bytes
        self.shell_calls: list[tuple[str, str]] = []
        self.pull_calls: list[tuple[str, str, str]] = []
        self.remote_photo = "/sdcard/DCIM/latest.jpg"

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


@pytest.fixture
def defaults() -> CaptureDefaults:
    return CaptureDefaults(
        package="com.camera.app",
        activity=".Main",
        photo_location="/sdcard/DCIM/Camera",
        zoom_point=ZoomPoint(x=100, y=200),
        delays=DelaySettings(camera_open=0.0, zoom=0.0, photo_capture=0.0, photo_save=0.0),
    )


@pytest.mark.asyncio
async def test_state_machine_requires_prepare(defaults: CaptureDefaults) -> None:
    adb = RecordingADB(b"test-bytes")
    machine = CameraStateMachine(serial="ZX1", adb=adb, defaults=defaults)

    with pytest.raises(RuntimeError):
        await machine.capture()

    assert machine.phase is CapturePhase.IDLE


@pytest.mark.asyncio
async def test_state_machine_runs_two_phases(defaults: CaptureDefaults) -> None:
    adb = RecordingADB(b"img-bytes")
    machine = CameraStateMachine(serial="ZX1", adb=adb, defaults=defaults)

    await machine.prepare()
    assert machine.phase is CapturePhase.PREPARED
    unlock_commands = "KEYCODE_WAKEUP" in " ".join(cmd for _, cmd in adb.shell_calls)
    assert unlock_commands

    result = await machine.capture()

    assert result.serial == "ZX1"
    assert result.image_bytes == b"img-bytes"
    assert machine.phase is CapturePhase.COMPLETE
    assert any("rm -f" in command for _, command in adb.shell_calls)
    assert adb.pull_calls
