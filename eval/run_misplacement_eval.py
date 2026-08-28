"""Can an embedding tell that a clip was filed in the wrong setup?

The Slate Agent proposes a move when a clip does not resemble the group it was
filed in. That proposal is only worth showing an editor if it is right far more
often than it is wrong, and until this ran nobody had checked — the threshold in
the agent carried a comment saying it was tuned on an eval set, and no such eval
existed.

The test is built by lying to the system. Every take is filed into a group it
does not belong to, and we count how many of those the check catches. The other
half matters more: every take is also scored against the group it genuinely
belongs to, and a check that flags one of those is worse than useless — an
editor told three times that a correctly filed take is misplaced stops reading
the fourth.

Two ways of asking are compared:

    absolute   is the similarity below a fixed number
    relative   is it low compared to how this group's own members score

The second is how every other measurement in this system works. The first is
what the agent currently does.

    python run_misplacement_eval.py --dataset ../../Editorial_AI_Dataset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))

from trimbin_agents.config import settings  # noqa: E402

# Frames sampled per take, spread across it.
#
# One frame is whatever happened to be on screen at that second — an actor
# turning, a hand crossing the lens — and two takes of one setup can differ more
# at one instant than two setups differ on average. Five costs five embedding
# calls and describes the take rather than a moment in it.
FRAMES_PER_TAKE = 5
FRAME_INTERVAL_S = 12
FRAME_HEIGHT = 360


@dataclass
class Take:
    key: str
    scene: str
    setup: str
    take_no: int
    embedding: list[float] = field(default_factory=list)

    @property
    def group(self) -> str:
        return f"{self.scene}{self.setup}"


def parse(path: Path) -> Take | None:
    name = path.stem
    if "Take_" not in name:
        return None
    scene = "S1" if "DoP_C" in name else "S2"
    setup = "A" if "Female" in name else "B"
    take_no = int(name.split("Take_")[1][0])
    return Take(key=f"{scene}{setup}t{take_no}", scene=scene, setup=setup, take_no=take_no)


def frames_for(source: Path, into: Path) -> list[Path]:
    into.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-vf", f"fps=1/{FRAME_INTERVAL_S},scale=-2:{FRAME_HEIGHT}",
            "-frames:v", str(FRAMES_PER_TAKE),
            str(into / "f_%d.jpg"),
        ],
        check=True,
    )
    return sorted(into.glob("*.jpg"))


def mean(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def cosine(a: list[float], b: list[float]) -> float:
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


async def embed_takes(dataset: Path, work: Path) -> list[Take]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True, project=settings.project_id, location=settings.model_location
    )

    takes: list[Take] = []
    for project in sorted((dataset / "projects").iterdir()):
        if not project.name.startswith(("P001", "P002")):
            continue
        for source in sorted((project / "takes").glob("*.mov")):
            take = parse(source)
            if take is None:
                continue
            vectors = []
            for frame in frames_for(source, work / take.key):
                response = await client.aio.models.embed_content(
                    model=settings.embedding_model,
                    contents=[
                        types.Part.from_bytes(
                            data=frame.read_bytes(), mime_type="image/jpeg"
                        )
                    ],
                    config=types.EmbedContentConfig(
                        output_dimensionality=settings.embedding_dimensions
                    ),
                )
                vectors.append(response.embeddings[0].values)
            take.embedding = mean(vectors)
            takes.append(take)
            print(f"  {take.key}  {len(vectors)} frames")
    return takes


def evaluate(takes: list[Take]) -> dict:
    groups: dict[str, list[Take]] = defaultdict(list)
    for t in takes:
        groups[t.group].append(t)

    def centroid(group: str, without: str | None = None) -> list[float]:
        return mean([t.embedding for t in groups[group] if t.key != without])

    # How a genuine member scores against its own group, with itself left out of
    # the centroid — otherwise it is partly compared against itself.
    belongs = {t.key: cosine(t.embedding, centroid(t.group, without=t.key)) for t in takes}
    group_median = {
        g: statistics.median([belongs[t.key] for t in ts]) for g, ts in groups.items()
    }

    intruders = []
    for t in takes:
        for group in groups:
            if group == t.group:
                continue
            similarity = cosine(t.embedding, centroid(group))
            intruders.append({
                "take": t.key,
                "filed_into": group,
                "same_scene": group[:2] == t.scene,
                "similarity": similarity,
                "relative": similarity / group_median[group],
            })

    members = [
        {
            "take": t.key,
            "group": t.group,
            "similarity": belongs[t.key],
            "relative": belongs[t.key] / group_median[t.group],
        }
        for t in takes
    ]

    # The only threshold that costs nothing: just under the lowest score a
    # genuine member reaches. Anything higher flags footage sitting exactly
    # where it belongs.
    safe_absolute = min(m["similarity"] for m in members)
    safe_relative = min(m["relative"] for m in members)

    def recall(field: str, threshold: float, same_scene_only: bool) -> list[int]:
        pool = [i for i in intruders if i["same_scene"]] if same_scene_only else intruders
        return [sum(1 for i in pool if i[field] < threshold), len(pool)]

    return {
        "takes": len(takes),
        "groups": len(groups),
        "frames_per_take": FRAMES_PER_TAKE,
        "embedding_model": settings.embedding_model,
        "members": members,
        "intruders": intruders,
        "safe_threshold": {"absolute": safe_absolute, "relative": safe_relative},
        "recall_at_safe_threshold": {
            "absolute_all": recall("similarity", safe_absolute, False),
            "absolute_same_scene": recall("similarity", safe_absolute, True),
            "relative_all": recall("relative", safe_relative, False),
            "relative_same_scene": recall("relative", safe_relative, True),
        },
    }


def report(result: dict) -> None:
    print(f"\n{result['takes']} takes across {result['groups']} setups")
    print(f"{result['embedding_model']}, {result['frames_per_take']} frames averaged per take\n")

    print("Correctly filed takes, scored against their own setup:")
    for m in sorted(result["members"], key=lambda m: m["similarity"]):
        print(
            f"  {m['take']:<8} in {m['group']:<5} "
            f"similarity {m['similarity']:.3f}   relative {m['relative']:.3f}"
        )

    same = [i for i in result["intruders"] if i["same_scene"]]
    cross = [i for i in result["intruders"] if not i["same_scene"]]
    print(f"\nIntruders: {len(same)} within a scene, {len(cross)} across scenes.")
    print("Within a scene is the case that matters: two setups shot the same day,")
    print("same room, same actors, and a folder dragged into the wrong one.\n")

    for label, pool in (("within a scene", same), ("across scenes", cross)):
        sims = [i["similarity"] for i in pool]
        rels = [i["relative"] for i in pool]
        print(
            f"  {label:<16} similarity  min {min(sims):.3f}  "
            f"mean {sum(sims)/len(sims):.3f}  max {max(sims):.3f}"
        )
        print(
            f"  {'':<16} relative    min {min(rels):.3f}  "
            f"mean {sum(rels)/len(rels):.3f}  max {max(rels):.3f}"
        )

    st = result["safe_threshold"]
    print("\nHighest threshold that flags no correctly filed take:")
    print(f"  absolute {st['absolute']:.3f}   relative {st['relative']:.3f}")

    print("\nWhat that catches, with zero false alarms:")
    for name, (caught, total) in result["recall_at_safe_threshold"].items():
        pct = 100 * caught / total if total else 0.0
        print(f"  {name:<24} {caught:>3}/{total:<3}  {pct:5.1f}%")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("./misplacement_eval.json"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        print("Embedding takes...")
        takes = await embed_takes(args.dataset, Path(tmp))

    if len(takes) < 4:
        print("Not enough takes to compare groups.", file=sys.stderr)
        return 1

    result = evaluate(takes)
    report(result)

    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWritten to {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
