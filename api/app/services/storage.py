"""Cloud Storage: signed URLs in, CDN paths out.

Video never passes through this service. The browser is handed a signed URL and
uploads directly to the bucket, which keeps Cloud Run sized for request count
rather than footage volume — proxying gigabytes would cost twice, once in and
once out, and make the service scale with the size of a shoot day.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from google.cloud import storage as gcs

from ..config import settings

log = logging.getLogger(__name__)

_client: gcs.Client | None = None


def client() -> gcs.Client:
    global _client
    if _client is None:
        _client = gcs.Client(project=settings.project_id)
    return _client


def originals_uri(object_path: str) -> str:
    return f"gs://{settings.originals_bucket}/{object_path}"


def proxy_url(object_path: str) -> str:
    """A path under our own domain, not a bucket URL.

    The CDN sits in front of /media, so serving the bucket address directly
    would bypass the cache and bill every viewer separately for the same
    segment — which on a demo everyone watches is the whole cost.
    """
    return f"/media/{object_path}"


async def signed_upload_url(
    object_path: str,
    ttl: timedelta,
    max_bytes: int,
) -> str:
    """A URL the browser can PUT to, and nothing else.

    Scoped to one object, one method, and one content length. A signed URL is a
    capability handed to an untrusted client, so it grants exactly the write it
    was issued for and expires.
    """
    blob = client().bucket(settings.originals_bucket).blob(object_path)

    return blob.generate_signed_url(
        version="v4",
        expiration=ttl,
        method="PUT",
        content_type="application/octet-stream",
        headers={"x-goog-content-length-range": f"0,{max_bytes}"},
    )


async def confirm_uploads(
    project_id: int,
    clip_ids: list[UUID],
) -> tuple[list[UUID], list[UUID]]:
    """Which of these actually arrived.

    The browser reports what it believes it uploaded and is not trusted: a
    client that crashed mid-transfer will happily claim success. Queueing work
    for an object that does not exist fails five times and lands in the dead
    letter queue having taught nobody anything.
    """
    bucket = client().bucket(settings.originals_bucket)
    present, missing = [], []

    for clip_id in clip_ids:
        prefix = f"p{project_id}/{clip_id}/"
        if next(bucket.list_blobs(prefix=prefix, max_results=1), None):
            present.append(clip_id)
        else:
            missing.append(clip_id)

    if missing:
        log.warning("%d of %d reported clips are not in storage", len(missing), len(clip_ids))

    return present, missing


def object_for(project_id: int, clip_id: UUID) -> str | None:
    """The stored object for a clip, whatever the browser named it.

    The original filename is preserved in the path for a human reading the
    bucket, so the name cannot be reconstructed and has to be looked up.
    """
    bucket = client().bucket(settings.originals_bucket)
    blob = next(bucket.list_blobs(prefix=f"p{project_id}/{clip_id}/", max_results=1), None)
    return blob.name if blob else None


def download(object_path: str, destination) -> None:
    client().bucket(settings.originals_bucket).blob(object_path).download_to_filename(
        str(destination)
    )


def upload_proxy(local_dir, object_prefix: str) -> None:
    """Push an encoded proxy tree to the CDN bucket.

    Content types are set explicitly: a manifest served as octet-stream will not
    play, and the failure appears in the player with nothing in the logs.
    """
    bucket = client().bucket(settings.proxies_bucket)
    types = {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".jpg": "image/jpeg",
    }

    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        blob = bucket.blob(f"{object_prefix}/{rel}")
        blob.content_type = types.get(path.suffix, "application/octet-stream")
        blob.upload_from_filename(str(path))
