from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from string import Formatter
import os
import re
import unicodedata
from typing import Any, Literal

SequenceSource = Literal["camera", "session"]

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PATH_SPLIT = re.compile(r"[\\/]+")
_WILDCARD_RUN = re.compile(r"(?<![A-Z])[X#?]{2,}(?![A-Z])")

_KNOWN_TOKENS = (
    "SESSION_SEQUENCE",
    "SESSIONSEQNUM",
    "CAMERA_SEQUENCE",
    "SESSIONSEQ",
    "SESSION_ID",
    "DATETIME",
    "SESSION",
    "CAMERA",
    "BOOTH",
    "MACHINE",
    "EVENT",
    "DATE",
    "TIME",
    "DAY",
    "EXT",
    "SEQ",
    "PHOTO",
)
_KNOWN_TOKEN_PATTERN = re.compile(
    r"(?<![A-Z0-9])(" + "|".join(re.escape(token) for token in _KNOWN_TOKENS) + r")(?![A-Z0-9])"
)


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = _PATH_SPLIT.sub("_", value)
    value = _INVALID_FILENAME_CHARS.sub("_", value)
    value = re.sub(r"\s+", "_", value).strip()
    value = re.sub(r"_+", "_", value)
    value = value.strip(" ._")
    return value or "_"


def sanitize_filename_part(value: str) -> str:
    return _normalize_text(value)


def sanitize_filename(value: str) -> str:
    stem, ext = os.path.splitext(value)
    safe = _normalize_text(stem)
    ext_value = ext.lstrip(".")
    safe_ext = _normalize_text(ext_value) if ext_value else ""
    ext_part = f".{safe_ext}" if safe_ext else ""
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"
    return f"{safe}{ext_part}" if ext_part else safe


def _format_day(value: datetime) -> str:
    return ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[value.weekday()]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


@dataclass(slots=True)
class NamingContext:
    event_name: str = ""
    booth_name: str = ""
    machine_name: str = ""
    session_name: str = ""
    session_id: str = ""
    capture_datetime: datetime = field(default_factory=datetime.now)
    camera_sequence: int | None = None
    session_sequence: int | None = None
    extension: str = ""
    preferred_sequence_source: SequenceSource = "camera"

    def value_map(self) -> dict[str, Any]:
        booth = self.booth_name or self.machine_name
        session = self.session_name or self.session_id
        ext = self.extension.lstrip(".")
        camera_seq = _safe_int(self.camera_sequence, 0)
        session_seq = _safe_int(self.session_sequence, camera_seq)
        return {
            "EVENT": self.event_name,
            "BOOTH": booth,
            "MACHINE": self.machine_name or booth,
            "SESSION": session,
            "SESSION_ID": self.session_id,
            "DAY": _format_day(self.capture_datetime),
            "DATE": self.capture_datetime.strftime("%Y%m%d"),
            "TIME": self.capture_datetime.strftime("%H%M%S"),
            "DATETIME": self.capture_datetime.strftime("%Y%m%d_%H%M%S"),
            "EXT": ext,
            "CAMERA": camera_seq,
            "SEQ": camera_seq,
            "PHOTO": camera_seq,
            "CAMERA_SEQUENCE": camera_seq,
            "SESSIONSEQ": session_seq,
            "SESSION_SEQUENCE": session_seq,
            "SESSIONSEQNUM": session_seq,
        }

    def render(self, template: str) -> "CompiledFilename":
        return compile_filename(template, self)


@dataclass(slots=True)
class CompiledFilename:
    template: str
    filename: str
    stem: str
    extension: str
    camera_sequence: int | None
    session_sequence: int | None
    sequence_source: SequenceSource


class _TemplateFormatter(Formatter):
    def __init__(self, values: dict[str, Any]):
        super().__init__()
        self._values = values

    def get_value(self, key: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if isinstance(key, str) and key in self._values:
            return self._values[key]
        return super().get_value(key, args, kwargs)


def _render_brace_template(template: str, values: dict[str, Any]) -> str:
    formatter = _TemplateFormatter(values)
    rendered = formatter.vformat(template, args=(), kwargs={})
    return rendered


def _render_wildcards(template: str, values: dict[str, Any], preferred_sequence_source: SequenceSource) -> str:
    sequence_value = values["CAMERA"] if preferred_sequence_source == "camera" else values["SESSIONSEQ"]

    def replace_wildcard(match: re.Match[str]) -> str:
        width = len(match.group(0))
        return f"{sequence_value:0{width}d}"

    rendered = _WILDCARD_RUN.sub(replace_wildcard, template)

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in values:
            return str(values[token])
        return token

    rendered = _KNOWN_TOKEN_PATTERN.sub(replace_token, rendered)
    return rendered


def compile_filename(template: str, context: NamingContext) -> CompiledFilename:
    values = context.value_map()
    rendered = template
    if "{" in rendered and "}" in rendered:
        rendered = _render_brace_template(template, values)
    rendered = _render_wildcards(rendered, values, context.preferred_sequence_source)

    rendered = sanitize_filename(rendered)
    stem, ext = os.path.splitext(rendered)
    return CompiledFilename(
        template=template,
        filename=f"{stem}{ext}",
        stem=stem,
        extension=ext,
        camera_sequence=context.camera_sequence,
        session_sequence=context.session_sequence,
        sequence_source=context.preferred_sequence_source,
    )
