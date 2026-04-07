from __future__ import annotations

from datetime import datetime
from queue import SimpleQueue

import cv2
import numpy as np

from ...models import CapturePayload, CameraStatus
from ..image_utils import encode_bgr_to_jpeg
from .base import CameraBackend


class SimulatedCameraBackend(CameraBackend):
    backend_id = "simulator"
    display_name = "Simulator"

    def __init__(self, auto_capture_seconds: float = 0.0):
        super().__init__()
        self._captures: SimpleQueue[CapturePayload] = SimpleQueue()
        self._camera_sequence = 1000
        self._frame_index = 0
        self._auto_capture_seconds = max(0.0, float(auto_capture_seconds))
        self._last_auto_capture = datetime.now()

    def connect(self) -> CameraStatus:
        self._connected = True
        return self.status()

    def disconnect(self) -> None:
        self._connected = False

    def status(self) -> CameraStatus:
        return CameraStatus(
            backend=self.backend_id,
            connected=self._connected,
            state="connected" if self._connected else "idle",
            message="Simulator polling for captures" if self._connected else "Simulator offline",
            camera_name="PythonBooth Simulator",
        )

    def poll_captures(self) -> list[CapturePayload]:
        self._maybe_auto_capture()
        captures: list[CapturePayload] = []
        while not self._captures.empty():
            captures.append(self._captures.get_nowait())
        return captures

    def request_capture(self) -> None:
        if not self._connected:
            return
        self._enqueue_capture(auto_capture=False)

    def _maybe_auto_capture(self) -> None:
        if self._auto_capture_seconds <= 0:
            return
        now = datetime.now()
        if (now - self._last_auto_capture).total_seconds() < self._auto_capture_seconds:
            return
        self._last_auto_capture = now
        self._enqueue_capture(auto_capture=True)

    def _enqueue_capture(self, *, auto_capture: bool) -> None:
        self._camera_sequence += 1
        photo = self._build_photo(self._camera_sequence)
        jpeg = encode_bgr_to_jpeg(photo, quality=96)
        if jpeg is None:
            return
        self._captures.put(
            CapturePayload(
                data=jpeg,
                original_filename=f"SIM_{self._camera_sequence:05d}.JPG",
                source=self.backend_id,
                camera_sequence=self._camera_sequence,
                metadata={"backend": self.backend_id, "simulated": True, "auto_capture": auto_capture},
            )
        )

    def _build_photo(self, sequence: int) -> np.ndarray:
        frame = np.zeros((1350, 2400, 3), dtype=np.uint8)
        gradient = np.linspace(0, 255, frame.shape[1], dtype=np.uint8)
        frame[:, :, 0] = gradient
        frame[:, :, 1] = gradient[::-1]
        frame[:, :, 2] = 48
        circle_x = int((np.sin(self._frame_index / 18.0) * 0.35 + 0.5) * frame.shape[1])
        circle_y = int((np.cos(self._frame_index / 24.0) * 0.3 + 0.5) * frame.shape[0])
        cv2.circle(frame, (circle_x, circle_y), 180, (90, 220, 180), -1)
        cv2.rectangle(frame, (120, 120), (1040, 390), (20, 24, 32), -1)
        cv2.putText(frame, "PythonBooth Capture", (170, 220), cv2.FONT_HERSHEY_DUPLEX, 2.2, (240, 246, 255), 3, cv2.LINE_AA)
        cv2.putText(
            frame,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (170, 305),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.25,
            (180, 228, 220),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Simulated Capture #{sequence}",
            (170, frame.shape[0] - 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.35,
            (255, 255, 255),
            3,
            cv2.LINE_AA,
        )
        self._frame_index += 1
        return frame
