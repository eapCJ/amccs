"""Configuration loading helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SAFE_REMOTE_PATH_PATTERN = re.compile(r"^[\w./-]+$")


@dataclass(slots=True, frozen=True)
class ZoomPoint:
    x: int
    y: int


@dataclass(slots=True, frozen=True)
class DelaySettings:
    camera_open: float
    zoom: float
    photo_capture: float
    photo_save: float


@dataclass(slots=True, frozen=True)
class CaptureDefaults:
    package: str
    activity: str
    photo_location: str
    zoom_point: ZoomPoint
    delays: DelaySettings


@dataclass(slots=True, frozen=True)
class Settings:
    defaults: CaptureDefaults
    timeout: float
    adb_command_timeout: float


def load_settings(path: Path) -> Settings:
    """Load configuration from a YAML document."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings_raw = raw.get("settings") or {}
    defaults_raw = settings_raw.get("camera_defaults") or {}
    zoom_raw = defaults_raw.get("zoom_point") or {}
    delays_raw = defaults_raw.get("delays") or {}

    defaults = CaptureDefaults(
        package=_require_str(defaults_raw, "package"),
        activity=_require_str(defaults_raw, "activity"),
        photo_location=_require_safe_remote_path(defaults_raw, "photo_location"),
        zoom_point=ZoomPoint(
            x=_require_int(zoom_raw, "x"),
            y=_require_int(zoom_raw, "y"),
        ),
        delays=DelaySettings(
            camera_open=_require_float(delays_raw, "camera_open"),
            zoom=_require_float(delays_raw, "zoom"),
            photo_capture=_require_float(delays_raw, "photo_capture"),
            photo_save=_require_float(delays_raw, "photo_save"),
        ),
    )

    timeout = float(settings_raw.get("request_timeout_seconds", 30))
    if timeout <= 0:
        raise ValueError("settings.request_timeout_seconds must be > 0")

    adb_timeout = float(settings_raw.get("adb_command_timeout_seconds", 15))
    if adb_timeout <= 0:
        raise ValueError("settings.adb_command_timeout_seconds must be > 0")

    return Settings(defaults=defaults, timeout=timeout, adb_command_timeout=adb_timeout)


def _require_str(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{key}' must be a non-empty string")
    return value.strip()


def _require_int(source: dict[str, Any], key: str) -> int:
    value = source.get(key)
    if value is None:
        raise ValueError(f"Field '{key}' must be provided")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{key}' must be an integer") from exc


def _require_float(source: dict[str, Any], key: str) -> float:
    value = source.get(key)
    if value is None:
        raise ValueError(f"Field '{key}' must be provided")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field '{key}' must be numeric") from exc


def _require_safe_remote_path(source: dict[str, Any], key: str) -> str:
    value = _require_str(source, key)
    if not SAFE_REMOTE_PATH_PATTERN.fullmatch(value):
        raise ValueError(
            (
                f"Field '{key}' must only contain letters, numbers, dots, slashes, "
                "underscores, or hyphens"
            )
        )
    if ".." in value.split("/"):
        raise ValueError(f"Field '{key}' must not contain parent directory segments")
    if value.startswith("-"):
        raise ValueError(f"Field '{key}' cannot start with '-'")
    return value
