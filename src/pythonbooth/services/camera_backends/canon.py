from __future__ import annotations

import logging
from pathlib import Path
import re
import threading
import time
from queue import Empty, SimpleQueue

import cv2
import numpy as np

from ...models import CapturePayload, CameraStatus
from ..image_utils import encode_bgr_to_jpeg
from .base import CameraBackend
from .edsdk import (
    EDSDKError,
    EDS_ERR_DEVICE_BUSY,
    EDS_ERR_OBJECT_NOTREADY,
    EDS_ERR_PTP_DEVICE_BUSY,
    EDS_ERR_TAKE_PICTURE_AF_NG,
    get_sdk,
    kEdsCameraCommand_DoEvfAf,
    kEdsCameraCommand_ExtendShutDownTimer,
    kEdsCameraCommand_PressShutterButton,
    kEdsCameraCommand_ShutterButton_Completely,
    kEdsCameraCommand_ShutterButton_Completely_NonAF,
    kEdsCameraCommand_ShutterButton_Halfway,
    kEdsCameraCommand_ShutterButton_OFF,
    kEdsEvfOutputDevice_PC,
    kEdsObjectEvent_DirItemRequestTransfer,
    kEdsPropID_Evf_DepthOfFieldPreview,
    kEdsPropID_Evf_Mode,
    kEdsPropID_Evf_OutputDevice,
    kEdsPropID_SaveTo,
    kEdsSaveTo_Host,
)

logger = logging.getLogger(__name__)


