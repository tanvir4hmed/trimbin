"""Write evaluation results to the archive, so the public page shows measurement.

This is the one number on the site that is genuinely earned. The synthetic corpus
proves the queries stay fast; it proves nothing about whether the system finds
faults, because the faults in it were invented by the same script that invented
the findings.

These rows come from footage with a fault planted at a timecode we chose. If the
system reports camera shake at 4.2 seconds, that is a fact — we put it there.

    python run_measurement_eval.py --clips fixtures/clips --json results.json
    python publish_results.py --results results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import urllib.request


def rows_from(results: list[dict], run_at: str, model: str, prompt: str) -> list[str]:
    """One CSV line per axis per fixture.

    Every case is written, including the ones the system got right on a control
    clip where nothing was planted. Dropping those would leave only the hits and
    turn a measurement into a highlight reel — false alarms are half of what this
    table exists to expose.
    """
    lines = []
    for case in results:
        lines.append(
            ",".join([
                run_at,
                f'"{case["fixture_id"]}"',
                f'"{case["axis"]}"',
                "1" if case["expected"] else "0",
                "1" if case["detected"] else "0",
                str(case["expected_start_s"]),
                str(case["detected_start_s"]),
                "1" if case["within_tolerance"] else "0",
                f'"{model}"',
                f'"{prompt}"',
            ])
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument(
        "--model",
        default="ffmpeg-deterministic",
        help="What produced these findings. The measurement layer is not a model, "
             "and recording it as one would obscure where the accuracy came from.",
    )
    parser.add_argument("--prompt-version", default="measurement/v1")
    parser.add_argument("--replace", action="store_true", help="Clear previous runs first")
    args = parser.parse_args()

    url = os.environ.get("CLICKHOUSE_URL")
    password = os.environ.get("CLICKHOUSE_PASSWORD")
    if not url or not password:
        print("CLICKHOUSE_URL and CLICKHOUSE_PASSWORD are required", file=sys.stderr)
        return 1

    results = json.loads(args.results.read_text(encoding="utf-8"))
    run_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def send(query: str, body: bytes = b"") -> str:
        request = urllib.request.Request(
            f"{url}/?query={quote(query)}&wait_end_of_query=1",
            data=body,
            method="POST",
        )
        import base64

        token = base64.b64encode(f"default:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode()

    if args.replace:
        # A published figure should reflect the current code, not an average of
        # every version that ever ran.
        send("TRUNCATE TABLE eval_results")

    lines = rows_from(results, run_at, args.model, args.prompt_version)
    send("INSERT INTO eval_results FORMAT CSV", "\n".join(lines).encode())

    print(f"{len(lines)} cases published")
    print(send("SELECT * FROM eval_accuracy FORMAT TSVWithNames"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
