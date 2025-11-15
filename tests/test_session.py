from __future__ import annotations

import asyncio

import pytest

from amccs.devices import CameraDevice
from amccs.session import CaptureSession
from amccs.state_machine import CaptureArtifact


class StubDeviceManager:
    def __init__(self, devices: list[CameraDevice]) -> None:
        self.devices = devices
        self.calls: list[str] = []

    async def discover(self) -> list[CameraDevice]:
        self.calls.append("discover")
        await asyncio.sleep(0)
        return self.devices


class StubStateMachine:
    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.events: list[str] = []

    async def prepare(self) -> None:
        self.events.append("prepare")
        await asyncio.sleep(0)

    async def capture(self) -> CaptureArtifact:
        self.events.append("capture")
        await asyncio.sleep(0)
        return CaptureArtifact(serial=self.serial, position=None, image_bytes=b"data")


@pytest.mark.asyncio
async def test_capture_all_discovers_when_not_primed() -> None:
    devices = [
        CameraDevice(serial="A", identifier="cam-A"),
        CameraDevice(serial="B", identifier="cam-B"),
    ]
    manager = StubDeviceManager(devices)

    machines: dict[str, StubStateMachine] = {}

    def factory(device: CameraDevice) -> StubStateMachine:
        machine = StubStateMachine(serial=device.serial)
        machines[device.serial] = machine
        return machine

    session = CaptureSession(device_manager=manager, state_machine_factory=factory)

    artifacts = await session.capture_all()

    assert manager.calls == ["discover"]
    assert all(machine.events == ["prepare", "capture"] for machine in machines.values())
    assert sorted(artifact.serial for artifact in artifacts) == ["A", "B"]


@pytest.mark.asyncio
async def test_capture_all_uses_prepared_machines() -> None:
    devices = [CameraDevice(serial="A", identifier="cam-A")]
    manager = StubDeviceManager(devices)

    created: list[StubStateMachine] = []

    def factory(device: CameraDevice) -> StubStateMachine:
        machine = StubStateMachine(serial=device.serial)
        created.append(machine)
        return machine

    session = CaptureSession(device_manager=manager, state_machine_factory=factory)

    machines = await session.prepare_all()
    assert manager.calls == ["discover"]
    assert created[0].events == ["prepare"]

    manager.calls.clear()

    artifacts = await session.capture_all(machines=machines)

    assert manager.calls == []  # no rediscovery when machines provided
    assert created[0].events == ["prepare", "capture"]
    assert [artifact.serial for artifact in artifacts] == ["A"]
