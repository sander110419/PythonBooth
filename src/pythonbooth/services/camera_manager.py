from __future__ import annotations

import logging
import time
from queue import Empty, Queue

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from ..models import CapturePayload, CameraStatus
from .camera_backends import CanonCameraBackend, SimulatedCameraBackend
from .image_utils import qimage_from_bgr

logger = logging.getLogger(__name__)


class CameraManager(QThread):
    preview_updated = pyqtSignal(QImage)
    status_updated = pyqtSignal(object)
    capture_ready = pyqtSignal(object)

    def __init__(
        self,
        backend_name: str = "simulator",
        *,
        auto_reconnect: bool = True,
        simulator_auto_capture_seconds: float = 0.0,
        edsdk_path: str = "",
    ) -> None:
        super().__init__()
        self._selected_backend = backend_name or "simulator"
        self._auto_reconnect = bool(auto_reconnect)
        self._simulator_auto_capture_seconds = float(simulator_auto_capture_seconds)
        self._edsdk_path = edsdk_path
        self._commands: Queue[tuple[str, object | None]] = Queue()
        self._backend = None
        self._stop_requested = False
        self._next_connect_at = 0.0
        self._next_preview_at = 0.0

    @staticmethod
    def backend_options() -> list[tuple[str, str]]:
        return [
            ("canon", "Canon EDSDK"),
            ("simulator", "Simulator"),
        ]

    def switch_backend(self, backend_name: str) -> None:
        self._commands.put(("switch_backend", backend_name))

    def request_reconnect(self) -> None:
        self._commands.put(("reconnect", None))

    def request_capture(self) -> None:
        self._commands.put(("capture", None))

    def update_runtime_options(self, *, auto_reconnect: bool | None = None, simulator_auto_capture_seconds: float | None = None, edsdk_path: str | None = None) -> None:
        self._commands.put(
            (
                "update_options",
                {
                    "auto_reconnect": auto_reconnect,
                    "simulator_auto_capture_seconds": simulator_auto_capture_seconds,
                    "edsdk_path": edsdk_path,
                },
            )
        )

    def stop(self) -> None:
        self._stop_requested = True
        self._commands.put(("stop", None))
        self.wait(3000)

    def run(self) -> None:
        self._build_backend()
        self.status_updated.emit(CameraStatus.idle(self._selected_backend, f"{self._selected_backend.title()} ready"))

        while not self._stop_requested:
            self._process_commands()
            now = time.monotonic()

            if self._backend is not None and not getattr(self._backend, "connected", False):
                if self._auto_reconnect and now >= self._next_connect_at:
                    self._attempt_connect()
                    self._next_connect_at = now + (1.0 if getattr(self._backend, "connected", False) else 3.0)

            if self._backend is not None and getattr(self._backend, "connected", False):
                self._emit_captures()
                if now >= self._next_preview_at:
                    self._emit_preview()
                    self._next_preview_at = now + 0.1

            self.msleep(35)

        if self._backend is not None:
            try:
                self._backend.disconnect()
            except Exception:
                logger.exception("Error disconnecting backend during shutdown")

    def _process_commands(self) -> None:
        while True:
            try:
                command, payload = self._commands.get_nowait()
            except Empty:
                return

            if command == "stop":
                self._stop_requested = True
                return
            if command == "switch_backend":
                self._selected_backend = str(payload or "simulator")
                self._recreate_backend()
                continue
            if command == "reconnect":
                self._recreate_backend()
                self._attempt_connect()
                continue
            if command == "capture":
                if self._backend is not None:
                    try:
                        self._backend.request_capture()
                    except Exception:
                        logger.exception("Capture request failed")
                continue
            if command == "update_options":
                assert isinstance(payload, dict)
                if payload.get("auto_reconnect") is not None:
                    self._auto_reconnect = bool(payload["auto_reconnect"])
                if payload.get("simulator_auto_capture_seconds") is not None:
                    self._simulator_auto_capture_seconds = float(payload["simulator_auto_capture_seconds"])
                if payload.get("edsdk_path") is not None:
                    self._edsdk_path = str(payload["edsdk_path"] or "")
                self._recreate_backend()

    def _build_backend(self) -> None:
        if self._selected_backend == "canon":
            self._backend = CanonCameraBackend(self._edsdk_path or None)
        else:
            self._backend = SimulatedCameraBackend(auto_capture_seconds=self._simulator_auto_capture_seconds)

    def _recreate_backend(self) -> None:
        if self._backend is not None:
            try:
                self._backend.disconnect()
            except Exception:
                logger.exception("Error disconnecting previous backend")
        self._build_backend()
        self.status_updated.emit(CameraStatus.idle(self._selected_backend, f"{self._selected_backend.title()} selected"))
        self._next_connect_at = 0.0

    def _attempt_connect(self) -> None:
        if self._backend is None:
            return
        try:
            status = self._backend.connect()
        except Exception as exc:
            logger.exception("Backend connect crashed")
            status = CameraStatus(
                backend=self._selected_backend,
                connected=False,
                state="error",
                message="Camera connection crashed",
                last_error=str(exc),
            )
        self.status_updated.emit(status)

    def _emit_preview(self) -> None:
        if self._backend is None:
            return
        try:
            frame = self._backend.get_preview_frame()
        except Exception:
            logger.exception("Preview retrieval failed")
            return
        if frame is None:
            return
        qimage = qimage_from_bgr(frame)
        if qimage is not None:
            self.preview_updated.emit(qimage)

    def _emit_captures(self) -> None:
        if self._backend is None:
            return
        try:
            captures = list(self._backend.poll_captures())
        except Exception:
            logger.exception("Polling captures failed")
            return
        for capture in captures:
            if isinstance(capture, CapturePayload):
                self.capture_ready.emit(capture)
