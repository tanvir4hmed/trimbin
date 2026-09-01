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

import google.auth
import google.auth.transport.requests
from google.cloud import storage as gcs

from ..config import settings

log = logging.getLogger(__name__)

_client: gcs.Client | None = None


def client() -> gcs.Client:
    global _client
    if _client is None:
        _client = gcs.Client(project=settings.project_id)
    return _client


def _signer() -> dict[str, str]:
    """What generate_signed_url needs in order to sign at all.

    Signing a URL is a private key operation, and on Cloud Run there is no
    private key: the metadata server hands out access tokens and keeps the key
    to itself. That is the point of it — a key that never exists on the instance
    cannot leak from the instance — but it means the local signing path the
    library takes by default simply cannot work here.

    The way through is to ask IAM to sign on our behalf. Passing the service
    account's own email and a current access token switches the library to the
    signBlob API, which needs the account to hold serviceAccountTokenCreator on
    itself (granted in run.tf).

    Locally, where credentials come from a key file or gcloud, the default path
    works and this returns nothing.

    Worth stating plainly: this failed in production while every test passed,
    because a key file is exactly what a developer machine has and a Cloud Run
    instance never does. The difference is invisible until a real request runs
    on a real instance.
    """
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

    if hasattr(credentials, "signer_email") and getattr(credentials, "signer", None):
        # A real private key is present. Sign locally: no network call, no IAM
        # permission needed.
        return {}

    if not credentials.valid:
        credentials.refresh(google.auth.transport.requests.Request())

    email = getattr(credentials, "service_account_email", None)
    if not email or email == "default":
        # The metadata server answers "default" until asked properly. Without a
        # real address IAM has nothing to sign as.
        raise RuntimeError(
            "cannot determine the service account to sign as; "
            "signed URLs need an identity, not just a token"
        )

    return {"service_account_email": email, "access_token": credentials.token}


def originals_uri(object_path: str) -> str:
    return f"gs://{settings.originals_bucket}/{object_path}"


def proxy_url(object_path: str) -> str:
    """A path under our own domain, not a bucket URL.

    The CDN sits in front of /media, so serving the bucket address directly
    would bypass the cache and bill every viewer separately for the same
    segment — which on a demo everyone watches is the whole cost.
    """
    return f"/media/{object_path}"


async def signed_resumable_url(
    object_path: str,
    ttl: timedelta,
    max_bytes: int,
) -> tuple[str, dict[str, str]]:
    """A URL the browser POSTs once to start a resumable session.

    The single-shot PUT it replaces had two problems on a real shoot day. A
    connection that dropped at ninety per cent of a four-gigabyte file started
    that file again from zero.

    A resumable session gives the browser a session URI it can hold: it asks
    Cloud Storage how many bytes arrived and continues from there while the
    browser still owns the File object. Restoring a batch after a page refresh
    is a separate product feature and is not implied by this URL.

    The signature covers the start of the session only. Once Cloud Storage
    issues a session URI, that URI is the capability — which is why it is
    scoped to one object and expires with the session rather than with our URL.
    """
    required = {
        "Content-Type": "application/octet-stream",
        "x-goog-resumable": "start",
        "x-goog-content-length-range": f"0,{max_bytes}",
    }

    blob = client().bucket(settings.originals_bucket).blob(object_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=ttl,
        method="POST",
        content_type="application/octet-stream",
        headers={
            "x-goog-resumable": "start",
            "x-goog-content-length-range": f"0,{max_bytes}",
        },
        **_signer(),
    )
    return url, required


async def signed_upload_url(
    object_path: str,
    ttl: timedelta,
    max_bytes: int,
) -> tuple[str, dict[str, str]]:
    """A URL the browser can PUT to, and the headers it must send with it.

    Scoped to one object, one method, and one content length. A signed URL is a
    capability handed to an untrusted client, so it grants exactly the write it
    was issued for and expires.

    The headers are returned rather than documented because they are part of the
    signature: Cloud Storage rejects a request that omits a signed header, with
    a 400 that says nothing about which one. Returning the exact set means a
    client cannot get it wrong by forgetting — which is how the first real
    visitor upload failed, and it would have failed identically in the browser.
    """
    required = {
        "Content-Type": "application/octet-stream",
        "x-goog-content-length-range": f"0,{max_bytes}",
    }

    blob = client().bucket(settings.originals_bucket).blob(object_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=ttl,
        method="PUT",
        content_type="application/octet-stream",
        headers={"x-goog-content-length-range": f"0,{max_bytes}"},
        **_signer(),
    )
    return url, required


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


