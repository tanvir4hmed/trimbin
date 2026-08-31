"""The ingest worker.

A shoot day is two hundred clips and an hour of ffmpeg with failures in the
middle. Agents answer questions; they are the wrong shape for driving that. This
is: it takes one clip off the queue, measures it, encodes a proxy, writes a row,
and reports what happened.

One message per clip, so an unreadable file cannot take the other 199 down with
it and a retry re-runs one clip rather than a day.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from uuid import UUID

from ..services import clips, identify, jobs, quota, storage
from ..services.ffmpeg_ops import UnusableClip, analyse, build_proxy, build_sprite

log = logging.getLogger(__name__)


class Rejected(Exception):
    """The clip arrived and cannot be used.

    Distinct from a failure: nothing here will work on a retry, so the message is
    acknowledged rather than left to be redelivered five times before the dead
    letter queue catches it.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def place(
    target_scene: int,
    target_shot: int,
    read_scene: int,
    read_shot: int,
    confident: bool,
) -> tuple[int, int, str]:
    """Where the clip goes, and whether anything disagreed.

    The declared target wins. A person who dropped footage into shot 12C meant
    12C, and moving it because a slate was misread is the one mistake that
    silently scatters a shoot day.

    But a disagreement is reported. A clip sent to 12C whose slate reads 15B is
    usually a file from the wrong folder, and saying so at upload is the whole
    difference between catching it now and finding it in the cut.

    Only a confident reading contradicts a target. An unreadable board is not
    evidence of anything.
    """
    if not target_scene:
        return read_scene, read_shot, ""

    # A scene named without a shot means "this scene, and the slate sorts the
    # shots" — which is how a day of coverage on one scene actually arrives.
    # Reading a zero as shot number zero would file the whole day as ungrouped.
    shot = target_shot or read_shot

    if confident and read_scene:
        declared = (target_scene, target_shot) if target_shot else (target_scene,)
        actual = (read_scene, read_shot) if target_shot else (read_scene,)
        if declared != actual:
            return (
                target_scene,
                shot,
                f"slate reads scene {read_scene} shot {read_shot}",
            )

    return target_scene, shot, ""


