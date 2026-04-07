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
            message="Simulator ready" if self._connected else "Simulator offline",
            camera_name="PythonBooth Simulator",
            preview_available=self._connected,
        )

    def get_preview_frame(self) -> np.ndarray | None:
        if not self._connected:
            return None
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        gradient = np.linspace(0, 255, frame.shape[1], dtype=np.uint8)
        frame[:, :, 0] = gradient
        frame[:, :, 1] = gradient[::-1]
        frame[:, :, 2] = 48
        circle_x = int((np.sin(self._frame_index / 18.0) * 0.35 + 0.5) * frame.shape[1])
        circle_y = int((np.cos(self._frame_index / 24.0) * 0.3 + 0.5) * frame.shape[0])
        cv2.circle(frame, (circle_x, circle_y), 110, (90, 220, 180), -1)
        cv2.rectangle(frame, (80, 80), (520, 240), (20, 24, 32), -1)
        cv2.putText(frame, "PythonBooth Live", (120, 150), cv2.FONT_HERSHEY_DUPLEX, 1.6, (240, 246, 255), 2, cv2.LINE_AA)
        cv2.putText(
            frame,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (120, 205),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (180, 228, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"Simulated Canon Feed #{self._camera_sequence}",
            (80, frame.shape[0] - 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        self._frame_index += 1
        self._maybe_auto_capture(frame)
        return frame

    def poll_captures(self) -> list[CapturePayload]:
        captures: list[CapturePayload] = []
        while not self._captures.empty():
            captures.append(self._captures.get_nowait())
        return captures

    def request_capture(self) -> None:
        if not self._connected:
            return
        frame = self.get_preview_frame()
        if frame is None:
            return
        photo = cv2.resize(frame, (2400, 1350), interpolation=cv2.INTER_CUBIC)
        jpeg = encode_bgr_to_jpeg(photo, quality=96)
        preview = encode_bgr_to_jpeg(frame, quality=90)
        if jpeg is None:
            return
        self._camera_sequence += 1
        payload = CapturePayload(
            data=jpeg,
            preview_data=preview,
            original_filename=f"SIM_{self._camera_sequence:05d}.JPG",
            source=self.backend_id,
            camera_sequence=self._camera_sequence,
            metadata={"backend": self.backend_id, "simulated": True},
        )
        self._captures.put(payload)

    def _maybe_auto_capture(self, frame: np.ndarray) -> None:
        if self._auto_capture_seconds <= 0:
            return
        now = datetime.now()
        if (now - self._last_auto_capture).total_seconds() < self._auto_capture_seconds:
            return
        self._last_auto_capture = now
        photo = cv2.resize(frame, (2400, 1350), interpolation=cv2.INTER_CUBIC)
        jpeg = encode_bgr_to_jpeg(photo, quality=96)
        preview = encode_bgr_to_jpeg(frame, quality=90)
        if jpeg is None:
            return
        self._camera_sequence += 1
        self._captures.put(
            CapturePayload(
                data=jpeg,
                preview_data=preview,
                original_filename=f"SIM_{self._camera_sequence:05d}.JPG",
                source=self.backend_id,
                camera_sequence=self._camera_sequence,
                metadata={"backend": self.backend_id, "simulated": True, "auto_capture": True},
            )
        )
