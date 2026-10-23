"""Provider-independent editorial content and generation settings."""

from pathlib import Path
from types import SimpleNamespace


class Part:
    def __init__(self, data: bytes, mime_type: str) -> None:
        self.data, self.mime_type = data, mime_type
        self.source_path: Path | None = None
        self.start_s = 0.0
        self.duration_s: float | None = None
        self.reference = ""

    @classmethod
    def from_bytes(cls, *, data: bytes, mime_type: str) -> "Part":
        return cls(data, mime_type)

    @classmethod
    def from_video_window(
        cls, path: Path, start: float, duration: float, reference: str = ""
    ) -> "Part":
        part = cls(b"", "video/mp4")
        part.source_path, part.start_s, part.duration_s = path, start, duration
        part.reference = reference
        return part


class GenerateContentConfig(SimpleNamespace):
    pass


class EmbedContentConfig(SimpleNamespace):
    pass


class ThinkingConfig(SimpleNamespace):
    pass
