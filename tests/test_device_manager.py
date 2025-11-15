from __future__ import annotations

import asyncio

import pytest

from amccs.adb import ADBClient
from amccs.devices import CameraDevice, DeviceManager


class StubADB(ADBClient):
    __slots__ = ("calls", "serials")

    def __init__(self, serials: list[str]) -> None:
        super().__init__()
        self.serials = serials
        self.calls: list[str] = []

    async def list_devices(self) -> list[str]:
        self.calls.append("list_devices")
        await asyncio.sleep(0)
        return self.serials


@pytest.mark.asyncio
async def test_discover_returns_all_adb_devices() -> None:
    adb = StubADB(["ZX1", "192.168.0.5:5555"])
    manager = DeviceManager(adb)

    devices = await manager.discover()

    assert [device.serial for device in devices] == adb.serials
    assert all(isinstance(device, CameraDevice) for device in devices)
    assert adb.calls.count("list_devices") == 1
