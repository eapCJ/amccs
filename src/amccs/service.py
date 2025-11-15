"""FastAPI integration entrypoint."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Iterable

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .adb import ADBClient, ADBError
from .config import Settings, load_settings
from .devices import DeviceManager
from .session import CaptureSession
from .state_machine import CameraStateMachine

SERVICE_NAME = "amccs"
CONFIG_ENV_VAR = "CAMERA_CONFIG_PATH"
CONFIG_SEARCH_PATHS_ENV_VAR = "CAMERA_CONFIG_SEARCH_PATHS"
DEFAULT_CONFIG_FILENAME = "config.yaml"
API_TOKEN_ENV_VAR = "CAMERA_API_TOKEN"  # noqa: S105 - env var name, not a secret
LOG_LEVEL_ENV_VAR = "AMCCS_LOG_LEVEL"
DEFAULT_CONFIG_SEARCH_PATHS: tuple[Path, ...] = (
    Path("config.yaml"),
    Path("config/config.yaml"),
    Path(__file__).resolve().parent / DEFAULT_CONFIG_FILENAME,
)

logger = logging.getLogger(SERVICE_NAME)
auth_scheme = HTTPBearer(auto_error=False)
AuthCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(auth_scheme)]


def create_app(
    *,
    config_path: str | None = None,
    adb_client: ADBClient | None = None,
    api_token: str | None = None,
    config_search_paths: Iterable[str | os.PathLike[str]] | None = None,
) -> FastAPI:
    """Instantiate the FastAPI application."""

    _configure_logging()

    state: dict[str, Any] = {
        "settings": None,
        "adb": adb_client,
        "config_path": config_path,
        "primed_machines": None,
        "api_token": api_token or os.getenv(API_TOKEN_ENV_VAR),
        "config_search_paths": tuple(config_search_paths or ()),
    }

    @asynccontextmanager
    async def _lifespan(app: FastAPI):  # pragma: no cover - exercised via tests
        resolved_path = _resolve_config_path(state["config_path"], state["config_search_paths"])
        try:
            settings = load_settings(resolved_path)
        except Exception:
            _log_event("config.load_failed", path=str(resolved_path))
            raise

        state["settings"] = settings
        state["config_path"] = str(resolved_path)
        _log_event("config.loaded", path=str(resolved_path))
        try:
            yield
        finally:
            state["settings"] = None
            _log_event("config.unloaded")

    app = FastAPI(
        title="AMCCS — Android Multi-cam Camera System",
        description="Capture synchronized photos from every connected Android device.",
        version="1.0.0",
        lifespan=_lifespan,
    )

    capture_lock = asyncio.Lock()

    def _require_settings() -> Settings:
        settings = state.get("settings")
        if settings is None:
            raise HTTPException(status_code=503, detail={"message": "Service not initialized"})
        return settings

    def _get_adb() -> ADBClient:
        adb = state.get("adb")
        if adb is None:
            settings = _require_settings()
            adb = ADBClient(command_timeout=settings.adb_command_timeout)
            state["adb"] = adb
        return adb

    async def _authorize(credentials: AuthCredentials) -> None:
        token = state.get("api_token")
        if token is None:
            return
        if credentials is None or credentials.credentials != token:
            raise HTTPException(status_code=401, detail={"message": "Invalid or missing API token"})

    def _build_session() -> CaptureSession:
        settings = _require_settings()
        adb = _get_adb()
        device_manager = DeviceManager(adb)

        def factory(device):
            return CameraStateMachine(
                serial=device.serial,
                adb=adb,
                defaults=settings.defaults,
                position=device.position,
            )

        return CaptureSession(device_manager=device_manager, state_machine_factory=factory)

    @app.get("/")
    async def root() -> dict[str, Any]:
        settings = state.get("settings")
        return {
            "service": SERVICE_NAME,
            "version": app.version,
            "config_path": state.get("config_path"),
            "timeout": settings.timeout if settings else None,
            "auth_enabled": bool(state.get("api_token")),
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        adb = _get_adb()
        device_manager = DeviceManager(adb)
        devices = await device_manager.discover()

        statuses: list[dict[str, Any]] = []
        overall_ok = bool(devices)
        for device in devices:
            ok = True
            issues: list[str] = []
            try:
                await adb.shell(device.serial, "echo ok", check=True)
            except Exception as exc:  # noqa: BLE001
                ok = False
                overall_ok = False
                issues.append(str(exc))
            statuses.append(
                {
                    "device_id": device.identifier,
                    "serial": device.serial,
                    "position": device.position,
                    "ok": ok,
                    "issues": issues,
                }
            )

        status_text = "healthy" if overall_ok else ("no-devices" if not devices else "issues")
        _log_event("health.reported", status=status_text, devices=len(devices))
        return {"service": SERVICE_NAME, "status": status_text, "devices": statuses}

    @app.post("/prime")
    async def prime(_: None = Depends(_authorize)) -> dict[str, Any]:
        session = _build_session()

        async with capture_lock:
            try:
                _log_event("prime.start")
                machines = await session.prepare_all()
            except ADBError as exc:
                _log_event("prime.failed", reason=str(exc))
                raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
            except RuntimeError as exc:
                _log_event("prime.failed", reason=str(exc))
                raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
            state["primed_machines"] = machines

        _log_event("prime.success", devices=len(machines))
        return {"service": SERVICE_NAME, "primed_devices": len(machines)}

    @app.post("/capture")
    async def capture(_: None = Depends(_authorize)) -> dict[str, Any]:
        session = _build_session()
        settings = _require_settings()

        async with capture_lock:
            primed = state.get("primed_machines")
            try:
                _log_event("capture.start", primed=bool(primed))
                artifacts = await asyncio.wait_for(
                    session.capture_all(machines=primed),
                    timeout=settings.timeout,
                )
            except asyncio.TimeoutError as exc:  # pragma: no cover - network boundary
                _log_event("capture.failed", reason="timeout")
                raise HTTPException(
                    status_code=504,
                    detail={"message": "Capture timed out"},
                ) from exc
            except ADBError as exc:
                _log_event("capture.failed", reason=str(exc))
                raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
            except RuntimeError as exc:
                _log_event("capture.failed", reason=str(exc))
                raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
            finally:
                state["primed_machines"] = None

        payload: list[dict[str, Any]] = []
        for artifact in artifacts:
            encoded = base64.b64encode(artifact.image_bytes).decode("ascii")
            payload.append(
                {
                    "device_id": artifact.serial,
                    "position": artifact.position,
                    "image_base64": encoded,
                }
            )

        _log_event("capture.success", devices=len(payload))
        return {"service": SERVICE_NAME, "count": len(payload), "devices": payload}

    return app


def _resolve_config_path(
    override: str | None = None,
    extra_search_paths: Iterable[str | os.PathLike[str]] | None = None,
) -> Path:
    candidate = override or os.getenv(CONFIG_ENV_VAR)
    if candidate:
        path = _normalize_path(candidate)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found at {path}")
        return path

    search_candidates: list[Path] = []
    env_search = os.getenv(CONFIG_SEARCH_PATHS_ENV_VAR)
    if env_search:
        for raw in env_search.split(os.pathsep):
            cleaned = raw.strip()
            if cleaned:
                search_candidates.append(Path(cleaned))

    if extra_search_paths:
        for configured in extra_search_paths:
            search_candidates.append(Path(str(configured)))

    search_candidates.extend(DEFAULT_CONFIG_SEARCH_PATHS)

    evaluated_paths: list[Path] = []
    for candidate_path in search_candidates:
        path = _normalize_path(candidate_path)
        evaluated_paths.append(path)
        if path.exists():
            return path

    searched = ", ".join(str(p) for p in evaluated_paths)
    raise FileNotFoundError(
        (
            "Unable to locate configuration file. Set "
            f"{CONFIG_ENV_VAR} or place config.yaml in one of: {searched}"
        )
    )


def _normalize_path(candidate: str | os.PathLike[str]) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _configure_logging() -> None:
    level_name = os.getenv(LOG_LEVEL_ENV_VAR, "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(message)s")


def _log_event(event: str, **fields: Any) -> None:
    record = {"event": event, "service": SERVICE_NAME, **fields}
    logger.info(json.dumps(record, sort_keys=True))