def delete_clip(project_id: int, clip_id: str) -> None:
    """Remove a clip's original and its proxy tree.

    Both buckets, because they are two halves of one thing: an original with no
    proxy cannot be watched and a proxy with no original cannot be re-encoded.
    Deleting one and keeping the other leaves something that is neither footage
    nor absence.

    Missing objects are not an error. A sweep that has already half-run, or a
    clip rejected before it was ever encoded, both leave gaps — and failing on
    them would stop the sweep at the first one.
    """
    prefix = f"p{project_id}/{clip_id}"

    for bucket_name in (settings.originals_bucket, settings.proxies_bucket):
        bucket = client().bucket(bucket_name)
        for blob in bucket.list_blobs(prefix=f"{prefix}/"):
            blob.delete()

    log.info("removed clip %s from storage", clip_id)


def download_proxy_window(object_prefix: str, destination, seconds: float) -> bool:
    """Fetch enough proxy segments to cover the opening of a take.

    The panel watches proxies rather than originals, and that is a fairness
    decision before it is a cost one. Proxies are encoded to one contract —
    same resolution, same codec, same keyframe placement — so a model comparing
    them is comparing the footage. Sent the originals, it would be comparing a
    4K take against a 1080p one and could be swayed by which looked sharper for
    reasons that have nothing to do with the take.

    It is also the only thing that works. An original may never have been
    uploaded, or may have aged into cold storage; a proxy exists for every
    active clip by definition.

    MPEG-TS segments concatenate byte-for-byte, which is what the format is for,
    so the window is assembled by appending files rather than by re-encoding.

    Returns False when nothing could be fetched, so the caller can judge the
    rest of the setup rather than failing the whole shot.
    """
    return download_proxy_range(object_prefix, destination, 0.0, seconds)


def download_proxy_range(
    object_prefix: str,
    destination,
    start_s: float,
    end_s: float,
) -> bool:
    """Fetch one segment-aligned source range from an HLS proxy.

    Full-take analysis works in overlapping windows. Fetching from segment zero
    for every window would repeatedly download the beginning and would make a
    58-second finding impossible to observe in the final window.

    Window boundaries are chosen on the HLS segment grid by the caller. The
    floor/ceiling here still make the function safe for a future caller with a
    fractional range: evidence is widened, never silently clipped.
    """
    from math import ceil, floor

    from .measure import SEGMENT_SECONDS

    if end_s <= start_s:
        return False

    bucket = client().bucket(settings.proxies_bucket)
    first = max(0, floor(start_s / SEGMENT_SECONDS))
    stop = max(first + 1, ceil(end_s / SEGMENT_SECONDS))

    written = 0
    with open(destination, "wb") as out:
        for index in range(first, stop):
            blob = bucket.blob(f"{object_prefix}/proxy/seg_{index:04d}.ts")
            if not blob.exists():
                break
            out.write(blob.download_as_bytes())
            written += 1

    if written == 0:
        log.warning("no proxy segments under %s for %.2f-%.2f", object_prefix, start_s, end_s)
        return False
    return True


def upload_file(local_path, object_path: str) -> None:
    """One file to the CDN bucket, with its content type set.

    Separate from upload_proxy because the worker's temporary directory holds
    more than the proxy — the clip head sent to the Slate Agent, the frames sent
    to the embedding model — and uploading the directory wholesale would put
    unlisted stills of somebody's footage on a public CDN.
    """
    types = {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".jpg": "image/jpeg",
    }
    blob = client().bucket(settings.proxies_bucket).blob(object_path)
    blob.content_type = types.get(local_path.suffix, "application/octet-stream")
    blob.upload_from_filename(str(local_path))


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
