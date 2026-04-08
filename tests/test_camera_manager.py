from __future__ import annotations

from collections import deque

from pythonbooth.models import CameraStatus
from pythonbooth.services.camera_backends.base import CameraBackend, RecoverableCameraError
from pythonbooth.services.camera_manager import CameraManager


class FakeBackend(CameraBackend):
    def __init__(self, connect_results: list[bool], poll_plan: list[object]):
        super().__init__()
        self.connect_results = deque(connect_results)
        self.poll_plan = deque(poll_plan)
        self.disconnect_count = 0

    def connect(self) -> CameraStatus:
        connected = self.connect_results.popleft() if self.connect_results else True
        self._connected = connected
        return CameraStatus(
            backend="fake",
            connected=connected,
            state="connected" if connected else "disconnected",
            message="connected" if connected else "not connected",
        )

    def disconnect(self) -> None:
        self.disconnect_count += 1
        self._connected = False

    def status(self) -> CameraStatus:
        return CameraStatus(backend="fake", connected=self._connected, state="connected" if self._connected else "idle", message="status")

    def poll_captures(self):
        if not self.poll_plan:
            return []
        item = self.poll_plan.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    def request_capture(self) -> None:
        return None


def test_camera_manager_retries_connect_with_backoff():
    backend = FakeBackend(connect_results=[False, True], poll_plan=[[]])
    manager = CameraManager(backend_name="fake", backend_factory=lambda _name: backend)
    manager._build_backend()

    manager._attempt_connect(10.0)
    assert manager.current_status.state == "retrying"
    assert manager.current_status.retry_in_seconds >= 1.0

    manager._attempt_connect(12.0)
    assert manager.current_status.state == "connected"
    assert manager.current_status.reconnect_attempts == 0


def test_camera_manager_resets_backend_after_repeated_poll_failures():
    backend = FakeBackend(connect_results=[True], poll_plan=[RecoverableCameraError("usb"), RecoverableCameraError("usb"), RecoverableCameraError("usb")])
    manager = CameraManager(backend_name="fake", backend_factory=lambda _name: backend)
    manager._build_backend()
    manager._attempt_connect(0.0)

    manager._poll_backend(1.0)
    manager._poll_backend(2.0)
    manager._poll_backend(3.0)

    assert backend.disconnect_count == 1
    assert manager.current_status.state == "retrying"
    assert manager.current_status.recoverable is True


def test_camera_manager_successful_poll_clears_degraded_state():
    backend = FakeBackend(connect_results=[True], poll_plan=[RecoverableCameraError("transient"), []])
    manager = CameraManager(backend_name="fake", backend_factory=lambda _name: backend)
    manager._build_backend()
    manager._attempt_connect(0.0)

    manager._poll_backend(1.0)
    assert manager.current_status.state == "degraded"

    manager._poll_backend(2.0)
    assert manager.current_status.state == "connected"
