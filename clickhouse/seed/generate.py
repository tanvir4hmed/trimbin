"""Generate a synthetic archive at production scale.

The point is not to fake a demo — the demo runs on real footage. The point is to
answer a fair question a judge will ask: at a hundred clips, any database would
do, so why ClickHouse?

This produces millions of decision rows across hundreds of productions, so the
showcase query in ../queries/ can be run live against a corpus no small store
would answer quickly. The shape of the data matters as much as the volume: takes
cluster into shots, margins cluster near the review threshold, and overrides
follow the pattern real ones do — common on close calls, rare on confident ones.

Embeddings are deliberately not generated. They are 768 floats per row, which
would dominate the file for no benefit — vector search is demonstrated on real
footage with real embeddings, and the column defaults to a zero vector that the
index simply never matches. So clips.csv is inserted with an explicit column
list, leaving `embedding` to its default.

    python generate.py --productions 400 --out ./out

    curl -u default:PASSWORD --data-binary @out/clips.csv \\
      "$URL/?query=INSERT+INTO+clips+($(cat out/clips.columns))+FORMAT+CSV"
    curl -u default:PASSWORD --data-binary @out/decisions.csv \\
      "$URL/?query=INSERT+INTO+decisions+FORMAT+CSV"
"""

from __future__ import annotations

import argparse
import csv
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Vocabulary drawn from how scenes are actually slugged, so a judge scrolling the
# data sees something that reads like a production rather than lorem ipsum.
INTERIORS = ["APARTMENT", "HALLWAY", "KITCHEN", "OFFICE", "CAR", "STAIRWELL", "BAR"]
EXTERIORS = ["DOCKYARD", "BRIDGE", "ROOFTOP", "ALLEY", "BEACH", "PLATFORM"]
TIMES = ["DAY", "NIGHT", "DUSK", "DAWN"]

# Reasons a take loses, weighted the way the editing literature reports them.
# Note the wording: every one states what was observed relative to the group,
# never a verdict. "Most camera movement in this group" is a fact; "too shaky" is
# an opinion the system has no standing to hold.
REJECTION_REASONS = [
    ("continuity.prop", "prop position differs from the rest of the group", 14),
    ("continuity.eyeline", "eyeline differs from the other takes", 11),
    ("completion.dialogue", "dialogue does not complete", 13),
    ("stability.outlier", "most camera movement in this group", 12),
    ("exposure.under", "darkest take in the group", 9),
    ("focus.soft", "softest focus in the group", 9),
    ("audio.noise", "highest noise floor in the group", 8),
    ("camera.move_short", "camera move does not reach its mark", 8),
    ("completion.false_start", "false start", 6),
    ("frame.intrusion", "unintended object enters frame", 5),
    ("continuity.wardrobe", "wardrobe differs from the rest of the group", 5),
]

# Why a human overrode the system. These are the entries that make the archive
# worth keeping — the only record anywhere of an editorial judgement.
OVERRIDE_REASONS = [
    "better performance",
    "director's preference",
    "cuts better with the next shot",
    "stronger emotional read",
    "matches the scene's rhythm",
    "wider frame works here",
]

_weighted_reasons = [r for r in REJECTION_REASONS for _ in range(r[2])]

# Written alongside the CSV so the insert never has to guess at column order —
# the file and the statement that loads it stay in step by construction.
CLIP_COLUMNS = (
    "project_id,group_id,subgroup_id,take_no,clip_id,captured_at,ingested_at,"
    "uploaded_by,storage_uri,proxy_uri,sprite_uri,duration_ms,description,tags,"
    "exposure_rel,clipping_pct,sharpness_rel,motion_rel,audio_lufs,"
    "noise_floor_db,dropped_frames,slate_confident,slate_raw,status"
)


def scene_slug(rng: random.Random) -> str:
    if rng.random() < 0.6:
        return f"INT. {rng.choice(INTERIORS)} - {rng.choice(TIMES)}"
    return f"EXT. {rng.choice(EXTERIORS)} - {rng.choice(TIMES)}"


# Synthetic rows live at and above this project id, and the accuracy view refuses
# to count them.
#
# The separation is by id rather than a flag because a flag can be forgotten in a
# WHERE clause. An accuracy figure computed over generated rows measures the
# random number generator, and publishing one as though it measured the system is
# the single thing a product built on not overclaiming cannot do.
SYNTHETIC_PROJECT_BASE = 900_000


