"""Operator commands for deferred discovery, explicit fixtures and bounded live evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..media.files import MediaPaths, digest_file, safe_path
from ..media.store import MediaStore
from .contracts import EmbeddingIdentity, TaskRequest, fingerprint
from .evaluation import EvaluationManifest, Scores, blind_pairs, paired_report
from .provider import InferenceError, TokenFactory, live_preflight, load_catalog
from .runner import embed, run_task


def read_json(path: str, limit: int = 8 * 1024**2):
    file = Path(path)
    if file.stat().st_size > limit:
        raise InferenceError("input_file_too_large")
    return json.loads(file.read_text("utf-8"))


def save_private(directory: Path, name: str, value: object) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    return target


def verify_registered_sources(request: TaskRequest, config: Settings) -> None:
    """Operator-only CLI: project/hash scope is resolved from the durable source registry."""
    paths, store = MediaPaths(config), MediaStore(config.database_url)
    for source in request.sources:
        row = store.get(request.project_id, source.id)
        if row["state"] != "succeeded" or row["fingerprint"] != source.sha256:
            raise InferenceError("source_version_unavailable")
        duration = row["metadata"]["duration"]
        exact = Fraction(duration["numerator"], duration["denominator"]) * 1_000_000
        if source.duration_us != -(-exact.numerator // exact.denominator):
            raise InferenceError("source_duration_mismatch")
        path = paths.resolve(request.project_id, row["root_alias"], row["relative_path"])
        if digest_file(path) != source.sha256:
            raise InferenceError("source_changed")


async def execute(args: argparse.Namespace, config: Settings) -> tuple[object, int]:
    if args.command == "discover":
        if not args.live:
            raise InferenceError("explicit_live_flag_required")
        return {"models": await TokenFactory(config).discover(), "capabilities_verified": False}, 0
    if args.command == "evaluate":
        manifest = EvaluationManifest.model_validate(read_json(args.manifest))
        scores = Scores.model_validate(read_json(args.scores))
        report = paired_report(manifest, scores, args.split)
        return report, int(report["status"] == "failed")
    if args.command == "freeze":
        manifest = EvaluationManifest.model_validate(read_json(args.manifest))
        return {
            "manifest": manifest.model_dump(mode="json"),
            "manifest_sha256": fingerprint(manifest.model_dump(mode="json")),
        }, 0
    if args.command == "blind":
        baseline, candidate = read_json(args.baseline), read_json(args.candidate)
        review, key = blind_pairs(baseline, candidate, args.seed)
        # The caller writes the key separately; never send it to blind reviewers.
        return {"review": review, "private_key": key}, 0
    if args.command == "embed":
        if not args.live:
            raise InferenceError("explicit_live_flag_required")
        identity = EmbeddingIdentity.model_validate(read_json(args.identity))
        return await embed(
            read_json(args.texts),
            identity,
            config,
            load_catalog(config.inference_catalog_path),
            project_id=args.project,
        ), 0
    request = TaskRequest.model_validate(read_json(args.request))
    if args.command == "fingerprint":
        return {"input_fingerprint": fingerprint(request.model_dump(mode="json"))}, 0
    if config.inference_mode == "nebius":
        if not args.live:
            raise InferenceError("explicit_live_flag_required")
        live_preflight(config)
        verify_registered_sources(request, config)
    fixture = read_json(args.fixture) if args.fixture else None
    assets = {}
    if config.inference_mode != "fixture":
        if request.frames and not args.asset_root:
            raise InferenceError("frame_asset_root_required")
        root = Path(args.asset_root or ".").resolve()
        # Content-addressed filenames only. No caller URLs or arbitrary file references.
        total = 0
        for frame in request.frames:
            path = safe_path(root, frame.sha256 + (".png" if frame.mime == "image/png" else ".jpg"))
            total += path.stat().st_size
            if total > 128 * 1024**2:
                raise InferenceError("frame_asset_limit_exceeded")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != frame.sha256:
                raise InferenceError("frame_hash_mismatch")
            assets[frame.id] = data
    catalog = (
        load_catalog(config.inference_catalog_path) if config.inference_mode == "nebius" else {}
    )
    result = await run_task(request, assets, config, catalog, fixture=fixture)
    return result, int(result["status"] not in {"fixture", "validated"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output-root", default="../.secrets/inference")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover").add_argument("--live", action="store_true")
    run = commands.add_parser("run")
    run.add_argument("--request", required=True)
    run.add_argument("--asset-root")
    run.add_argument("--fixture")
    run.add_argument("--live", action="store_true")
    commands.add_parser("fingerprint").add_argument("--request", required=True)
    commands.add_parser("freeze").add_argument("--manifest", required=True)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--manifest", required=True)
    evaluation.add_argument("--scores", required=True)
    evaluation.add_argument("--split", choices=["development", "held_out"], required=True)
    embedding = commands.add_parser("embed")
    embedding.add_argument("--identity", required=True)
    embedding.add_argument("--texts", required=True)
    embedding.add_argument("--project", required=True, type=int)
    embedding.add_argument("--live", action="store_true")
    blind = commands.add_parser("blind")
    blind.add_argument("--baseline", required=True)
    blind.add_argument("--candidate", required=True)
    blind.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    output = Path(args.output_root).resolve()
    if ".secrets" not in output.parts:
        parser.error("Private run artifacts must be under an ignored .secrets directory")
    try:
        config = Settings(_env_file=args.env_file)
        result, code = asyncio.run(execute(args, config))
        run_id = str(uuid4())
        if args.command == "blind":
            save_private(output, f"{run_id}-private-key.json", result["private_key"])
            result = result["review"]
        path = save_private(output, f"{run_id}-{args.command}.json", result)
        print(f"Private artifact saved: {path.name}")
        return code
    except InferenceError as exc:
        print(json.dumps({"status": "unavailable", "error_code": exc.code}))
        return 2
    except Exception:
        # Raw validation/provider exceptions can include private text or credentials.
        print(json.dumps({"status": "failed", "error_code": "invalid_input_or_runtime"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
