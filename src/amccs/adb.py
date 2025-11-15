"""Thin async wrappers around adb commands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


class ADBError(RuntimeError):
    """Raised when adb returns a non-zero status."""


@dataclass(slots=True)
class ADBClient:
    """Asynchronous helper for invoking adb commands."""

    executable: str = "adb"
    command_timeout: float | None = 15.0

    async def list_devices(self) -> list[str]:
        stdout, _, _ = await self._exec("devices")
        devices: list[str] = []
        for line in stdout.splitlines():
            if not line or line.startswith("List of devices"):
                continue
            serial, *rest = line.split()
            if rest and rest[0] == "device":
                devices.append(serial)
        return devices

    async def shell(self, serial: str, command: str, *, check: bool = True) -> str:
        stdout, _, _ = await self._exec("-s", serial, "shell", command, check=check)
        return stdout

    async def pull(self, serial: str, remote: str, local: str, *, check: bool = True) -> None:
        await self._exec("-s", serial, "pull", remote, local, check=check)

    async def _exec(self, *args: str, check: bool = True) -> tuple[str, str, int]:
        process = await asyncio.create_subprocess_exec(
            self.executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            if self.command_timeout is None:
                stdout_bytes, stderr_bytes = await process.communicate()
            else:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.command_timeout,
                )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ADBError(f"adb {' '.join(args)} timed out after {self.command_timeout}s") from exc
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = int(process.returncode or 0)
        if check and returncode != 0:
            rendered_args = " ".join(args)
            details = stderr.strip() or "no stderr output"
            raise ADBError(f"adb {rendered_args} exited with {returncode}: {details}")
        return stdout, stderr, returncode
