"""Generate test footage with faults planted on purpose.

The eval set answers the question the live accuracy number cannot: not "did an
editor disagree with us" but "did we find the thing we know is there". We put
camera shake at 4.2 seconds, so if the system reports it at 4.2 seconds that is
a fact rather than an agreement.

These are synthetic — ffmpeg test patterns with faults introduced deliberately —
which makes them reproducible, versionable, and available before anyone has time
to shoot. They are not a substitute for real footage. Real camera faults have
sensor noise, rolling shutter, focus breathing and motion blur that a synthetic
gradient does not, so a system that scores well here has cleared the lower bar.
Real fixtures replace these as they are shot; the manifest format is identical
and the harness does not care which it is reading.

    python build_fixtures.py --out ./clips
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DURATION_S = 12.0
FPS = 25
SIZE = "1280x720"


@dataclass
class PlantedFault:
    """What we put in, so we can ask whether it was found."""

    axis: str
    start_s: float
    end_s: float
    detail: str


@dataclass
class Fixture:
    fixture_id: str
    description: str
    filters: list[str]
    faults: list[PlantedFault] = field(default_factory=list)

    def is_control(self) -> bool:
        return not self.faults


# One shot, seven takes. Six carry a single planted fault and one is clean,
# because a set with no clean takes cannot measure false alarms — a system that
# flags everything would score perfectly on recall and be useless.
FIXTURES: list[Fixture] = [
    Fixture(
        fixture_id="take01_clean",
        description="Control. Nothing planted.",
        filters=[],
    ),
    Fixture(
        fixture_id="take02_shake_midsection",
        description="Camera shake between 4.2s and 7.8s, steady either side.",
        # Sinusoidal displacement, bounded to the middle of the clip. The steady
        # head and tail matter: they are what makes the finding a timecode rather
        # than a verdict on the whole take.
        #
        # Each expression is single-quoted because ffmpeg splits a filter chain
        # on commas, and between(t,4.2,7.8) contains two.
        filters=[
            "crop=in_w-40:in_h-40:"
            "'20+if(between(t,4.2,7.8),12*sin(t*38),0)':"
            "'20+if(between(t,4.2,7.8),9*cos(t*31),0)'"
        ],
        faults=[PlantedFault("stability", 4.2, 7.8, "camera shake, mid-clip only")],
    ),
    Fixture(
        fixture_id="take03_underexposed",
        description="Two stops under throughout.",
        filters=["eq=brightness=-0.28:contrast=0.82"],
        faults=[PlantedFault("exposure", 0.0, DURATION_S, "underexposed throughout")],
    ),
    Fixture(
        fixture_id="take04_soft_focus",
        description="Out of focus from 6s to the end.",
        # Timeline `enable` rather than a per-frame sigma expression: gblur takes
        # a constant, and switching the filter on at 6s is what the fault
        # actually is — focus lost partway, not focus gradually varying.
        filters=["gblur=sigma=9:enable='gte(t,6)'"],
        faults=[PlantedFault("focus", 6.0, DURATION_S, "focus lost from 6s")],
    ),
    Fixture(
        fixture_id="take05_clipped_highlights",
        description="Blown highlights throughout.",
        filters=["eq=brightness=0.55:contrast=2.6"],
        faults=[PlantedFault("exposure", 0.0, DURATION_S, "clipped highlights")],
    ),
    Fixture(
        fixture_id="take06_freeze",
        description="Frame freeze from 5s to 8s.",
        # A genuine freeze: one frame repeated. `loop` holds frame 125 (5s at
        # 25fps) for 75 frames, which is exactly what a dropped-frame event looks
        # like downstream — identical successive frames, which is what
        # freezedetect is built to find.
        filters=["loop=loop=75:size=1:start=125"],
        faults=[PlantedFault("completion", 5.0, 8.0, "picture freezes mid-take")],
    ),
    Fixture(
        fixture_id="take07_black_head",
        description="Three seconds of black at the head — a late start.",
        filters=["eq=brightness=-1:enable='lt(t,3)'"],
        faults=[PlantedFault("completion", 0.0, 3.0, "black at head, late start")],
    ),
]


def build(fixture: Fixture, out_dir: Path) -> Path:
    """Render one fixture. The source is a test pattern, not noise.

    testsrc2 has hard edges and flat colour fields, so sharpness and exposure are
    measurable rather than approximate — a noise source would give the blur
    detector nothing to lose. It also moves, which a still pattern does not, and
    a still pattern is frozen by definition.
    """
    out_path = out_dir / f"{fixture.fixture_id}.mp4"

    video_filters = ",".join(fixture.filters) if fixture.filters else "null"

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        # testsrc2 rather than a still pattern: it animates, so freezedetect has
        # something to distinguish a real freeze from. A static source is frozen
        # by definition and every take would report one.
        "-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={FPS}:duration={DURATION_S}",
        # A steady tone so the audio path has something to measure. Silence would
        # make every take identical on the audio axis and hide any regression there.
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION_S}",
        "-vf", video_filters,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{fixture.fixture_id}: {result.stderr.strip()[:300]}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("./clips"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    manifest = []
    for fixture in FIXTURES:
        try:
            path = build(fixture, args.out)
        except RuntimeError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            return 1

        manifest.append({
            "fixture_id": fixture.fixture_id,
            "file": path.name,
            "description": fixture.description,
            "is_control": fixture.is_control(),
            "faults": [asdict(f) for f in fixture.faults],
        })
        marker = "control" if fixture.is_control() else fixture.faults[0].axis
        print(f"  {fixture.fixture_id:<28} {marker}")

    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    planted = sum(len(f.faults) for f in FIXTURES)
    print(f"\n{len(FIXTURES)} takes, {planted} planted faults, 1 control")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
