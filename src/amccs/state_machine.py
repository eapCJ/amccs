"""State machine coordinating camera capture phases."""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from .adb import ADBClient, ADBError
from .config import CaptureDefaults


class CapturePhase(Enum):
    IDLE = auto()
    PREPARING = auto()
    PREPARED = auto()
    CAPTURING = auto()
    COMPLETE = auto()
    ERROR = auto()


@dataclass(slots=True)
class CaptureArtifact:
    serial: str
    position: str | None
    image_bytes: bytes


class CameraStateMachine:
    """Implements the two-phase capture workflow for a single device."""

    def __init__(
        self,
        *,
        serial: str,
        adb: ADBClient,
        defaults: CaptureDefaults,
        position: str | None = None,
        skip_zoom: bool = False,
    ) -> None:
        self.serial = serial
        self._adb = adb
        self._defaults = defaults
        self._position = position
        self._skip_zoom = skip_zoom
        self.phase = CapturePhase.IDLE

    async def prepare(self) -> None:
        if self.phase not in (CapturePhase.IDLE, CapturePhase.COMPLETE):
            return
        self.phase = CapturePhase.PREPARING

        await self._adb.shell(self.serial, "input keyevent KEYCODE_WAKEUP", check=False)
        await asyncio.sleep(0.1)
        await self._adb.shell(self.serial, "input keyevent KEYCODE_MENU", check=False)
        await asyncio.sleep(0.1)
        await self._adb.shell(
            self.serial,
            f"mkdir -p {self._defaults.photo_location}",
            check=False,
        )

        component = f"{self._defaults.package}/{self._defaults.activity}"
        await self._adb.shell(self.serial, f"am force-stop {self._defaults.package}", check=False)
        await self._adb.shell(self.serial, f"am start -n {component}", check=True)
        await asyncio.sleep(self._defaults.delays.camera_open)

        if not self._skip_zoom:
            point = self._defaults.zoom_point
            await self._adb.shell(
                self.serial,
                f"input tap {point.x} {point.y}",
                check=True,
            )
            await asyncio.sleep(self._defaults.delays.zoom)

        self.phase = CapturePhase.PREPARED

    async def capture(self) -> CaptureArtifact:
        if self.phase is not CapturePhase.PREPARED:
            raise RuntimeError("Device must be prepared before capture")

        self.phase = CapturePhase.CAPTURING
        temp_path = Path(self._tmp_file())
        try:
            await self._adb.shell(self.serial, "input keyevent KEYCODE_VOLUME_DOWN", check=True)
            total_delay = self._defaults.delays.photo_capture + self._defaults.delays.photo_save
            await asyncio.sleep(total_delay)

            remote_photo = await self._latest_photo()
            await self._adb.pull(self.serial, remote_photo, str(temp_path), check=True)
            await self._adb.shell(self.serial, f"rm -f {remote_photo}", check=False)

            image_bytes = temp_path.read_bytes()
            artifact = CaptureArtifact(
                serial=self.serial,
                position=self._position,
                image_bytes=image_bytes,
            )
            self.phase = CapturePhase.COMPLETE
            return artifact
        except Exception:
            self.phase = CapturePhase.ERROR
            raise
        finally:
            await self._cleanup(temp_path)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    async def _latest_photo(self) -> str:
        command = f"ls -t {self._defaults.photo_location}/*.jpg 2>/dev/null | head -1"
        for _ in range(20):
            output = (await self._adb.shell(self.serial, command, check=False)).strip().splitlines()
            if output:
                return output[0]
            await asyncio.sleep(0.3)
        raise ADBError("No photo captured")

    async def _cleanup(self, temp_path: Path) -> None:
        with suppress(Exception):
            await self._adb.shell(
                self.serial,
                f"am force-stop {self._defaults.package}",
                check=False,
            )
        with suppress(Exception):
            await self._adb.shell(self.serial, "input keyevent KEYCODE_POWER", check=False)
        if temp_path.exists():
            try:
                temp_path.chmod(0o600)
            except OSError:
                pass

    def _tmp_file(self) -> str:
        fd, temp_name = tempfile.mkstemp(suffix=".jpg", prefix=f"{self.serial}_")
        os.close(fd)
        return temp_name
