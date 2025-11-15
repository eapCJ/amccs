"""Capture session orchestration."""

from __future__ import annotations

import asyncio
from typing import Callable, Iterable, Protocol

from .devices import CameraDevice
from .state_machine import CaptureArtifact


class DeviceManagerProtocol(Protocol):
    async def discover(self) -> list[CameraDevice]:
        ...


class StateMachineProtocol(Protocol):
    async def prepare(self) -> None:
        ...

    async def capture(self) -> CaptureArtifact:
        ...


StateMachineFactory = Callable[[CameraDevice], StateMachineProtocol]


class CaptureSession:
    """Orchestrates multi-device capture via the two-phase workflow."""

    def __init__(
        self,
        *,
        device_manager: DeviceManagerProtocol,
        state_machine_factory: StateMachineFactory,
    ) -> None:
        self._device_manager = device_manager
        self._state_machine_factory = state_machine_factory

    async def prepare_all(self) -> list[StateMachineProtocol]:
        devices = await self._device_manager.discover()
        if not devices:
            raise RuntimeError("No ADB devices detected")

        machines = [self._state_machine_factory(device) for device in devices]
        await asyncio.gather(*(machine.prepare() for machine in machines))
        return machines

    async def capture_all(
        self,
        machines: Iterable[StateMachineProtocol] | None = None,
    ) -> list[CaptureArtifact]:
        if machines is None:
            machines = await self.prepare_all()

        artifacts = await asyncio.gather(*(machine.capture() for machine in machines))
        return list(artifacts)
