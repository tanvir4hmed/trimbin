"""Persistent filesystem originals and derived media; no provider storage SDK."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from ..config import settings
from ..media.files import safe_path


def original_path(object_path: str, *, exists=True) -> Path:
    return safe_path(Path(settings.originals_root), object_path, exists=exists)


def derivative_path(object_path: str, *, exists=True) -> Path:
    return safe_path(Path(settings.proxies_root), "editorial/" + object_path, exists=exists)


def originals_uri(object_path: str) -> str:
    return "trimbin://originals/" + object_path


def proxy_url(object_path: str) -> str:
    return "/api/files/media/" + quote(object_path, safe="/")


async def signed_resumable_url(object_path, ttl, max_bytes):
    from .file_capabilities import issue_upload

    token = issue_upload(object_path, max_bytes, int(time.time() + ttl.total_seconds()))
    return "/api/files/upload/" + token, {"Content-Type": "application/octet-stream"}


async def signed_upload_url(object_path, ttl, max_bytes):
    return await signed_resumable_url(object_path, ttl, max_bytes)


async def confirm_uploads(project_id, clip_ids):
    present, missing = [], []
    for clip_id in clip_ids:
        (present if object_for(project_id, clip_id) else missing).append(clip_id)
    return present, missing


def object_for(project_id: int, clip_id: UUID):
    folder = Path(settings.originals_root) / f"p{project_id}" / str(clip_id)
    for file in folder.iterdir() if folder.is_dir() and not folder.is_symlink() else []:
        if file.is_file() and not file.is_symlink() and not file.name.endswith(".partial"):
            return file.relative_to(settings.originals_root).as_posix()
    from ..media.files import MediaError
    from ..media.store import MediaStore

    try:
        MediaStore(settings.database_url).get(project_id, clip_id)
        return f"source:{project_id}:{clip_id}"
    except MediaError:
        return None
    return None


def resolve_original(object_path):
    if object_path.startswith("source:"):
        from ..media.files import MediaPaths
        from ..media.store import MediaStore

        _, project, source_id = object_path.split(":")
        source = MediaStore(settings.database_url).get(int(project), UUID(source_id))
        path = MediaPaths(settings).resolve(
            int(project), source["root_alias"], source["relative_path"]
        )
    else:
        path = original_path(object_path)
    return path


def resolve_source(project_id, clip_id):
    reference = object_for(project_id, clip_id)
    if not reference:
        raise FileNotFoundError("Original source unavailable")
    return resolve_original(reference)


def download(object_path, destination):
    shutil.copyfile(resolve_original(object_path), destination)


def delete_clip(project_id: int, clip_id: str):
    UUID(clip_id)
    for root, relative in (
        (Path(settings.originals_root), f"p{project_id}/{clip_id}"),
        (Path(settings.proxies_root), f"editorial/p{project_id}/{clip_id}"),
    ):
        folder = root / relative
        if (
            folder.is_dir()
            and not folder.is_symlink()
            and folder.resolve().is_relative_to(root.resolve())
        ):
            shutil.rmtree(folder)


def download_proxy_window(object_prefix, destination, seconds):
    return download_proxy_range(object_prefix, destination, 0, seconds)


def download_proxy_range(object_prefix, destination, start_s, end_s):
    from math import ceil, floor

    from .measure import SEGMENT_SECONDS

    if end_s <= start_s:
        return False
    written = 0
    with open(destination, "wb") as out:
        for index in range(max(0, floor(start_s / SEGMENT_SECONDS)), ceil(end_s / SEGMENT_SECONDS)):
            try:
                file = derivative_path(f"{object_prefix}/proxy/seg_{index:04d}.ts")
            except FileNotFoundError:
                break
            with file.open("rb") as source:
                shutil.copyfileobj(source, out)
            written += 1
    return written > 0


def upload_file(local_path, object_path):
    target = derivative_path(object_path, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(local_path, target)


def upload_proxy(local_dir, object_prefix):
    for file in sorted(local_dir.rglob("*")):
        if file.is_file():
            upload_file(file, f"{object_prefix}/{file.relative_to(local_dir).as_posix()}")
