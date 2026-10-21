"""Operator-owned roots, immutable source reads and bounded file work."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from ..config import Settings

SUFFIXES = frozenset({".mov", ".mp4", ".m4v", ".mkv", ".avi", ".mxf"})
CHUNK_BYTES = 8 * 1024**2


class MediaError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def relative_name(value: str) -> str:
    # Apply the same rules on Windows and Linux, including ADS and device paths.
    parts = value.split("/")
    if (
        not value
        or len(value) > 1500
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
        or any(p in {"", ".", ".."} or p.endswith((".", " ")) for p in parts)
        or any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in parts)
    ):
        raise MediaError("invalid_media_path")
    return PurePosixPath(value).as_posix()


def safe_path(root: Path, relative: str, *, exists: bool = True) -> Path:
    relative_name(relative)
    root = root.resolve(strict=True)
    candidate = root.joinpath(*relative.split("/"))
    current = root
    for part in relative.split("/"):
        current /= part
        if current.is_symlink() or current.is_junction():
            raise MediaError("media_link_forbidden")
    resolved = candidate.resolve(strict=exists)
    if not resolved.is_relative_to(root):
        raise MediaError("media_path_escape")
    if exists and not resolved.is_file():
        raise MediaError("not_a_media_file")
    return resolved


def media_filename(value: str) -> str:
    relative_name(value)
    if "/" in value or Path(value).suffix.lower() not in SUFFIXES:
        raise MediaError("unsupported_media_format")
    return value


class MediaPaths:
    """Roots must be controlled by the deployment operator, not browser callers.

    Mount originals read-only in worker/API containers. The upload process owns
    the separate originals root and staging root. No arbitrary host path API.
    """

    def __init__(self, settings: Settings):
        values = [settings.originals_root, settings.proxies_root, settings.staging_root]
        if not all(values):
            raise MediaError("media_not_configured")
        self.originals, self.derivatives, self.staging = [Path(v).resolve() for v in values]
        self.roots = {name: Path(path).resolve() for name, path in settings.media_roots.items()}
        self.projects = settings.media_root_projects
        if "uploads" in self.roots or any(
            not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", name) for name in self.roots
        ):
            raise MediaError("invalid_root_alias")
        allowed = {Path(p).resolve() for p in settings.allowed_media_roots}
        if not {self.originals, *self.roots.values()} <= allowed:
            raise MediaError("root_not_allowed")
        all_roots = [self.originals, self.derivatives, self.staging, *self.roots.values()]
        if settings.export_root:
            all_roots.append(Path(settings.export_root).resolve())
        for index, first in enumerate(all_roots):
            for second in all_roots[index + 1 :]:
                if first.is_relative_to(second) or second.is_relative_to(first):
                    raise MediaError("media_roots_overlap")
        for path in (self.originals, self.derivatives, self.staging):
            path.mkdir(parents=True, exist_ok=True)

    def resolve(self, project: int, alias: str, relative: str, *, exists: bool = True) -> Path:
        if alias == "uploads":
            if not relative.startswith(f"p{project}/"):
                raise MediaError("root_not_allowed")
            root = self.originals
        else:
            if alias not in self.roots or project not in self.projects.get(alias, []):
                raise MediaError("root_not_allowed")
            root = self.roots[alias]
        return safe_path(root, relative, exists=exists)


def file_signature(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def digest_file(path: Path, check: Callable[[], None] = lambda: None) -> str:
    before = file_signature(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024**2):
            check()
            digest.update(block)
    if file_signature(path) != before:
        raise MediaError("source_changed")
    return digest.hexdigest()


def require_space(root: Path, needed: int, reserve: int) -> None:
    if shutil.disk_usage(root).free < needed + reserve:
        raise MediaError("insufficient_disk_space")


def byte_range(header: str | None, size: int) -> tuple[int, int, bool]:
    if not header:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or not any(match.groups()) or size <= 0:
        raise MediaError("invalid_range")
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise MediaError("invalid_range")
        return max(0, size - length), size - 1, True
    start, end = int(first), min(size - 1, int(last)) if last else size - 1
    if start >= size or end < start:
        raise MediaError("invalid_range")
    return start, end, True
