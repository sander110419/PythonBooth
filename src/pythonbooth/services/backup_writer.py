from __future__ import annotations

from pathlib import Path

from ..models import BackupTargetResult
from .atomic_io import atomic_copy_file


def write_backups(
    source_path: Path,
    *,
    session_relative_path: Path,
    backup_roots: list[str],
    verify: bool = True,
) -> list[BackupTargetResult]:
    results: list[BackupTargetResult] = []
    if not backup_roots:
        return results

    source_size = source_path.stat().st_size if source_path.exists() else 0
    for raw_root in backup_roots:
        root = str(raw_root or "").strip()
        if not root:
            continue
        target = Path(root).expanduser() / session_relative_path
        try:
            atomic_copy_file(source_path, target)
            verified = target.exists() and (not verify or target.stat().st_size == source_size)
            results.append(
                BackupTargetResult(
                    root=root,
                    target_path=str(target),
                    status="written" if verified else "failed",
                    verified=verified,
                    size=target.stat().st_size if target.exists() else 0,
                    last_error="" if verified else "Backup verification failed.",
                )
            )
        except Exception as exc:
            results.append(
                BackupTargetResult(
                    root=root,
                    target_path=str(target),
                    status="failed",
                    verified=False,
                    size=0,
                    last_error=str(exc),
                )
            )
    return results
