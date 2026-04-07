from __future__ import annotations

import abc
from typing import Iterable

from ...models import CapturePayload, CameraStatus


class CameraBackend(abc.ABC):
    backend_id = "base"
    display_name = "Base"

    def __init__(self) -> None:
        self._connected = False

    @abc.abstractmethod
    def connect(self) -> CameraStatus:
        raise NotImplementedError

    @abc.abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def status(self) -> CameraStatus:
        raise NotImplementedError

    @abc.abstractmethod
    def poll_captures(self) -> Iterable[CapturePayload]:
        raise NotImplementedError

    @abc.abstractmethod
    def request_capture(self) -> None:
        raise NotImplementedError

    def list_available_cameras(self) -> list[str]:
        return []

    @property
    def connected(self) -> bool:
        return self._connected
