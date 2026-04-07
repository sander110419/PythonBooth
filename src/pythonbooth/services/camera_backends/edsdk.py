from __future__ import annotations

import atexit
import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_char,
    c_int32,
    c_int64,
    c_uint32,
    c_uint64,
    c_void_p,
)
import logging
import os
import platform
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EdsError = c_uint32
EdsBool = c_int32
EdsChar = c_char
EdsInt32 = c_int32
EdsInt64 = c_int64
EdsUInt32 = c_uint32
EdsUInt64 = c_uint64
EdsVoid = c_void_p

EdsBaseRef = c_void_p
EdsCameraListRef = EdsBaseRef
EdsCameraRef = EdsBaseRef
EdsStreamRef = EdsBaseRef
EdsEvfImageRef = EdsBaseRef
EdsDirectoryItemRef = EdsBaseRef

EDS_ERR_OK = 0
EDS_ERR_DEVICE_BUSY = 0x00000081
EDS_ERR_OBJECT_NOTREADY = 0x0000A102
EDS_ERR_PTP_DEVICE_BUSY = 0x00002019
EDS_ERR_TAKE_PICTURE_AF_NG = 0x00008D01

kEdsPropID_SaveTo = 0x0000000B
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_Evf_Mode = 0x00000501
kEdsPropID_Evf_DepthOfFieldPreview = 0x00000504
kEdsSaveTo_Host = 2
kEdsEvfOutputDevice_PC = 2
kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_PressShutterButton = 0x00000004
kEdsCameraCommand_DoEvfAf = 0x00000102
kEdsCameraCommand_ShutterButton_OFF = 0x00000000
kEdsCameraCommand_ShutterButton_Halfway = 0x00000001
kEdsCameraCommand_ShutterButton_Completely = 0x00000003
kEdsCameraCommand_ShutterButton_Completely_NonAF = 0x00010003
kEdsObjectEvent_All = 0x00000200
kEdsObjectEvent_DirItemRequestTransfer = 0x00000208
kEdsSeek_Begin = 1

if os.name == "nt":
    CallbackFactory = ctypes.WINFUNCTYPE
else:
    CallbackFactory = CFUNCTYPE


@dataclass
class EdsDeviceInfo:
    szPortName: bytes
    szDeviceDescription: bytes


class EDSDKError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(f"{message} (EDSDK error=0x{code:08x})")
        self.code = int(code)


def _check(err: int, message: str) -> None:
    if int(err) != EDS_ERR_OK:
        raise EDSDKError(int(err), message)


class _EdsDeviceInfoStruct(ctypes.Structure):
    _fields_ = [
        ("szPortName", EdsChar * 256),
        ("szDeviceDescription", EdsChar * 256),
        ("deviceSubType", EdsUInt32),
        ("reserved", EdsUInt32),
    ]


class _EdsDirectoryItemInfoStruct(ctypes.Structure):
    _fields_ = [
        ("size", EdsUInt64),
        ("isFolder", EdsBool),
        ("groupID", EdsUInt32),
        ("option", EdsUInt32),
        ("szFileName", EdsChar * 256),
        ("format", EdsUInt32),
        ("dateTime", EdsUInt32),
    ]


class _EdsCapacityStruct(ctypes.Structure):
    _fields_ = [
        ("numberOfFreeClusters", EdsInt32),
        ("bytesPerSector", EdsInt32),
        ("reset", EdsBool),
    ]


EdsObjectEventHandler = CallbackFactory(EdsError, EdsUInt32, EdsBaseRef, EdsVoid)
EdsPropertyEventHandler = CallbackFactory(EdsError, EdsUInt32, EdsUInt32, EdsUInt32, EdsVoid)
EdsStateEventHandler = CallbackFactory(EdsError, EdsUInt32, EdsUInt32, EdsVoid)


