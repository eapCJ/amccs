"""Device abstractions used by the service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .adb import ADBClient


@dataclass(slots=True)
class CameraDevice:
    serial: str
    identifier: str
    position: str | None = None


PositionStrategy = Callable[[str, int], str | None]


class DeviceManager:
    """Discovers connected devices via adb."""

    def __init__(
        self,
        adb: ADBClient,
        *,
        position_strategy: PositionStrategy | None = None,
    ) -> None:
        self._adb = adb
        self._position_strategy = position_strategy or self._default_position

    async def discover(self) -> list[CameraDevice]:
        serials = await self._adb.list_devices()
        devices: list[CameraDevice] = []
        for index, serial in enumerate(serials):
            position = self._position_strategy(serial, index)
            devices.append(CameraDevice(serial=serial, identifier=serial, position=position))
        return devices

    @staticmethod
    def _default_position(_serial: str, index: int) -> str:
        return f"device_{index + 1}"