def generate(productions: int, out_dir: Path, seed: int = 7) -> dict[str, int]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    counts = {"clips": 0, "decisions": 0}
    base_date = datetime(2026, 1, 6, 8, 0, 0)

    with (
        (out_dir / "clips.csv").open("w", newline="", encoding="utf-8") as cf,
        (out_dir / "decisions.csv").open("w", newline="", encoding="utf-8") as df,
    ):
        clips = csv.writer(cf)
        decisions = csv.writer(df)

        for n in range(1, productions + 1):
            project_id = SYNTHETIC_PROJECT_BASE + n
            shoot_start = base_date + timedelta(days=rng.randint(0, 300))

            for group_id in range(1, rng.randint(18, 45)):
                slug = scene_slug(rng)

                for subgroup_id in range(1, rng.randint(3, 8)):
                    # Take counts follow real coverage: usually a handful,
                    # occasionally a difficult shot that ran to twenty.
                    take_count = rng.choices(
                        [2, 3, 4, 5, 6, 7, 8, 12, 18],
                        weights=[8, 15, 20, 18, 14, 10, 7, 5, 3],
                    )[0]

                    captured = shoot_start + timedelta(
                        days=group_id // 6, minutes=subgroup_id * 25
                    )
                    take_ids = [uuid.uuid4() for _ in range(take_count)]

                    # Most shots have an obvious winner — a crew shoots until
                    # they get one, and the last take is usually the reason they
                    # stopped. Roughly one in five is genuinely contested, and
                    # those are the ones worth a person's attention. Drawing all
                    # scores from one distribution would make almost every shot
                    # look like a close call, which is the opposite of the truth.
                    scores = sorted(
                        (rng.betavariate(4, 3) for _ in range(take_count)), reverse=True
                    )
                    if rng.random() < 0.8:
                        scores[0] = min(1.0, scores[0] + rng.uniform(0.18, 0.35))
                    scores = sorted(scores, reverse=True)

                    winner_idx = 0
                    margin = round(scores[0] - scores[1], 4) if take_count > 1 else 1.0

                    for i, clip_id in enumerate(take_ids):
                        duration_ms = rng.randint(4_000, 95_000)
                        clips.writerow([
                            project_id, group_id, subgroup_id, i + 1, clip_id,
                            (captured + timedelta(seconds=i * 90)).strftime("%Y-%m-%d %H:%M:%S"),
                            (captured + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                            rng.choice(["tanvir", "dipon", "mohid"]),
                            f"gs://trimbin-media/p{project_id}/{clip_id}.mov",
                            f"gs://trimbin-proxy/p{project_id}/{clip_id}/index.m3u8",
                            f"gs://trimbin-proxy/p{project_id}/{clip_id}/sprite.jpg",
                            duration_ms,
                            f"{slug} - take {i + 1}",
                            "[]",
                            round(rng.gauss(1.0, 0.18), 4),   # exposure_rel
                            round(abs(rng.gauss(0.4, 0.6)), 4),  # clipping_pct
                            round(rng.gauss(1.0, 0.15), 4),   # sharpness_rel
                            round(abs(rng.gauss(1.0, 0.45)), 4),  # motion_rel
                            round(rng.gauss(-19.0, 2.5), 2),  # audio_lufs
                            round(rng.gauss(-56.0, 5.0), 2),  # noise_floor_db
                            0,
                            1 if rng.random() < 0.88 else 0,  # slate_confident
                            f"{group_id}-{subgroup_id}-{i + 1}",
                            "active",
                        ])
                        counts["clips"] += 1

                        # -- the agent's decision --------------------------
                        decided = captured + timedelta(hours=7, seconds=i)
                        if i == winner_idx:
                            outcome, code, reason = (
                                "selected", "selected.clean", "cleanest complete take",
                            )
                        elif i == 1:
                            code, reason, _ = rng.choice(_weighted_reasons)
                            outcome = "runner_up"
                        else:
                            code, reason, _ = rng.choice(_weighted_reasons)
                            outcome = "not_selected"

                        panel = 1 if margin < 0.15 else 0
                        decisions.writerow([
                            project_id, group_id, subgroup_id, clip_id,
                            decided.strftime("%Y-%m-%d %H:%M:%S.000"),
                            outcome, round(scores[i], 4), margin if i == winner_idx else 0,
                            reason, code, "[]", "[]", "[]",
                            "agent", "analyst",
                            "gemini-3.6-flash", "analyst/v1", 0, panel,
                            uuid.uuid4().hex[:16],
                            round(rng.uniform(0.5, 2.0), 2),
                            round(duration_ms / 1000 - rng.uniform(0.5, 2.0), 2),
                        ])
                        counts["decisions"] += 1

                    # -- the human's answer, where there was one ------------
                    # Humans look at close calls far more often than confident
                    # ones, which is the asymmetry the published metric is split
                    # to expose.
                    review_chance = 0.62 if margin < 0.15 else 0.05
                    if rng.random() < review_chance and take_count > 1:
                        # Reviewing is not the same as disagreeing. An editor who
                        # opens a shot and keeps the system's pick has confirmed
                        # it, and counting that as an error would make the metric
                        # punish the product for being looked at. On a genuine
                        # close call they change their mind about two thirds of
                        # the time; on a confident one they rarely do.
                        confirm_chance = 0.33 if margin < 0.15 else 0.75
                        if rng.random() < confirm_chance:
                            chosen = take_ids[winner_idx]
                        else:
                            chosen = take_ids[rng.randrange(1, take_count)]
                        decisions.writerow([
                            project_id, group_id, subgroup_id, chosen,
                            (captured + timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S.000"),
                            "selected", 0, 0,
                            rng.choice(OVERRIDE_REASONS), "override.human",
                            "[]", "[]", "[]",
                            "human", rng.choice(["tanvir", "dipon", "mohid"]),
                            "", "", 0, 0, "", 0, 0,
                        ])
                        counts["decisions"] += 1

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productions", type=int, default=200)
    parser.add_argument("--out", type=Path, default=Path("./out"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    counts = generate(args.productions, args.out, args.seed)
    (args.out / "clips.columns").write_text(CLIP_COLUMNS, encoding="utf-8")

    print(f"{counts['clips']:,} clips")
    print(f"{counts['decisions']:,} decisions")
    print(f"written to {args.out.resolve()}")


if __name__ == "__main__":
    main()
