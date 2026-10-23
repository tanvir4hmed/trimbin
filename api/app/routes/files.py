"""Scoped streaming access to persistent originals and editorial HLS media."""

import asyncio
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from ..auth import Principal, current_principal
from ..config import settings
from ..media.files import require_space
from ..services import storage
from ..services.file_capabilities import verify_upload

router = APIRouter(prefix="/files", tags=["media"])


def capability(token):
    try:
        return verify_upload(token)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(403, "Upload capability invalid or expired") from None


@router.post("/upload/{token}")
async def open_upload(token: str):
    capability(token)
    return Response(
        status_code=201,
        headers={"Location": f"/api/files/upload/{token}", "Cache-Control": "no-store"},
    )


@router.put("/upload/{token}")
async def upload(token: str, request: Request):
    import fcntl

    object_path, maximum = capability(token)
    target = storage.original_path(object_path, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(str(target) + ".partial")
    content_range = request.headers.get("Content-Range", "")
    match = re.fullmatch(r"bytes (?:(\d+)-(\d+)|\*)/(\d+)", content_range)
    if not match:
        raise HTTPException(400, "Content-Range required")
    start, end, total = match.groups()
    total = int(total)
    if not 0 < total <= maximum:
        raise HTTPException(413, "File exceeds upload grant")
    if target.exists():
        if target.stat().st_size != total:
            raise HTTPException(409, "Completed original is immutable")
        return Response(status_code=200)
    with partial.open("a+b") as file:
        # Nonblocking lock acquisition keeps concurrent retries from blocking the event loop.
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "Another chunk is in progress") from None
        current = file.seek(0, os.SEEK_END)
        if start is None:
            return Response(
                status_code=308, headers={"Range": f"bytes=0-{current - 1}"} if current else {}
            )
        start, end = int(start), int(end)
        if start != current or end < start or end >= total or end - start + 1 > 8 * 1024**2:
            raise HTTPException(409, "Upload offset or chunk size invalid")
        require_space(target.parent, end - start + 1, settings.media_reserve_bytes)
        received = 0
        try:
            async for block in request.stream():
                received += len(block)
                if received > end - start + 1:
                    raise HTTPException(413, "Chunk exceeds declared range")
                file.write(block)
            if received != end - start + 1:
                raise HTTPException(400, "Chunk incomplete")
            file.flush()
            await asyncio.to_thread(os.fsync, file.fileno())
        except BaseException:
            file.truncate(start)
            raise
    if end + 1 == total:
        os.replace(partial, target)
        return Response(status_code=200)
    return Response(status_code=308, headers={"Range": f"bytes=0-{end}"})


@router.get("/media/{object_path:path}")
async def media(object_path: str, principal: Annotated[Principal, Depends(current_principal)]):
    try:
        project = int(object_path.split("/", 1)[0][1:])
        await principal.assert_can_read(project)
        path = storage.derivative_path(object_path)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Media not found") from None
    mime = (
        "application/vnd.apple.mpegurl"
        if path.suffix == ".m3u8"
        else "video/mp2t"
        if path.suffix == ".ts"
        else None
    )
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, no-store"})
