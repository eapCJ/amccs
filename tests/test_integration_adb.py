from __future__ import annotations

import os

import pytest

from amccs.adb import ADBClient

RUN_INTEGRATION = os.getenv("AMCCS_INTEGRATION_ADB")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_INTEGRATION,
        reason="Set AMCCS_INTEGRATION_ADB=1 to run adb-backed smoke tests",
    ),
]


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - configuration guardrail
        raise ValueError(f"{name} must be an integer") from exc


@pytest.mark.asyncio
async def test_adb_smoke_round_trip() -> None:
    client = ADBClient()
    devices = await client.list_devices()

    min_devices = _int_env("AMCCS_INTEGRATION_MIN_DEVICES", 1)
    if len(devices) < min_devices:
        pytest.fail(f"Expected at least {min_devices} adb devices, found {len(devices)}")

    target = os.getenv("AMCCS_INTEGRATION_TARGET_SERIAL") or devices[0]
    command = os.getenv("AMCCS_INTEGRATION_SHELL_COMMAND", "echo amccs-integration-ok")
    output = await client.shell(target, command, check=True)

    expected = os.getenv("AMCCS_INTEGRATION_EXPECTED_OUTPUT")
    if expected:
        assert expected in output