class EDSDK:
    def __init__(self, library_path: Optional[str] = None):
        self._library_path = self._resolve_library_path(library_path) or self._default_library_path()
        if not self._library_path:
            raise FileNotFoundError("Could not locate Canon EDSDK library. Set EDSDK_LIBRARY_PATH or provide a valid SDK path.")
        loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
        logger.info("Loading EDSDK from %s", self._library_path)
        self._lib = loader(str(self._library_path))
        self._define_prototypes()
        self._callback_refs: list[object] = []
        self._initialized = False
        self._init_lock = threading.Lock()

    @staticmethod
    def _resolve_library_path(path: Optional[str]) -> Optional[str]:
        if not path:
            return None

        candidate = Path(path).expanduser()
        if candidate.is_file():
            return str(candidate)

        if not candidate.is_dir():
            return None

        if os.name == "nt":
            candidates = [
                candidate / "EDSDK.dll",
                candidate / "windows" / "EDSDK.dll",
                candidate / "windows" / "EDSDK_64" / "Dll" / "EDSDK.dll",
                candidate / "canon-sdk" / "windows" / "EDSDK_64" / "Dll" / "EDSDK.dll",
            ]
        else:
            machine = platform.machine().lower()
            arch_dir = "x86_64" if machine in {"x86_64", "amd64"} else "ARM64"
            candidates = [
                candidate / "libEDSDK.so",
                candidate / "Linux" / "EDSDK" / "Library" / arch_dir / "libEDSDK.so",
                candidate / "canon-sdk" / "Linux" / "EDSDK" / "Library" / arch_dir / "libEDSDK.so",
            ]
        for maybe in candidates:
            if maybe.exists():
                return str(maybe)
        return None

    @staticmethod
    def _default_library_path() -> Optional[str]:
        env_path = os.environ.get("EDSDK_LIBRARY_PATH")
        if env_path:
            resolved = EDSDK._resolve_library_path(env_path)
            return resolved or env_path

        repo_root = Path(__file__).resolve().parents[4]
        sibling_reference = repo_root.parent / "Photobooth-software" / "canon-sdk"
        local_sdk_root = repo_root / "canon-sdk"

        search_roots = [local_sdk_root, sibling_reference]

        if os.name == "nt":
            candidates = [
                root / "windows" / "EDSDK_64" / "Dll" / "EDSDK.dll"
                for root in search_roots
            ] + [
                root / "windows" / "EDSDK.dll"
                for root in search_roots
            ]
        else:
            machine = platform.machine().lower()
            arch_dir = "x86_64" if machine in {"x86_64", "amd64"} else "ARM64"
            candidates = [
                root / "Linux" / "EDSDK" / "Library" / arch_dir / "libEDSDK.so"
                for root in search_roots
            ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _define_prototypes(self) -> None:
        lib = self._lib
        lib.EdsInitializeSDK.restype = EdsError
        lib.EdsTerminateSDK.restype = EdsError
        lib.EdsGetEvent.restype = EdsError
        lib.EdsGetCameraList.argtypes = [POINTER(EdsCameraListRef)]
        lib.EdsGetCameraList.restype = EdsError
        lib.EdsGetChildCount.argtypes = [EdsBaseRef, POINTER(EdsUInt32)]
        lib.EdsGetChildCount.restype = EdsError
        lib.EdsGetChildAtIndex.argtypes = [EdsBaseRef, EdsInt32, POINTER(EdsBaseRef)]
        lib.EdsGetChildAtIndex.restype = EdsError
        lib.EdsGetDeviceInfo.argtypes = [EdsCameraRef, POINTER(_EdsDeviceInfoStruct)]
        lib.EdsGetDeviceInfo.restype = EdsError
        lib.EdsOpenSession.argtypes = [EdsCameraRef]
        lib.EdsOpenSession.restype = EdsError
        lib.EdsCloseSession.argtypes = [EdsCameraRef]
        lib.EdsCloseSession.restype = EdsError
        lib.EdsSendCommand.argtypes = [EdsCameraRef, EdsUInt32, EdsInt32]
        lib.EdsSendCommand.restype = EdsError
        lib.EdsSetPropertyData.argtypes = [EdsBaseRef, EdsUInt32, EdsInt32, EdsUInt32, EdsVoid]
        lib.EdsSetPropertyData.restype = EdsError
        lib.EdsGetPropertyData.argtypes = [EdsBaseRef, EdsUInt32, EdsInt32, EdsUInt32, EdsVoid]
        lib.EdsGetPropertyData.restype = EdsError
        lib.EdsSetCapacity.argtypes = [EdsCameraRef, _EdsCapacityStruct]
        lib.EdsSetCapacity.restype = EdsError
        lib.EdsCreateMemoryStream.argtypes = [EdsUInt64, POINTER(EdsStreamRef)]
        lib.EdsCreateMemoryStream.restype = EdsError
        lib.EdsCreateEvfImageRef.argtypes = [EdsStreamRef, POINTER(EdsEvfImageRef)]
        lib.EdsCreateEvfImageRef.restype = EdsError
        lib.EdsDownloadEvfImage.argtypes = [EdsCameraRef, EdsEvfImageRef]
        lib.EdsDownloadEvfImage.restype = EdsError
        lib.EdsGetLength.argtypes = [EdsStreamRef, POINTER(EdsUInt64)]
        lib.EdsGetLength.restype = EdsError
        lib.EdsSeek.argtypes = [EdsStreamRef, EdsInt64, EdsInt32]
        lib.EdsSeek.restype = EdsError
        lib.EdsRead.argtypes = [EdsStreamRef, EdsUInt64, EdsVoid, POINTER(EdsUInt64)]
        lib.EdsRead.restype = EdsError
        lib.EdsGetDirectoryItemInfo.argtypes = [EdsDirectoryItemRef, POINTER(_EdsDirectoryItemInfoStruct)]
        lib.EdsGetDirectoryItemInfo.restype = EdsError
        lib.EdsDownload.argtypes = [EdsDirectoryItemRef, EdsUInt64, EdsStreamRef]
        lib.EdsDownload.restype = EdsError
        lib.EdsDownloadComplete.argtypes = [EdsDirectoryItemRef]
        lib.EdsDownloadComplete.restype = EdsError
        lib.EdsDeleteDirectoryItem.argtypes = [EdsDirectoryItemRef]
        lib.EdsDeleteDirectoryItem.restype = EdsError
        lib.EdsSetObjectEventHandler.argtypes = [EdsCameraRef, EdsUInt32, EdsObjectEventHandler, EdsVoid]
        lib.EdsSetObjectEventHandler.restype = EdsError
        lib.EdsSetPropertyEventHandler.argtypes = [EdsCameraRef, EdsUInt32, EdsPropertyEventHandler, EdsVoid]
        lib.EdsSetPropertyEventHandler.restype = EdsError
        lib.EdsSetCameraStateEventHandler.argtypes = [EdsCameraRef, EdsUInt32, EdsStateEventHandler, EdsVoid]
        lib.EdsSetCameraStateEventHandler.restype = EdsError
        lib.EdsRelease.argtypes = [EdsBaseRef]
        lib.EdsRelease.restype = EdsUInt32
        lib.EdsRetain.argtypes = [EdsBaseRef]
        lib.EdsRetain.restype = EdsUInt32

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            _check(self._lib.EdsInitializeSDK(), "EdsInitializeSDK failed")
            self._initialized = True
            atexit.register(self.terminate)

    def terminate(self) -> None:
        with self._init_lock:
            if not self._initialized:
                return
            try:
                self._lib.EdsTerminateSDK()
            finally:
                self._initialized = False

    def pump_events(self) -> None:
        if self._initialized:
            self._lib.EdsGetEvent()

    def get_camera_list(self) -> list[tuple[EdsCameraRef, EdsDeviceInfo]]:
        self.initialize()
        camera_list_ref = EdsCameraListRef()
        _check(self._lib.EdsGetCameraList(ctypes.byref(camera_list_ref)), "EdsGetCameraList failed")
        try:
            count = EdsUInt32()
            _check(self._lib.EdsGetChildCount(camera_list_ref, ctypes.byref(count)), "EdsGetChildCount(camera_list) failed")
            results: list[tuple[EdsCameraRef, EdsDeviceInfo]] = []
            for index in range(int(count.value)):
                cam_ref = EdsBaseRef()
                _check(self._lib.EdsGetChildAtIndex(camera_list_ref, index, ctypes.byref(cam_ref)), "EdsGetChildAtIndex(camera) failed")
                info = _EdsDeviceInfoStruct()
                _check(self._lib.EdsGetDeviceInfo(cam_ref, ctypes.byref(info)), "EdsGetDeviceInfo failed")
                results.append(
                    (
                        EdsCameraRef(cam_ref.value),
                        EdsDeviceInfo(szPortName=bytes(info.szPortName), szDeviceDescription=bytes(info.szDeviceDescription)),
                    )
                )
            return results
        finally:
            if camera_list_ref:
                self._lib.EdsRelease(camera_list_ref)

    def open_session(self, camera_ref: EdsCameraRef) -> None:
        self.initialize()
        _check(self._lib.EdsOpenSession(camera_ref), "EdsOpenSession failed")

    def close_session(self, camera_ref: EdsCameraRef) -> None:
        _check(self._lib.EdsCloseSession(camera_ref), "EdsCloseSession failed")

    def release_ref(self, ref: EdsBaseRef) -> None:
        if ref:
            self._lib.EdsRelease(ref)

    def retain_ref(self, ref: EdsBaseRef) -> None:
        if ref:
            self._lib.EdsRetain(ref)

    def set_u32_property(self, ref: EdsBaseRef, prop_id: int, value: int) -> None:
        value_ref = EdsUInt32(int(value))
        _check(
            self._lib.EdsSetPropertyData(ref, EdsUInt32(prop_id), EdsInt32(0), EdsUInt32(ctypes.sizeof(value_ref)), ctypes.byref(value_ref)),
            f"EdsSetPropertyData(prop=0x{prop_id:08x}) failed",
        )

    def get_u32_property(self, ref: EdsBaseRef, prop_id: int) -> int:
        value_ref = EdsUInt32(0)
        _check(
            self._lib.EdsGetPropertyData(ref, EdsUInt32(prop_id), EdsInt32(0), EdsUInt32(ctypes.sizeof(value_ref)), ctypes.byref(value_ref)),
            f"EdsGetPropertyData(prop=0x{prop_id:08x}) failed",
        )
        return int(value_ref.value)

    def set_capacity_for_host(self, camera_ref: EdsCameraRef) -> None:
        cap = _EdsCapacityStruct(0x7FFFFFFF, 0x1000, 1)
        _check(self._lib.EdsSetCapacity(camera_ref, cap), "EdsSetCapacity failed")

    def send_command(self, camera_ref: EdsCameraRef, command: int, param: int = 0) -> None:
        _check(self._lib.EdsSendCommand(camera_ref, EdsUInt32(command), EdsInt32(param)), f"EdsSendCommand(0x{command:08x}) failed")

    def set_object_event_handler(self, camera_ref: EdsCameraRef, handler) -> None:
        callback = EdsObjectEventHandler(handler)
        self._callback_refs.append(callback)
        _check(self._lib.EdsSetObjectEventHandler(camera_ref, EdsUInt32(kEdsObjectEvent_All), callback, None), "EdsSetObjectEventHandler failed")

    def set_state_event_handler(self, camera_ref: EdsCameraRef, handler) -> None:
        callback = EdsStateEventHandler(handler)
        self._callback_refs.append(callback)
        _check(self._lib.EdsSetCameraStateEventHandler(camera_ref, EdsUInt32(0x00000300), callback, None), "EdsSetCameraStateEventHandler failed")

    def set_property_event_handler(self, camera_ref: EdsCameraRef, handler) -> None:
        callback = EdsPropertyEventHandler(handler)
        self._callback_refs.append(callback)
        _check(self._lib.EdsSetPropertyEventHandler(camera_ref, EdsUInt32(0x00000100), callback, None), "EdsSetPropertyEventHandler failed")

    def download_directory_item(self, dir_item_ref: EdsDirectoryItemRef) -> tuple[str, bytes]:
        info = _EdsDirectoryItemInfoStruct()
        _check(self._lib.EdsGetDirectoryItemInfo(dir_item_ref, ctypes.byref(info)), "EdsGetDirectoryItemInfo failed")
        filename = bytes(info.szFileName).split(b"\x00", 1)[0].decode(errors="replace")

        stream = EdsStreamRef()
        _check(self._lib.EdsCreateMemoryStream(EdsUInt64(0), ctypes.byref(stream)), "EdsCreateMemoryStream failed")
        try:
            _check(self._lib.EdsDownload(dir_item_ref, info.size, stream), "EdsDownload failed")
            _check(self._lib.EdsDownloadComplete(dir_item_ref), "EdsDownloadComplete failed")
            try:
                self._lib.EdsDeleteDirectoryItem(dir_item_ref)
            except Exception:
                pass

            length = EdsUInt64(0)
            _check(self._lib.EdsGetLength(stream, ctypes.byref(length)), "EdsGetLength failed")
            if length.value == 0:
                return filename, b""
            _check(self._lib.EdsSeek(stream, EdsInt64(0), EdsInt32(kEdsSeek_Begin)), "EdsSeek(Begin) failed")
            buf = (ctypes.c_ubyte * int(length.value))()
            read = EdsUInt64(0)
            _check(self._lib.EdsRead(stream, EdsUInt64(length.value), ctypes.byref(buf), ctypes.byref(read)), "EdsRead failed")
            return filename, bytes(buf[: int(read.value)])
        finally:
            if stream:
                self._lib.EdsRelease(stream)

    def download_evf_frame_to_bytes(self, camera_ref: EdsCameraRef) -> bytes:
        stream = EdsStreamRef()
        _check(self._lib.EdsCreateMemoryStream(EdsUInt64(0), ctypes.byref(stream)), "EdsCreateMemoryStream failed")
        evf_image = EdsEvfImageRef()
        try:
            _check(self._lib.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image)), "EdsCreateEvfImageRef failed")
            _check(self._lib.EdsDownloadEvfImage(camera_ref, evf_image), "EdsDownloadEvfImage failed")
            length = EdsUInt64(0)
            _check(self._lib.EdsGetLength(stream, ctypes.byref(length)), "EdsGetLength failed")
            if length.value == 0:
                return b""
            _check(self._lib.EdsSeek(stream, EdsInt64(0), EdsInt32(kEdsSeek_Begin)), "EdsSeek(Begin) failed")
            buf = (ctypes.c_ubyte * int(length.value))()
            read = EdsUInt64(0)
            _check(self._lib.EdsRead(stream, EdsUInt64(length.value), ctypes.byref(buf), ctypes.byref(read)), "EdsRead failed")
            return bytes(buf[: int(read.value)])
        finally:
            if evf_image:
                self._lib.EdsRelease(evf_image)
            if stream:
                self._lib.EdsRelease(stream)


_sdk_singleton: Optional[EDSDK] = None
_sdk_lock = threading.Lock()


def get_sdk(library_path: Optional[str] = None) -> EDSDK:
    global _sdk_singleton
    with _sdk_lock:
        if _sdk_singleton is None:
            _sdk_singleton = EDSDK(library_path)
            _sdk_singleton.initialize()
        return _sdk_singleton
