from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import sys
from typing import Any
import zipfile

from ..config import AppConfig
from ..models import CameraStatus, PreflightReport
from ..paths import data_dir
from .atomic_io import _json_default
from .library import SessionLibrary


def _package_version() -> str:
    try:
        return version("pythonbooth")
    except PackageNotFoundError:
        return "0.1.0"


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("password", "token", "secret", "apikey", "api_key")):
        return "[redacted]"
    if isinstance(value, dict):
        return {child_key: _redact_value(child_key, child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _serialise(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def build_diagnostics_report(
    *,
    config: AppConfig,
    session_library: SessionLibrary,
    camera_status: CameraStatus | None = None,
    preflight_report: PreflightReport | None = None,
) -> dict[str, Any]:
    log_root = data_dir() / "logs"
    backups: list[dict[str, Any]] = []
    for raw_root in config.backup_roots:
        root = Path(raw_root).expanduser()
        try:
            usage = root.exists() and root.is_dir()
            disk = root.stat() if usage else None
            backups.append(
                {
                    "root": str(root),
                    "exists": root.exists(),
                    "is_dir": root.is_dir(),
                    "writable": root.exists() and root.is_dir(),
                    "size_hint": disk.st_size if disk else 0,
                }
            )
        except Exception as exc:
            backups.append({"root": str(root), "exists": root.exists(), "error": str(exc)})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "application": {
            "name": "PythonBooth",
            "version": _package_version(),
            "python": sys.version,
            "platform": platform.platform(),
        },
        "config": _redact_value("config", asdict(config)),
        "camera_status": _serialise(camera_status) if camera_status else session_library.state.last_camera_status,
        "session": {
            "session_id": session_library.state.session_id,
            "session_root": str(session_library.session_root),
            "photo_count": len(session_library.records),
            "job_count": len(session_library.jobs),
            "active_jobs": list(session_library.state.active_job_ids),
            "needs_recovery": session_library.state.needs_recovery,
            "last_error": session_library.state.last_error,
        },
        "backup_roots": backups,
        "log_files": [path.name for path in sorted(log_root.glob("*.log*"))],
        "preflight_report": _serialise(preflight_report) if preflight_report else None,
    }


def export_diagnostics_bundle(
    destination: Path,
    *,
    config: AppConfig,
    session_library: SessionLibrary,
    camera_status: CameraStatus | None = None,
    preflight_report: PreflightReport | None = None,
) -> Path:
    destination = destination.expanduser()
    if destination.suffix.lower() != ".zip":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / f"pythonbooth_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)

    report = build_diagnostics_report(
        config=config,
        session_library=session_library,
        camera_status=camera_status,
        preflight_report=preflight_report,
    )

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("report.json", json.dumps(report, indent=2, default=_json_default))
        bundle.writestr("config.json", json.dumps(_redact_value("config", asdict(config)), indent=2, default=_json_default))
        for maybe_file in (
            session_library.index_path,
            session_library.state_path,
            session_library.jobs_path,
        ):
            if maybe_file.exists():
                bundle.write(maybe_file, arcname=maybe_file.name)

        log_root = data_dir() / "logs"
        for log_file in sorted(log_root.glob("*.log*")):
            bundle.write(log_file, arcname=f"logs/{log_file.name}")

    return destination
