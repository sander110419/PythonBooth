from __future__ import annotations

import subprocess
import sys


def detect_likely_camera_claimers() -> list[str]:
    if not sys.platform.startswith("linux"):
        return []
    try:
        result = subprocess.run(
            ["ps", "-axo", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except Exception:
        return []

    known = (
        "gvfsd-gphoto2-volume-monitor",
        "shotwell",
        "rapid-photo-downloader",
        "digikam",
        "darktable",
        "gphoto2",
    )
    lines = result.stdout.splitlines()
    detected: list[str] = []
    for marker in known:
        if any(marker in line for line in lines):
            detected.append(marker)
    return detected


def build_canon_access_help() -> str:
    steps = [
        "On the camera, set [Choose USB connection app] to [Photo Import/Remote Control].",
        "Turn off Wi-Fi/Bluetooth connections on the camera before using USB tethering.",
        "Connect the camera directly to the computer with a data-capable USB cable, not through a hub.",
        "Close any software that may be trying to import files from the camera.",
    ]

    if sys.platform.startswith("linux"):
        detected = detect_likely_camera_claimers()
        if detected:
            steps.append(
                "Linux photo-import helpers appear to be running: "
                + ", ".join(detected)
                + ". Close them or disable auto-mount while tethering."
            )
        else:
            steps.append(
                "On Linux, desktop auto-mount helpers such as gvfs/gphoto2 can claim the camera before tethering software can."
            )
    elif sys.platform.startswith("win"):
        steps.append("On Windows, close Photos, AutoPlay/import dialogs, EOS Utility, Webcam Utility, or Explorer camera import windows.")

    return " ".join(steps)
