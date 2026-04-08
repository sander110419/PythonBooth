from pathlib import Path

from pythonbooth.config import AppConfig
from pythonbooth.models import CameraStatus
from pythonbooth.services.library import SessionLibrary
from pythonbooth.services.preflight import run_preflight


def test_preflight_passes_for_simulator_defaults(tmp_path: Path):
    config = AppConfig(backend="simulator", output_root=str(tmp_path))
    session = SessionLibrary(tmp_path / "session")

    report = run_preflight(config=config, session_library=session, camera_status=CameraStatus.idle("simulator"))

    assert report.overall_status in {"pass", "warn"}
    assert any(check.name == "Filename Template" and check.severity == "pass" for check in report.checks)


def test_preflight_fails_with_missing_hot_folder_and_sdk(tmp_path: Path):
    config = AppConfig(
        backend="canon",
        output_root=str(tmp_path),
        hot_folder_enabled=True,
        hot_folder_path=str(tmp_path / "missing-hot-folder"),
        edsdk_path=str(tmp_path / "missing-sdk"),
    )
    session = SessionLibrary(tmp_path / "session")

    report = run_preflight(config=config, session_library=session, camera_status=CameraStatus.idle("canon"))

    severities = {check.name: check.severity for check in report.checks}
    assert severities["Hot Folder"] == "fail"
    assert severities["Canon SDK"] == "fail"
    assert severities["Canon USB Mode"] == "warn"


def test_preflight_warns_for_unavailable_backup_root(tmp_path: Path, monkeypatch):
    config = AppConfig(backend="simulator", output_root=str(tmp_path), backup_roots=[str(tmp_path / "backup")])
    session = SessionLibrary(tmp_path / "session")

    monkeypatch.setattr("pythonbooth.services.preflight._check_writable", lambda _path: (False, "permission denied"))

    report = run_preflight(config=config, session_library=session, camera_status=CameraStatus.idle("simulator"))

    assert any(check.name.startswith("Backup Target:") and check.severity == "warn" for check in report.checks)
