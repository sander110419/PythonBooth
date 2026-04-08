from pathlib import Path
import zipfile

from pythonbooth.config import AppConfig
from pythonbooth.services.diagnostics import _redact_value, build_diagnostics_report, export_diagnostics_bundle
from pythonbooth.services.library import SessionLibrary


def test_diagnostics_bundle_contains_expected_files(tmp_path: Path):
    config = AppConfig(output_root=str(tmp_path))
    session = SessionLibrary(tmp_path / "session")
    bundle = export_diagnostics_bundle(tmp_path / "bundle.zip", config=config, session_library=session)

    assert bundle.exists()
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "report.json" in names
        assert "config.json" in names
        assert "session.json" in names or "session_state.json" in names


def test_diagnostics_report_redacts_sensitive_keys(tmp_path: Path):
    config = AppConfig(output_root=str(tmp_path))
    session = SessionLibrary(tmp_path / "session")

    report = build_diagnostics_report(config=config, session_library=session)
    redacted = _redact_value("config", {"api_token": "secret-value", "nested": {"password": "secret"}})

    assert report["session"]["session_id"] == session.state.session_id
    assert redacted["api_token"] == "[redacted]"
    assert redacted["nested"]["password"] == "[redacted]"
