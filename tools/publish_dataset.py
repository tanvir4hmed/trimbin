"""Publish an ingested dataset project: proxies to the CDN, rows to the archive.

Runs after ingest_dataset.py has measured and encoded. Separated because the two
fail for entirely different reasons — encoding fails because of a codec, this
fails because of a credential — and a single script that does both leaves you
re-encoding an hour of video to retry an upload.

    python tools/publish_dataset.py --build ./dataset-build --project P001 --project-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.services.ffmpeg_ops import analyse  # noqa: E402

OUTLIER_RATIO = 1.6

# Scene numbering for the dataset. These are annotations we are adding, not
# anything the source claimed — the Zenodo record supplies takes and no verdicts.
SCENE_ID = 1

ATTRIBUTION = (
    "Yilmaz, Rietdijk, Primett, Mukhina, Lotman & Tikka (2025), Filmed Scenes, "
    "Zenodo, doi:10.5281/zenodo.15767853, CC BY 4.0"
)


def relative(values: dict[str, float]) -> dict[str, float]:
    """Each take against the median of its own setup."""
    ordered = sorted(values.values())
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    if median <= 0:
        return dict.fromkeys(values, 1.0)
    return {k: round(v / median, 4) for k, v in values.items()}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("./dataset-build"))
    parser.add_argument("--project", required=True, help="P001 or P002")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    if args.project_id >= 900_000:
        # That range is reserved for generated rows and excluded from every
        # accuracy figure. Real footage landing there would be silently omitted
        # from the numbers it should be counted in.
        print("project ids at or above 900000 are reserved for synthetic data", file=sys.stderr)
        return 1

    build = args.build / args.project
    manifest_path = build / "takes.json"
    if not manifest_path.exists():
        print(f"No manifest at {manifest_path} — run ingest_dataset.py first", file=sys.stderr)
        return 1

    takes = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_root = next(
        d for d in (args.dataset / "projects").iterdir() if d.name.startswith(args.project)
    )

    print(f"{args.project} -> project_id {args.project_id}, {len(takes)} takes")

    # Re-measure rather than carrying numbers forward from the manifest. The
    # manifest holds structure; the archive should hold measurements taken by
    # the code that is deployed now, so a change to the measurement layer is
    # never invisible in the data it produced.
    print("\nMeasuring...")
    measured = {}
    for t in takes:
        source = source_root / "takes" / t["file"]
        measured[t["clip_id"]] = await analyse(source)
        print(f"  T{t['take_no']:02d}")

    by_setup: dict[int, list[dict]] = {}
    for t in takes:
        by_setup.setdefault(t["setup_no"], []).append(t)

    if not args.skip_upload:
        from app.services import storage

        print("\nUploading proxies...")
        for t in takes:
            local = build / t["clip_id"]
            if not local.exists():
                print(f"  T{t['take_no']:02d} skipped, nothing encoded")
                continue
            storage.upload_proxy(local, f"p{args.project_id}/{t['clip_id']}")
            print(f"  T{t['take_no']:02d} uploaded")

    print("\nWriting rows...")
    rows = []
    base = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)

    for setup_no, group in sorted(by_setup.items()):
        exposure = relative({t["clip_id"]: max(measured[t["clip_id"]].mean_luma, 0.001) for t in group})
        sharp = relative({t["clip_id"]: max(measured[t["clip_id"]].sharpness, 0.001) for t in group})
        motion = relative({t["clip_id"]: max(measured[t["clip_id"]].motion_mean, 0.001) for t in group})

        for t in sorted(group, key=lambda x: x["take_no"]):
            cid = t["clip_id"]
            m = measured[cid]
            prefix = f"p{args.project_id}/{cid}"

            rows.append([
                args.project_id, SCENE_ID, setup_no, t["take_no"], UUID(cid),
                base + timedelta(minutes=t["take_no"] * 5),
                datetime.now(UTC),
                "dataset-import",
                f"zenodo:{t['file']}",
                f"/media/{prefix}/proxy/index.m3u8",
                f"/media/{prefix}/sprite.jpg",
                int(m.duration_s * 1000),
                f"{t['setup_label']} - take {t['take_no']}",
                ["cc-by-4.0", "zenodo"],
                exposure[cid],
                round(m.highlight_clip_pct + m.shadow_clip_pct, 4),
                sharp[cid],
                motion[cid],
                round(m.audio_lufs, 2),
                round(m.noise_floor_db, 2),
                m.dropped_frames,
                # The source supplies no slate. Filenames named the setup, which
                # is a stronger signal than timecode but still not a board that
                # was held up and read.
                0,
                f"filename:{t['file']}",
                "active",
                # The values the ratios above were computed from. Written even
                # though this script does its own normalisation, because
                # normalise_group has to be able to redo it when a take is added
                # — and without these it has nothing to take a median of.
                round(m.mean_luma, 4),
                round(m.sharpness, 4),
                round(m.motion_mean, 4),
                datetime.now(UTC),
            ])

    from app.services.analytics import client

    ch = await client()
    await ch.command(
        "ALTER TABLE clips DELETE WHERE project_id = {p:UInt32}",
        parameters={"p": args.project_id},
    )
    await ch.insert("clips", rows, column_names=_COLUMNS)

    print(f"  {len(rows)} clips written to project {args.project_id}")
    print(f"\nAttribution recorded: {ATTRIBUTION}")

    result = await ch.query(
        """
        SELECT subgroup_id, count() AS takes,
               round(avg(exposure_rel), 3) AS exposure,
               round(avg(motion_rel), 3) AS motion
        FROM clips WHERE project_id = {p:UInt32}
        GROUP BY subgroup_id ORDER BY subgroup_id
        """,
        parameters={"p": args.project_id},
    )
    print("\nIn the archive:")
    for row in result.result_rows:
        print(f"  setup {row[0]}: {row[1]} takes, exposure {row[2]}, motion {row[3]}")

    return 0


_COLUMNS = [
    "project_id", "group_id", "subgroup_id", "take_no", "clip_id",
    "captured_at", "ingested_at", "uploaded_by",
    "storage_uri", "proxy_uri", "sprite_uri",
    "duration_ms", "description", "tags",
    "exposure_rel", "clipping_pct", "sharpness_rel", "motion_rel",
    "audio_lufs", "noise_floor_db", "dropped_frames",
    "slate_confident", "slate_raw", "status",
    "exposure_raw", "sharpness_raw", "motion_raw", "normalised_at",
]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
