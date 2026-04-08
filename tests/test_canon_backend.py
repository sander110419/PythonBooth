import numpy as np

from pythonbooth.services.camera_backends.canon import CanonCameraBackend
from pythonbooth.services.image_utils import encode_bgr_to_jpeg


def test_canon_backend_prefers_direct_take_picture_for_eos_r_bodies():
    backend = CanonCameraBackend()
    backend._device_description = "Canon EOS R6 Mark II"

    assert backend._prefer_direct_take_picture() is True


def test_canon_backend_keeps_shutter_press_for_non_r_bodies():
    backend = CanonCameraBackend()
    backend._device_description = "Canon EOS 5D Mark IV"

    assert backend._prefer_direct_take_picture() is False


def test_canon_download_capture_builds_raw_preview_from_downloaded_file_only():
    class FakeSDK:
        def download_directory_item(self, _ref):
            frame = np.zeros((40, 60, 3), dtype=np.uint8)
            frame[:, :] = (30, 200, 120)
            jpeg = encode_bgr_to_jpeg(frame, quality=90)
            assert jpeg is not None
            return "IMG_1234.CR3", b"RAWDATA" + jpeg + b"TAIL"

    backend = CanonCameraBackend()
    backend._sdk = FakeSDK()
    payload = backend._download_capture(object())

    assert payload is not None
    assert payload.original_filename == "IMG_1234.CR3"
    assert payload.preview_data is not None
    assert payload.preview_data.startswith(b"\xff\xd8\xff")
