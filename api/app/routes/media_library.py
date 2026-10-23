"""Authenticated filesystem media library sharing project and editorial identities."""

from __future__ import annotations

import mimetypes
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..auth import Principal, current_principal, require_signed_in
from ..config import settings
from ..foundation.jobs import PostgresJobs
from ..media import tickets
from ..media.files import (
    CHUNK_BYTES,
    MediaError,
    MediaPaths,
    byte_range,
    digest_file,
    media_filename,
    relative_name,
    require_space,
    safe_path,
)
from ..media.store import MediaStore

router = APIRouter(prefix="/media-library", tags=["media-library"])
User = Annotated[Principal, Depends(require_signed_in)]
MediaKind = Literal["original", "proxy", "sprite", "audio"]


class MediaLocation(BaseModel):
    root_alias: str = Field(min_length=1, max_length=48)
    relative_path: str = Field(min_length=1, max_length=1500)


class MediaSourceView(BaseModel):
    id: UUID
    filename: str
    root_alias: str
    relative_path: str
    state: str
    stage: str
    error_code: str | None = None
    fingerprint: str | None = None
    duplicate_of: UUID | None = None
    metadata: dict | None = None
    available: bool
    available_files: list[str]


class MediaUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    expected_bytes: int = Field(gt=0)


class MediaUploadView(BaseModel):
    id: UUID
    filename: str
    expected_bytes: int
    received_bytes: int
    chunk_hashes: list[str]
    source_id: UUID | None = None
    chunk_bytes: int = CHUNK_BYTES


class MediaAccessView(BaseModel):
    url: str
    expires_in_seconds: int = 300


def runtime() -> tuple[MediaPaths, MediaStore]:
    return MediaPaths(settings), MediaStore(settings.database_url)


async def authorize(principal: Principal, project: int, permission: str) -> None:
    if principal.is_anonymous:
        raise HTTPException(401, "Sign in to access media.")
    store = MediaStore(settings.database_url)
    if not await run_in_threadpool(store.allowed, project, principal.email or "", permission):
        raise HTTPException(404, "No such media project.")


@router.get("/status")
async def media_status() -> dict:
    try:
        runtime()
    except (MediaError, OSError):
        return {"enabled": False}
    return {"enabled": True, "max_upload_bytes": settings.max_upload_bytes}


def source_view(paths: MediaPaths, row: dict) -> MediaSourceView:
    available = True
    try:
        paths.resolve(row["project_id"], row["root_alias"], row["relative_path"])
    except (OSError, MediaError):
        available = False
    output = row.get("derivatives") or {}
    return MediaSourceView(
        **{key: value for key, value in row.items() if key in MediaSourceView.model_fields},
        available=available,
        available_files=(["original"] if available else [])
        + [kind for kind in ("proxy", "sprite", "audio") if kind in output],
    )


@router.get("/{project}/roots", response_model=list[str])
async def roots(project: int, principal: User):
    await authorize(principal, project, "write")
    paths, _ = runtime()
    return [name for name in paths.roots if project in paths.projects.get(name, [])]


@router.post("/{project}/sources", response_model=MediaSourceView, status_code=201)
async def register(project: int, body: MediaLocation, principal: User):
    await authorize(principal, project, "write")
    paths, store = runtime()
    if body.root_alias == "uploads":
        raise MediaError("root_not_allowed")
    relative_name(body.relative_path)
    media_filename(body.relative_path.rsplit("/", 1)[-1])
    try:
        paths.resolve(project, body.root_alias, body.relative_path)
    except FileNotFoundError as exc:
        raise MediaError("source_not_found") from exc
    row = await run_in_threadpool(
        store.register,
        project,
        body.root_alias,
        body.relative_path,
        principal.email,
    )
    return source_view(paths, await run_in_threadpool(store.get, project, row["id"]))