async def process(
    job_id: UUID,
    clip_id: UUID,
    project_id: int,
    target_scene: int = 0,
    target_shot: int = 0,
    filename: str = "",
) -> None:
    """One clip, start to finish.

    Measurement runs before encoding, which is the largest saving in the whole
    pipeline: a false start or a black clip is discarded in seconds instead of
    after minutes of ffmpeg, and a meaningful share of any shoot day is footage
    nobody will ever use.
    """
    object_path = storage.object_for(project_id, clip_id)
    if object_path is None:
        raise Rejected("not found in storage")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        source = work / "source"

        log.info("clip %s: downloading", clip_id)
        storage.download(object_path, source)

        log.info("clip %s: measuring", clip_id)
        measurements = await analyse(source)

        # Length is a guest-project rule and cannot be known before measuring —
        # only ffmpeg can tell sixty seconds from six minutes at a low bitrate.
        # Checked here rather than at upload, and recorded as a rejection with a
        # reason, so the person sees the limit rather than a clip that vanished.
        #
        # The limits follow the project's owner, not whoever uploaded. A limit
        # that changed with the uploader is one a guest could raise by asking an
        # editor to press the button.
        limits = await quota.limits_for_project(project_id)
        if quota.clip_is_too_long(measurements.duration_s, limits):
            await clips.write_unusable(
                project_id=project_id,
                clip_id=clip_id,
                object_path=object_path,
                measurements=measurements,
                reason="guest.too_long",
            )
            raise Rejected(
                f"A guest project takes clips up to {limits.clip_seconds} "
                f"seconds; this one is {measurements.duration_s:.0f}."
            )

        usable, reason = measurements.is_usable()
        if not usable:
            # Recorded rather than dropped. An editor who uploaded 200 clips and
            # got 196 rows needs to know which four and why.
            await clips.write_unusable(
                project_id=project_id,
                clip_id=clip_id,
                object_path=object_path,
                measurements=measurements,
                reason=reason,
            )
            raise Rejected(reason)

        # Who is this clip? Both calls are best-effort and neither can cost the
        # clip: a take with measurements and no slate reading is still a take an
        # editor can use, while a take lost to a model timeout is gone.
        log.info("clip %s: reading the slate", clip_id)
        identity = await identify.read_slate(source, work, clip_id, project_id)
        identity.embedding = await identify.embed(source, work, clip_id, measurements.duration_s)

        scene, shot, mismatch = place(
            target_scene,
            target_shot,
            identity.group_id,
            identity.subgroup_id,
            bool(identity.slate_confident),
        )
        if mismatch:
            log.warning(
                "clip %s sent to %d/%d but %s", clip_id, target_scene, target_shot, mismatch
            )

        # How many takes of this shot are already here.
        #
        # Only knowable now: which shot a clip belongs to is decided just above.
        # A guest project that already has its five takes of 12A keeps the clip
        # as a rejected row rather than dropping it, so the person sees the
        # limit they were told about instead of a file that went nowhere.
        if limits.takes_per_shot and shot:
            held = await quota.takes_in_shot(project_id, scene, shot)
            if held >= limits.takes_per_shot:
                await clips.write_unusable(
                    project_id=project_id,
                    clip_id=clip_id,
                    object_path=object_path,
                    measurements=measurements,
                    reason="guest.too_many_takes",
                )
                raise Rejected(
                    f"This shot already has {held} takes, which is the limit for a guest project."
                )

        log.info("clip %s: encoding proxy", clip_id)
        proxy_dir = work / "proxy"
        await build_proxy(source, proxy_dir)
        await build_sprite(source, work / "sprite.jpg", measurements.duration_s)

        prefix = f"p{project_id}/{clip_id}"
        # Only the proxy tree and the sprite. The head clip and the embedding
        # frames are working files, and uploading them would put unlisted stills
        # of somebody's footage on a public CDN.
        storage.upload_proxy(proxy_dir, f"{prefix}/proxy")
        storage.upload_file(work / "sprite.jpg", f"{prefix}/sprite.jpg")

        await clips.write(
            project_id=project_id,
            clip_id=clip_id,
            object_path=object_path,
            measurements=measurements,
            proxy_uri=storage.proxy_url(f"{prefix}/proxy/index.m3u8"),
            sprite_uri=storage.proxy_url(f"{prefix}/sprite.jpg"),
            group_id=scene,
            subgroup_id=shot,
            take_no=identity.take_no,
            slate_confident=identity.slate_confident,
            slate_raw=identity.slate_raw,
            camera=identity.camera,
            embedding=identity.embedding,
        )

    await jobs.record_placement(
        job_id=job_id,
        clip_id=clip_id,
        filename=filename,
        scene=scene,
        shot=shot,
        take_no=identity.take_no,
        slate_raw=identity.slate_raw,
        confident=bool(identity.slate_confident),
        mismatch=mismatch,
    )
    log.info("clip %s: done", clip_id)


async def handle_message(attributes: dict[str, str]) -> bool:
    """Returns whether to acknowledge.

    A rejection is acknowledged — retrying will not make a corrupt file readable,
    and leaving it to be redelivered five times only delays the same answer while
    holding a worker each time.

    A genuine failure is not, so Pub/Sub redelivers and the dead letter policy
    eventually parks it with the evidence intact.
    """
    job_id = UUID(attributes["job_id"])
    clip_id = UUID(attributes["clip_id"])
    target_scene = int(attributes.get("target_scene", "0") or 0)
    target_shot = int(attributes.get("target_shot", "0") or 0)
    filename = attributes.get("filename", "")
    # No default. A missing project id used to become 0, which sent the download
    # to a prefix that cannot exist and produced "not found in storage" — a
    # message that blames the upload for a fault in the queue.
    project_id = int(attributes["project_id"])

    try:
        await process(job_id, clip_id, project_id, target_scene, target_shot, filename)
        await jobs.record_progress(job_id, clip_id, ok=True)
        return True

    except (Rejected, UnusableClip) as exc:
        reason = getattr(exc, "reason", str(exc))
        log.info("clip %s rejected: %s", clip_id, reason)
        await jobs.record_progress(job_id, clip_id, ok=False, reason=reason)
        return True

    except Exception as exc:
        log.exception("clip %s failed", clip_id)
        await jobs.record_progress(job_id, clip_id, ok=False, reason=f"processing error: {exc}")
        return False
