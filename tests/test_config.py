from __future__ import annotations

from pathlib import Path

import pytest

from amccs.config import CaptureDefaults, DelaySettings, Settings, ZoomPoint, load_settings


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


def test_load_settings_parses_defaults(tmp_path: Path) -> None:
    yaml_text = """
    settings:
      request_timeout_seconds: 12
      adb_command_timeout_seconds: 5
      camera_defaults:
        package: com.camera
        activity: .Main
        photo_location: /sdcard/DCIM/Camera
        zoom_point:
          x: 100
          y: 200
        delays:
          camera_open: 0.1
          zoom: 0.2
          photo_capture: 0.3
          photo_save: 0.4
    """
    config_path = _write_config(tmp_path, yaml_text)

    settings = load_settings(config_path)

    assert isinstance(settings, Settings)
    assert settings.timeout == 12
    assert settings.adb_command_timeout == 5
    assert settings.defaults == CaptureDefaults(
        package="com.camera",
        activity=".Main",
        photo_location="/sdcard/DCIM/Camera",
        zoom_point=ZoomPoint(x=100, y=200),
        delays=DelaySettings(camera_open=0.1, zoom=0.2, photo_capture=0.3, photo_save=0.4),
    )


def test_load_settings_requires_required_fields(tmp_path: Path) -> None:
    yaml_text = """
    settings:
      camera_defaults:
        activity: .Main
        photo_location: /sdcard/DCIM/Camera
        zoom_point:
          x: 0
          y: 0
        delays:
          camera_open: 0
          zoom: 0
          photo_capture: 0
          photo_save: 0
    """
    config_path = _write_config(tmp_path, yaml_text)

    with pytest.raises(ValueError, match="Field 'package'"):
        load_settings(config_path)


def test_load_settings_requires_positive_adb_timeout(tmp_path: Path) -> None:
    yaml_text = """
    settings:
      adb_command_timeout_seconds: 0
      camera_defaults:
        package: com.camera
        activity: .Main
        photo_location: /sdcard/DCIM/Camera
        zoom_point:
          x: 0
          y: 0
        delays:
          camera_open: 0
          zoom: 0
          photo_capture: 0
          photo_save: 0
    """
    config_path = _write_config(tmp_path, yaml_text)

    with pytest.raises(ValueError, match="adb_command_timeout_seconds"):
        load_settings(config_path)


def test_load_settings_rejects_unsafe_photo_location(tmp_path: Path) -> None:
    yaml_text = """
    settings:
      camera_defaults:
        package: com.camera
        activity: .Main
        photo_location: "; rm -rf /"
        zoom_point:
          x: 0
          y: 0
        delays:
          camera_open: 0
          zoom: 0
          photo_capture: 0
          photo_save: 0
    """
    config_path = _write_config(tmp_path, yaml_text)

    with pytest.raises(ValueError, match="must only contain"):
        load_settings(config_path)
