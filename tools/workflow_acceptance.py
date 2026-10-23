"""Create/check a private evidence register. Never turns fixtures into release acceptance."""

import argparse
import hashlib
import json
from pathlib import Path

GATES = (
    "ingest_integrity",
    "real_nemotron_analysis",
    "review_and_retrieval",
    "timeline_persistence",
    "nle_interchange",
    "render_fidelity",
    "project_isolation",
    "cancel_restart_recovery",
    "root_endpoint_remap",
    "backup_restore",
    "held_out_quality",
    "resource_measurements",
)


def template():
    return {
        "schema": "workflow-acceptance-v1",
        "commit": "",
        "corpus_sha256": "",
        "host_description": "",
        "image_digests": {},
        "model_identity": {},
        "gates": {g: {"status": "pending", "evidence": [], "notes": ""} for g in GATES},
    }


def check(record: dict, root: Path) -> list[str]:
    import re

    failures = []
    if record.get("schema") != "workflow-acceptance-v1":
        failures.append("unknown_schema")
    for field, length in (("commit", 40), ("corpus_sha256", 64)):
        if not re.fullmatch(f"[0-9a-f]{{{length}}}", record.get(field, "")):
            failures.append(field + "_missing")
    for field in ("host_description", "image_digests", "model_identity"):
        if not record.get(field):
            failures.append(field + "_missing")
    root = root.resolve()
    for gate in GATES:
        entry = record.get("gates", {}).get(gate, {})
        if entry.get("status") != "passed" or not entry.get("evidence"):
            failures.append(gate + "_pending_or_failed")
            continue
        for item in entry["evidence"]:
            # Evidence is operator-controlled, local and non-symlinked. No downloads.
            name = item.get("path", "")
            path = root / name
            if (
                not name
                or not path.resolve().is_relative_to(root)
                or any(
                    p.is_symlink() or p.is_junction()
                    for p in (path, *path.parents)
                    if p != root
                )
                or not path.is_file()
                or item.get("fixture_only") is not False
            ):
                failures.append(gate + "_invalid_evidence")
                continue
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != item.get(
                    "sha256"
                ):
                    failures.append(gate + "_evidence_changed")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "check"))
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    if args.action == "init":
        args.record.parent.mkdir(parents=True, exist_ok=True)
        with args.record.open("x", encoding="utf8") as handle:
            json.dump(template(), handle, indent=2)
        print("Pending evidence register created; no checks executed.")
    else:
        failures = check(
            json.loads(args.record.read_text(encoding="utf8")), args.record.parent
        )
        print(
            "\n".join(failures)
            if failures
            else "Register complete; human evidence review still required."
        )
        raise SystemExit(bool(failures))
