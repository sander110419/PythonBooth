from __future__ import annotations

import logging
import time
from queue import Empty, Queue
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..models import CapturePayload, CameraStatus
from .camera_backends import CanonCameraBackend, SimulatedCameraBackend
from .camera_backends.base import CameraBackend, FatalCameraError, RecoverableCameraError

logger = logging.getLogger(__name__)

BackendFactory = Callable[[str], CameraBackend]


class CameraManager(QThread):
    status_updated = pyqtSignal(object)
    capture_ready = pyqtSignal(object)

    def __init__(
        self,
        backend_name: str = "simulator",
        *,
        auto_reconnect: bool = True,
        simulator_auto_capture_seconds: float = 0.0,
        edsdk_path: str = "",
        backend_factory: BackendFactory | None = None,
    ) -> None:
        super().__init__()
        self._selected_backend = backend_name or "simulator"
        self._auto_reconnect = bool(auto_reconnect)
        self._simulator_auto_capture_seconds = float(simulator_auto_capture_seconds)
        self._edsdk_path = edsdk_path
        self._backend_factory = backend_factory or self._default_backend_factory
        self._commands: Queue[tuple[str, object | None]] = Queue()
        self._backend: CameraBackend | None = None
        self._stop_requested = False
        self._next_connect_at = 0.0
        self._next_retry_delay_s = 1.0
        self._reconnect_attempts = 0
        self._consecutive_poll_failures = 0
        self._poll_failure_threshold = 3
        self._last_status = CameraStatus.idle(self._selected_backend, f"{self._selected_backend.title()} ready")
        self._last_successful_poll_at = 0.0

    @property
    def current_status(self) -> CameraStatus:
        return self._last_status

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
        self._emit_status(CameraStatus.idle(self._selected_backend, f"{self._selected_backend.title()} ready"))

        while not self._stop_requested:
            self._process_commands()
            now = time.monotonic()
            self._ensure_connected(now)
            self._poll_backend(now)
            self.msleep(35)

        if self._backend is not None:
            try:
                self._backend.disconnect()
            except Exception:
                logger.exception("Error disconnecting backend during shutdown")

    def _default_backend_factory(self, backend_name: str) -> CameraBackend:
        if backend_name == "canon":
            return CanonCameraBackend(self._edsdk_path or None)
        return SimulatedCameraBackend(auto_capture_seconds=self._simulator_auto_capture_seconds)

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
                self._reconnect_attempts = 0
                self._next_retry_delay_s = 1.0
                self._next_connect_at = 0.0
                self._recreate_backend()
                continue
            if command == "capture":
                if self._backend is not None and self._backend.connected:
                    try:
                        self._backend.request_capture()
                    except Exception as exc:
                        logger.exception("Capture request failed")
                        self._emit_status(
                            CameraStatus(
                                backend=self._selected_backend,
                                connected=False,
                                state="error",
                                message="Capture request failed",
                                last_error=str(exc),
                                recoverable=True,
                            )
                        )
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
        self._backend = self._backend_factory(self._selected_backend)

    def _recreate_backend(self) -> None:
        if self._backend is not None:
            try:
                self._backend.disconnect()
            except Exception:
                logger.exception("Error disconnecting previous backend")
        self._build_backend()
        self._consecutive_poll_failures = 0
        self._next_connect_at = 0.0
        self._next_retry_delay_s = 1.0
        self._emit_status(CameraStatus.idle(self._selected_backend, f"{self._selected_backend.title()} selected"))

    def _ensure_connected(self, now: float) -> None:
        if self._backend is None or self._backend.connected:
            return
        if not self._auto_reconnect and self._reconnect_attempts > 0:
            return
        if now < self._next_connect_at:
            return
        self._attempt_connect(now)

    def _attempt_connect(self, now: float) -> None:
        if self._backend is None:
            return
        if self._reconnect_attempts > 0:
            self._emit_status(
                CameraStatus(
                    backend=self._selected_backend,
                    connected=False,
                    state="retrying",
                    message="Retrying camera connection",
                    retry_in_seconds=0.0,
                    reconnect_attempts=self._reconnect_attempts,
                    recoverable=True,
                )
            )
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
                recoverable=True,
            )

        if status.connected:
            self._reconnect_attempts = 0
            self._consecutive_poll_failures = 0
            self._next_connect_at = 0.0
            self._next_retry_delay_s = 1.0
            self._last_successful_poll_at = now
            status.reconnect_attempts = 0
            self._emit_status(status)
            return

        self._reconnect_attempts += 1
        delay = self._schedule_retry(now)
        status.state = "retrying" if self._auto_reconnect else status.state
        status.message = f"{status.message}. Retrying in {int(round(delay))}s" if self._auto_reconnect else status.message
        status.retry_in_seconds = delay
        status.reconnect_attempts = self._reconnect_attempts
        status.recoverable = True
        self._emit_status(status)

    def _poll_backend(self, now: float) -> None:
        if self._backend is None or not self._backend.connected:
            return
        try:
            captures = list(self._backend.poll_captures())
        except RecoverableCameraError as exc:
            self._handle_poll_failure(now, exc, recoverable=True)
            return
        except FatalCameraError as exc:
            self._handle_poll_failure(now, exc, recoverable=False)
            return
        except Exception as exc:
            logger.exception("Polling captures failed")
            self._handle_poll_failure(now, exc, recoverable=True)
            return

        self._consecutive_poll_failures = 0
        self._last_successful_poll_at = now
        if self._last_status.state != "connected":
            self._emit_status(self._backend.status())
        for capture in captures:
            if isinstance(capture, CapturePayload):
                self.capture_ready.emit(capture)

    def _handle_poll_failure(self, now: float, exc: Exception, *, recoverable: bool) -> None:
        self._consecutive_poll_failures += 1
        should_reset = (
            not recoverable
            or self._consecutive_poll_failures >= self._poll_failure_threshold
            or (self._backend is not None and not self._backend.is_healthy())
        )
        if should_reset:
            if self._backend is not None:
                try:
                    self._backend.disconnect()
                except Exception:
                    logger.exception("Backend disconnect after poll failure failed")
            self._reconnect_attempts += 1
            delay = self._schedule_retry(now)
            self._emit_status(
                CameraStatus(
                    backend=self._selected_backend,
                    connected=False,
                    state="retrying" if recoverable else "error",
                    message=f"Camera session lost. Retrying in {int(round(delay))}s" if recoverable else "Camera session failed",
                    last_error=str(exc),
                    retry_in_seconds=delay if recoverable else 0.0,
                    reconnect_attempts=self._reconnect_attempts,
                    recoverable=recoverable,
                )
            )
            self._consecutive_poll_failures = 0
            return

        self._emit_status(
            CameraStatus(
                backend=self._selected_backend,
                connected=True,
                state="degraded",
                message=f"Camera poll hiccup ({self._consecutive_poll_failures}/{self._poll_failure_threshold})",
                last_error=str(exc),
                reconnect_attempts=self._reconnect_attempts,
                recoverable=True,
            )
        )

    def _schedule_retry(self, now: float) -> float:
        delay = max(1.0, min(30.0, self._next_retry_delay_s))
        self._next_connect_at = now + delay
        self._next_retry_delay_s = min(30.0, delay * 2.0)
        return delay

    def _emit_status(self, status: CameraStatus) -> None:
        self._last_status = status
        self.status_updated.emit(status)
