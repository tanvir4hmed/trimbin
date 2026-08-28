"""Run the Editorial AI Dataset through the real pipeline.

This is the first real footage the system has seen. Everything before it was
generated, and the difference matters: these are handheld takes shot by working
cinematographers, carrying the sensor noise, focus breathing and motion blur that
a filter-generated fixture does not have.

Structure the dataset does not state but its filenames do:

    Scene 001
      Setup A - female perspective   takes 1, 2, 3
      Setup B - male perspective     takes 4, 5, 6

Treating these as six takes of one setup would be wrong. Comparison only means
something within a setup: three attempts at the same camera position can be
ranked on which came out best, while a wide against a close-up asks which shot
the scene needs, which is a story question nobody should answer from
measurements.

    python tools/ingest_dataset.py --dataset ../Editorial_AI_Dataset --dry-run
    python tools/ingest_dataset.py --dataset ../Editorial_AI_Dataset --project P001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.services.ffmpeg_ops import analyse, build_proxy, build_sprite  # noqa: E402
from app.services.measure import RawMeasurements  # noqa: E402

# Only CC BY 4.0 material may reach a public deployment. The Blackmagic package
# is training material given away freely and still owned by Blackmagic: it can be
# analysed locally and must not be redistributed. Refused here rather than left
# to somebody's memory at deploy time.
PUBLISHABLE = {"P001", "P002"}
LOCAL_ONLY = {"P003"}

OUTLIER_RATIO = 1.6

# Setup is not a column in the dataset, but it is in the filenames.
_PERSPECTIVE = re.compile(r"_(Female|Male)_Perspective", re.IGNORECASE)
_TAKE = re.compile(r"Take[_ ]?(\d+)", re.IGNORECASE)

SETUPS = {
    "female": (1, "A", "female perspective"),
    "male": (2, "B", "male perspective"),
}


@dataclass
class Take:
    file: Path
    setup_no: int
    setup_letter: str
    setup_label: str
    take_no: int
    clip_id: str
    measurements: RawMeasurements | None = None


def parse(file: Path) -> tuple[int, str, str, int] | None:
    """Read setup and take out of the filename.

    Returns None rather than guessing when the pattern does not match. A filename
    that does not say which setup it belongs to is not evidence of one, and
    inventing a grouping is exactly the quiet mistake this system exists to
    avoid.
    """
    perspective = _PERSPECTIVE.search(file.name)
    take = _TAKE.search(file.name)
    if not perspective or not take:
        return None

    setup_no, letter, label = SETUPS[perspective.group(1).lower()]
    return setup_no, letter, label, int(take.group(1))


def relative(values: dict[str, float]) -> dict[str, float]:
    """Each take against the median of its own setup.

    Never against an absolute standard. Six takes of a dim scene are a dim scene,
    not six faults, and only a ratio can tell those apart.
    """
    ordered = sorted(values.values())
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    if median <= 0:
        return dict.fromkeys(values, 1.0)
    return {k: round(v / median, 4) for k, v in values.items()}


async def ingest_project(root: Path, out: Path, dry_run: bool) -> None:
    code = root.name.split("_")[0]
    print("\n" + "=" * 66)
    print(f"{code} - {root.name}")
    print("=" * 66)

    takes: list[Take] = []
    for file in sorted((root / "takes").glob("*.mov")):
        parsed = parse(file)
        if parsed is None:
            print(f"  skipped, filename says nothing about setup: {file.name}")
            continue
        setup_no, letter, label, take_no = parsed
        takes.append(
            Take(
                file=file,
                setup_no=setup_no,
                setup_letter=letter,
                setup_label=label,
                take_no=take_no,
                # Deterministic, so a re-run replaces rather than duplicates.
                clip_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"trimbin/{code}/{file.name}")),
            )
        )

    by_setup: dict[int, list[Take]] = {}
    for t in takes:
        by_setup.setdefault(t.setup_no, []).append(t)

    print(f"{len(takes)} takes across {len(by_setup)} setups")
    for _, group in sorted(by_setup.items()):
        numbers = ", ".join(str(t.take_no) for t in group)
        print(f"  Setup {group[0].setup_letter} - {group[0].setup_label}: takes {numbers}")

    print("\nMeasuring...")
    for t in takes:
        t.measurements = await analyse(t.file)
        m = t.measurements
        flags = []
        if m.freeze_spans:
            flags.append(f"{len(m.freeze_spans)} freeze")
        if m.black_spans:
            flags.append(f"{len(m.black_spans)} black")
        if m.focus_loss_spans:
            flags.append(f"focus lost {m.focus_loss_spans[0].start_s:.1f}s")
        if m.motion_spikes:
            flags.append(f"{len(m.motion_spikes)} motion spike")
        events = " / ".join(flags) if flags else "no events"
        print(f"  T{t.take_no:02d}  {m.duration_s:5.1f}s  {events}")

    print("\nRelative to each setup's median:")
    for _, group in sorted(by_setup.items()):
        exposure = relative({t.clip_id: max(t.measurements.mean_luma, 0.001) for t in group})
        sharp = relative({t.clip_id: max(t.measurements.sharpness, 0.001) for t in group})
        motion = relative({t.clip_id: max(t.measurements.motion_mean, 0.001) for t in group})

        print(f"\n  Setup {group[0].setup_letter} - {group[0].setup_label}")
        print(f"  {'take':<7}{'exposure':>10}{'focus':>9}{'motion':>9}   outliers")
        for t in sorted(group, key=lambda x: x.take_no):
            marks = []
            if exposure[t.clip_id] <= 1 / OUTLIER_RATIO:
                marks.append("darkest")
            if exposure[t.clip_id] >= OUTLIER_RATIO:
                marks.append("brightest")
            if sharp[t.clip_id] <= 1 / OUTLIER_RATIO:
                marks.append("softest")
            if motion[t.clip_id] >= OUTLIER_RATIO:
                marks.append("most movement")
            print(
                f"  T{t.take_no:<6}{exposure[t.clip_id]:>10.2f}"
                f"{sharp[t.clip_id]:>9.2f}{motion[t.clip_id]:>9.2f}   {', '.join(marks)}"
            )

    if dry_run:
        print("\nDry run - nothing encoded.")
        return

    out.mkdir(parents=True, exist_ok=True)
    print("\nEncoding proxies...")
    for t in takes:
        work = out / code / t.clip_id
        await build_proxy(t.file, work / "proxy")
        await build_sprite(t.file, work / "sprite.jpg", t.measurements.duration_s)
        print(f"  T{t.take_no:02d} done")

    manifest = out / code / "takes.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "clip_id": t.clip_id,
                    "file": t.file.name,
                    "setup_no": t.setup_no,
                    "setup_letter": t.setup_letter,
                    "setup_label": t.setup_label,
                    "take_no": t.take_no,
                    "duration_s": round(t.measurements.duration_s, 3),
                }
                for t in takes
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nProxies and manifest in {(out / code).resolve()}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--project", help="P001, P002. Omit for all publishable ones.")
    parser.add_argument("--out", type=Path, default=Path("./dataset-build"))
    parser.add_argument("--dry-run", action="store_true", help="Measure and report, encode nothing.")
    args = parser.parse_args()

    roots = sorted((args.dataset / "projects").iterdir())
    selected = [
        r
        for r in roots
        if r.is_dir()
        and r.name.split("_")[0] in PUBLISHABLE
        and (args.project is None or r.name.startswith(args.project))
    ]

    if not selected:
        print("No publishable project matched.", file=sys.stderr)
        print(f"Local-only and excluded: {', '.join(sorted(LOCAL_ONLY))}", file=sys.stderr)
        return 1

    for root in selected:
        await ingest_project(root, args.out, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