class CanonCameraBackend(CameraBackend):
    backend_id = "canon"
    display_name = "Canon EDSDK"

    def __init__(self, sdk_path: str | None = None):
        super().__init__()
        self._sdk_path = sdk_path or None
        self._sdk = None
        self._camera_ref = None
        self._device_description = ""
        self._port_name = ""
        self._status = CameraStatus.idle(self.backend_id, "Canon disconnected")
        self._op_lock = threading.RLock()
        self._transfer_queue: SimpleQueue[int] = SimpleQueue()
        self._last_frame: np.ndarray | None = None
        self._remote_ready = False
        self._live_view_active = False
        self._last_keepalive = 0.0

    @staticmethod
    def _should_retry(code: int) -> bool:
        return int(code) in {EDS_ERR_DEVICE_BUSY, EDS_ERR_PTP_DEVICE_BUSY, EDS_ERR_OBJECT_NOTREADY}

    def _retry(self, fn, retries: int = 6, delay_s: float = 0.08):
        last_error: Exception | None = None
        for attempt in range(max(1, int(retries))):
            try:
                return fn()
            except EDSDKError as exc:
                last_error = exc
                if self._should_retry(exc.code) and attempt < int(retries) - 1:
                    try:
                        if self._sdk:
                            self._sdk.pump_events()
                    except Exception:
                        pass
                    time.sleep(max(0.0, float(delay_s)))
                    continue
                raise
        if last_error:
            raise last_error

    def list_available_cameras(self) -> list[str]:
        try:
            sdk = get_sdk(self._sdk_path)
            cameras = sdk.get_camera_list()
            names: list[str] = []
            for cam_ref, info in cameras:
                model = info.szDeviceDescription.split(b"\x00", 1)[0].decode(errors="replace")
                port = info.szPortName.split(b"\x00", 1)[0].decode(errors="replace")
                names.append(f"{model} ({port})")
                try:
                    sdk.release_ref(cam_ref)
                except Exception:
                    pass
            return names
        except Exception:
            return []

    def connect(self) -> CameraStatus:
        try:
            self._sdk = get_sdk(self._sdk_path)
            cameras = self._sdk.get_camera_list()
            if not cameras:
                self._connected = False
                self._status = CameraStatus(
                    backend=self.backend_id,
                    connected=False,
                    state="disconnected",
                    message="No Canon camera detected",
                    available_cameras=[],
                )
                return self._status

            self._camera_ref, info = cameras[0]
            for extra_ref, _extra_info in cameras[1:]:
                try:
                    self._sdk.release_ref(extra_ref)
                except Exception:
                    pass

            self._device_description = info.szDeviceDescription.split(b"\x00", 1)[0].decode(errors="replace")
            self._port_name = info.szPortName.split(b"\x00", 1)[0].decode(errors="replace")
            self._retry(lambda: self._sdk.open_session(self._camera_ref), retries=10, delay_s=0.2)
            time.sleep(0.12)
            self._register_handlers()
            self._ensure_remote_ready()
            self._connected = True
            self._status = CameraStatus(
                backend=self.backend_id,
                connected=True,
                state="connected",
                message=f"Connected to {self._device_description}",
                camera_name=self._device_description,
                preview_available=True,
                available_cameras=self.list_available_cameras(),
            )
            return self._status
        except FileNotFoundError as exc:
            self._connected = False
            self._status = CameraStatus(
                backend=self.backend_id,
                connected=False,
                state="error",
                message="Canon SDK not found",
                last_error=str(exc),
            )
            return self._status
        except Exception as exc:
            logger.exception("Canon connect failed")
            self._connected = False
            self._status = CameraStatus(
                backend=self.backend_id,
                connected=False,
                state="error",
                message="Failed to connect Canon camera",
                last_error=str(exc),
            )
            self.disconnect()
            return self._status

    def disconnect(self) -> None:
        if not self._sdk or not self._camera_ref:
            self._connected = False
            return
        try:
            self._release_preview()
        except Exception:
            pass
        try:
            self._sdk.close_session(self._camera_ref)
        except Exception:
            pass
        try:
            self._sdk.release_ref(self._camera_ref)
        except Exception:
            pass
        self._camera_ref = None
        self._connected = False
        self._remote_ready = False
        self._status = CameraStatus.idle(self.backend_id, "Canon disconnected")

    def status(self) -> CameraStatus:
        return self._status

    def request_capture(self) -> None:
        if not self._connected or not self._sdk or not self._camera_ref:
            return

        self._ensure_remote_ready()
            try:
                self._auto_focus()
            with self._op_lock:
                try:
                    self._retry(
                        lambda: self._sdk.send_command(
                            self._camera_ref,
                            kEdsCameraCommand_PressShutterButton,
                            kEdsCameraCommand_ShutterButton_Completely,
                        ),
                        retries=5,
                        delay_s=0.12,
                    )
                except EDSDKError as exc:
                    if int(exc.code) == int(EDS_ERR_TAKE_PICTURE_AF_NG):
                        self._retry(
                            lambda: self._sdk.send_command(
                                self._camera_ref,
                                kEdsCameraCommand_PressShutterButton,
                                kEdsCameraCommand_ShutterButton_Completely_NonAF,
                            ),
                            retries=2,
                            delay_s=0.15,
                        )
                    else:
                        raise
                finally:
                    try:
                        self._sdk.send_command(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_OFF)
                    except Exception:
                        pass
        except Exception as exc:
            logger.exception("Canon capture request failed")
            self._status = CameraStatus(
                backend=self.backend_id,
                connected=self._connected,
                state="error",
                message="Capture request failed",
                camera_name=self._device_description,
                last_error=str(exc),
                preview_available=True,
            )

    def poll_captures(self) -> list[CapturePayload]:
        if not self._connected or not self._sdk:
            return []
        with self._op_lock:
            try:
                self._sdk.pump_events()
            except Exception:
                return []

        captures: list[CapturePayload] = []
        while not self._transfer_queue.empty():
            try:
                dir_item_ref = self._transfer_queue.get_nowait()
            except Empty:
                break
            try:
                capture = self._download_capture(dir_item_ref)
                if capture is not None:
                    captures.append(capture)
            finally:
                try:
                    self._sdk.release_ref(dir_item_ref)
                except Exception:
                    pass
        return captures

    def get_preview_frame(self) -> np.ndarray | None:
        if not self._connected or not self._sdk or not self._camera_ref:
            return None
        try:
            with self._op_lock:
                self._keep_alive()
                self._sdk.pump_events()
                if not self._live_view_active:
                    self._start_preview()
                data = None
                for _ in range(5):
                    try:
                        data = self._sdk.download_evf_frame_to_bytes(self._camera_ref)
                        break
                    except EDSDKError as exc:
                        if self._should_retry(exc.code):
                            time.sleep(0.03)
                            self._sdk.pump_events()
                            continue
                        raise
                if not data:
                    return self._last_frame
                image_data = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if frame is not None:
                    self._last_frame = frame
                return self._last_frame
        except Exception as exc:
            self._status = CameraStatus(
                backend=self.backend_id,
                connected=self._connected,
                state="error",
                message="Live view unavailable",
                camera_name=self._device_description,
                last_error=str(exc),
            )
            return self._last_frame

    def _register_handlers(self) -> None:
        assert self._sdk is not None
        assert self._camera_ref is not None

        def on_object_event(event, item_ref, _context):
            try:
                if int(event) == int(kEdsObjectEvent_DirItemRequestTransfer):
                    self._sdk.retain_ref(item_ref)
                    self._transfer_queue.put(item_ref)
            finally:
                if item_ref:
                    self._sdk.release_ref(item_ref)
            return 0

        def noop_property(_event, _prop_id, _param, _context):
            return 0

        def noop_state(_event, _param, _context):
            return 0

        self._sdk.set_object_event_handler(self._camera_ref, on_object_event)
        self._sdk.set_property_event_handler(self._camera_ref, noop_property)
        self._sdk.set_state_event_handler(self._camera_ref, noop_state)

    def _ensure_remote_ready(self) -> None:
        if self._remote_ready or not self._sdk or not self._camera_ref:
            return

        def setup():
            self._sdk.pump_events()
            self._sdk.send_command(self._camera_ref, kEdsCameraCommand_ExtendShutDownTimer, 0)
            self._sdk.set_u32_property(self._camera_ref, kEdsPropID_SaveTo, kEdsSaveTo_Host)
            self._sdk.set_capacity_for_host(self._camera_ref)

        self._retry(setup, retries=10, delay_s=0.15)
        self._remote_ready = True

    def _auto_focus(self) -> None:
        if not self._sdk or not self._camera_ref:
            return
        with self._op_lock:
            try:
                self._sdk.send_command(self._camera_ref, kEdsCameraCommand_DoEvfAf, 1)
                time.sleep(0.18)
                self._sdk.send_command(self._camera_ref, kEdsCameraCommand_DoEvfAf, 0)
                return
            except Exception:
                pass
            self._retry(
                lambda: self._sdk.send_command(
                    self._camera_ref,
                    kEdsCameraCommand_PressShutterButton,
                    kEdsCameraCommand_ShutterButton_Halfway,
                ),
                retries=4,
                delay_s=0.12,
            )
            time.sleep(0.25)
            try:
                self._sdk.send_command(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_OFF)
            except Exception:
                pass

    def _start_preview(self) -> None:
        if not self._sdk or not self._camera_ref:
            return
        self._retry(lambda: self._sdk.set_u32_property(self._camera_ref, kEdsPropID_Evf_Mode, 1), retries=5, delay_s=0.08)
        try:
            current = self._sdk.get_u32_property(self._camera_ref, kEdsPropID_Evf_OutputDevice)
        except Exception:
            current = 0
        self._retry(
            lambda: self._sdk.set_u32_property(self._camera_ref, kEdsPropID_Evf_OutputDevice, int(current) | int(kEdsEvfOutputDevice_PC)),
            retries=5,
            delay_s=0.08,
        )
        self._live_view_active = True
        time.sleep(0.18)

    def _release_preview(self) -> None:
        if not self._sdk or not self._camera_ref or not self._live_view_active:
            return
        try:
            dof = self._sdk.get_u32_property(self._camera_ref, kEdsPropID_Evf_DepthOfFieldPreview)
            if int(dof) != 0:
                self._sdk.set_u32_property(self._camera_ref, kEdsPropID_Evf_DepthOfFieldPreview, 0)
        except Exception:
            pass
        try:
            current = self._sdk.get_u32_property(self._camera_ref, kEdsPropID_Evf_OutputDevice)
        except Exception:
            current = int(kEdsEvfOutputDevice_PC)
        try:
            self._sdk.set_u32_property(self._camera_ref, kEdsPropID_Evf_OutputDevice, int(current) & ~int(kEdsEvfOutputDevice_PC))
        except Exception:
            pass
        try:
            self._sdk.set_u32_property(self._camera_ref, kEdsPropID_Evf_Mode, 0)
        except Exception:
            pass
        self._live_view_active = False

    def _keep_alive(self) -> None:
        if not self._sdk or not self._camera_ref:
            return
        now = time.time()
        if now - self._last_keepalive < 15.0:
            return
        try:
            self._sdk.send_command(self._camera_ref, kEdsCameraCommand_ExtendShutDownTimer, 0)
        except Exception:
            pass
        self._last_keepalive = now

    def _download_capture(self, dir_item_ref) -> CapturePayload | None:
        assert self._sdk is not None
        filename, data = self._sdk.download_directory_item(dir_item_ref)
        if not data:
            return None
        camera_sequence = self._extract_camera_sequence(filename)

        preview_data = None
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is not None:
            preview_data = data
            self._last_frame = image
        elif self._last_frame is not None:
            preview_data = encode_bgr_to_jpeg(self._last_frame, quality=88)

        return CapturePayload(
            data=data,
            preview_data=preview_data,
            original_filename=filename,
            source=self.backend_id,
            camera_sequence=camera_sequence,
            metadata={"camera_name": self._device_description, "port": self._port_name},
        )

    @staticmethod
    def _extract_camera_sequence(filename: str) -> int | None:
        match = re.search(r"(\d{3,})", Path(filename).stem)
        return int(match.group(1)) if match else None
