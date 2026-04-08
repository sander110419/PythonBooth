from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import tempfile

from ..config import AppConfig
from ..models import CameraStatus, PreflightCheckResult, PreflightReport
from ..paths import data_dir
from .canon_guidance import build_canon_access_help
from .library import SessionLibrary
from .naming import NamingContext, compile_filename


def _check_writable(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True) as handle:
            handle.write(b"pythonbooth")
            handle.flush()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _resolve_edsdk_path(config: AppConfig) -> str | None:
    try:
        from .camera_backends.edsdk import EDSDK

        if config.edsdk_path:
            return EDSDK._resolve_library_path(config.edsdk_path)
        return EDSDK._default_library_path()
    except Exception:
        return None


def run_preflight(
    *,
    config: AppConfig,
    session_library: SessionLibrary,
    camera_status: CameraStatus | None = None,
) -> PreflightReport:
    checks: list[PreflightCheckResult] = []

    session_ok, session_error = _check_writable(session_library.session_root)
    checks.append(
        PreflightCheckResult(
            name="Session Storage",
            severity="pass" if session_ok else "fail",
            message="Session folder is writable." if session_ok else "Session folder is not writable.",
            details=session_error,
        )
    )

    log_root = data_dir() / "logs"
    log_ok, log_error = _check_writable(log_root)
    checks.append(
        PreflightCheckResult(
            name="Logs",
            severity="pass" if log_ok else "fail",
            message="Diagnostics log folder is writable." if log_ok else "Diagnostics log folder is not writable.",
            details=log_error,
        )
    )

    usage = shutil.disk_usage(session_library.session_root)
    free_gb = usage.free / (1024**3)
    checks.append(
        PreflightCheckResult(
            name="Disk Space",
            severity="warn" if free_gb < 1.0 else "pass",
            message=f"{free_gb:.1f} GB free in the session location.",
            details="Free up storage before long events." if free_gb < 1.0 else "",
        )
    )

    if config.hot_folder_enabled:
        hot_path = Path(config.hot_folder_path).expanduser()
        checks.append(
            PreflightCheckResult(
                name="Hot Folder",
                severity="pass" if hot_path.exists() and hot_path.is_dir() else "fail",
                message="Hot-folder path is ready." if hot_path.exists() and hot_path.is_dir() else "Hot-folder path is missing.",
                details=str(hot_path),
            )
        )

    for raw_root in config.backup_roots:
        root = Path(raw_root).expanduser()
        writable, error = _check_writable(root)
        checks.append(
            PreflightCheckResult(
                name=f"Backup Target: {root}",
                severity="pass" if writable else "warn",
                message="Backup target is writable." if writable else "Backup target is unavailable.",
                details=error,
            )
        )

    try:
        compile_filename(
            config.naming_template,
            NamingContext(
                event_name=config.event_name,
                booth_name=config.booth_name,
                session_name=config.session_name,
                session_id=session_library.state.session_id,
            ),
        )
        checks.append(PreflightCheckResult(name="Filename Template", severity="pass", message="Filename template compiled successfully."))
    except Exception as exc:
        checks.append(
            PreflightCheckResult(
                name="Filename Template",
                severity="fail",
                message="Filename template is invalid.",
                details=str(exc),
            )
        )

    if config.backend == "canon":
        sdk_path = _resolve_edsdk_path(config)
        checks.append(
            PreflightCheckResult(
                name="Canon SDK",
                severity="pass" if sdk_path else "fail",
                message="Canon SDK library resolved." if sdk_path else "Canon SDK library could not be resolved.",
                details=sdk_path or (config.edsdk_path or "No SDK path configured."),
            )
        )
        checks.append(
            PreflightCheckResult(
                name="Canon USB Mode",
                severity="pass" if camera_status and camera_status.connected else "warn",
                message=(
                    "Canon camera is currently reachable for remote control."
                    if camera_status and camera_status.connected
                    else "Set the camera to remote-control USB mode before tethering."
                ),
                details=build_canon_access_help(),
            )
        )
        if camera_status and not camera_status.connected:
            checks.append(
                PreflightCheckResult(
                    name="Canon Camera",
                    severity="warn",
                    message="No Canon camera is currently connected.",
                    details=camera_status.message,
                )
            )
        elif camera_status and camera_status.connected:
            checks.append(PreflightCheckResult(name="Canon Camera", severity="pass", message="Canon camera is connected."))
    else:
        checks.append(PreflightCheckResult(name="Backend", severity="pass", message="Simulator backend is ready."))

    severities = {check.severity for check in checks}
    overall_status = "fail" if "fail" in severities else "warn" if "warn" in severities else "pass"
    return PreflightReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        overall_status=overall_status,
        checks=checks,
    )