@router.get("/{project}/sources", response_model=list[MediaSourceView])
async def sources(
    project: int,
    principal: User,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await authorize(principal, project, "read")
    paths, store = runtime()
    rows = await run_in_threadpool(store.listing, project, offset, limit)
    return [source_view(paths, row) for row in rows]


@router.get("/{project}/sources/{source_id}", response_model=MediaSourceView)
async def source(project: int, source_id: UUID, principal: User):
    await authorize(principal, project, "read")
    paths, store = runtime()
    return source_view(paths, await run_in_threadpool(store.get, project, source_id))


@router.put("/{project}/sources/{source_id}/location", response_model=MediaSourceView)
async def relink(project: int, source_id: UUID, body: MediaLocation, principal: User):
    await authorize(principal, project, "owner")
    paths, store = runtime()
    await run_in_threadpool(store.get, project, source_id)
    try:
        path = paths.resolve(project, body.root_alias, body.relative_path)
    except FileNotFoundError as exc:
        raise MediaError("source_not_found") from exc
    fingerprint = await run_in_threadpool(digest_file, path)
    await run_in_threadpool(
        store.relink, project, source_id, body.root_alias, body.relative_path, fingerprint
    )
    return source_view(paths, await run_in_threadpool(store.get, project, source_id))


@router.post("/{project}/sources/{source_id}/retry", status_code=202)
async def retry(project: int, source_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    _, store = runtime()
    await run_in_threadpool(store.retry, project, source_id)
    return {"status": "queued"}


@router.post("/{project}/sources/{source_id}/cancel")
async def cancel(project: int, source_id: UUID, principal: User) -> dict:
    await authorize(principal, project, "write")
    _, store = runtime()
    row = await run_in_threadpool(store.get, project, source_id)
    await run_in_threadpool(PostgresJobs(settings.database_url).cancel, project, row["job_id"])
    return {"status": "cancellation_requested"}


@router.post("/{project}/uploads", response_model=MediaUploadView, status_code=201)
async def open_upload(project: int, body: MediaUploadRequest, principal: User):
    await authorize(principal, project, "write")
    paths, store = runtime()
    if body.expected_bytes > settings.max_upload_bytes:
        raise MediaError("upload_size_exceeded")
    require_space(paths.staging, body.expected_bytes, settings.media_reserve_bytes)
    return await run_in_threadpool(
        store.open_upload,
        project,
        body.filename,
        body.expected_bytes,
        principal.email,
    )


@router.get("/{project}/uploads/{upload_id}", response_model=MediaUploadView)
async def upload_status(project: int, upload_id: UUID, principal: User):
    await authorize(principal, project, "write")
    _, store = runtime()
    return await run_in_threadpool(store.upload_status, project, upload_id, principal.email)


@router.get("/{project}/uploads", response_model=list[MediaUploadView])
async def pending_uploads(project: int, principal: User):
    await authorize(principal, project, "write")
    _, store = runtime()
    return await run_in_threadpool(store.pending_uploads, project, principal.email)


@router.put("/{project}/uploads/{upload_id}", response_model=MediaUploadView)
async def upload_chunk(
    project: int,
    upload_id: UUID,
    request: Request,
    principal: User,
    offset: int = Query(ge=0),
):
    await authorize(principal, project, "write")
    paths, store = runtime()
    await run_in_threadpool(store.upload_status, project, upload_id, principal.email)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > CHUNK_BYTES:
            raise MediaError("invalid_chunk_size")
        data.extend(chunk)
    return await run_in_threadpool(
        store.append_upload,
        paths,
        project,
        upload_id,
        principal.email,
        offset,
        bytes(data),
        settings.media_reserve_bytes,
    )


@router.post("/{project}/uploads/{upload_id}/complete", response_model=MediaUploadView)
async def complete_upload(project: int, upload_id: UUID, principal: User):
    await authorize(principal, project, "write")
    paths, store = runtime()
    return await run_in_threadpool(
        store.complete_upload, paths, project, upload_id, principal.email
    )


@router.delete("/{project}/uploads/{upload_id}", status_code=204)
async def discard_upload(project: int, upload_id: UUID, principal: User):
    await authorize(principal, project, "write")
    paths, store = runtime()
    await run_in_threadpool(store.discard_upload, paths, project, upload_id, principal.email)


@router.post("/{project}/sources/{source_id}/access/{kind}", response_model=MediaAccessView)
async def access(project: int, source_id: UUID, kind: MediaKind, principal: User):
    await authorize(principal, project, "read")
    _, store = runtime()
    row = await run_in_threadpool(store.get, project, source_id)
    if kind != "original" and kind not in (row.get("derivatives") or {}):
        raise MediaError("derivative_not_ready")
    token = tickets.issue(settings.session_secret, project, str(source_id), kind)
    return MediaAccessView(
        url=f"/media-library/{project}/sources/{source_id}/file/{kind}?ticket={token}"
    )


@router.get("/{project}/sources/{source_id}/file/{kind}")
@router.head("/{project}/sources/{source_id}/file/{kind}", include_in_schema=False)
async def file_response(
    project: int,
    source_id: UUID,
    kind: MediaKind,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    ticket: str | None = None,
):
    if ticket:
        tickets.verify(settings.session_secret, project, str(source_id), kind, ticket)
    else:
        if principal.is_anonymous:
            raise HTTPException(401, "Sign in to access media.")
        await authorize(principal, project, "read")
    paths, store = runtime()
    row = await run_in_threadpool(store.get, project, source_id)
    if kind == "original":
        try:
            path = paths.resolve(project, row["root_alias"], row["relative_path"])
        except FileNotFoundError as exc:
            raise MediaError("source_not_found") from exc
    else:
        output = row.get("derivatives") or {}
        if kind not in output:
            raise MediaError("derivative_not_ready")
        try:
            path = safe_path(paths.derivatives, f"{output['directory']}/{output[kind]}")
        except FileNotFoundError as exc:
            raise MediaError("derivative_not_found") from exc
    handle = path.open("rb")
    try:
        import os

        size = os.fstat(handle.fileno()).st_size
        try:
            start, end, partial = byte_range(request.headers.get("range"), size)
        except MediaError:
            handle.close()
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        }
        if partial:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        if request.method == "HEAD":
            handle.close()
            return Response(status_code=206 if partial else 200, headers=headers)

        def stream():
            try:
                handle.seek(start)
                remaining = end - start + 1
                while remaining:
                    block = handle.read(min(1024**2, remaining))
                    if not block:
                        break
                    remaining -= len(block)
                    yield block
            finally:
                handle.close()

        return StreamingResponse(
            stream(),
            status_code=206 if partial else 200,
            headers=headers,
            media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )
    except BaseException:
        handle.close()
        raise
