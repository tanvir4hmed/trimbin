"""Idempotent complete ClickHouse snapshots; retrieval has SELECT-only credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import clickhouse_connect
from trimbin_agents.config import placeholder

from ..config import Settings
from ..inference.contracts import EmbeddingIdentity, fingerprint
from ..inference.provider import load_catalog
from ..inference.runner import embed
from .contracts import EvidenceError, Search
from .store import KIND, EvidenceStore


def client(config: Settings, *, writer: bool = False):
    user = config.clickhouse_user if writer else config.clickhouse_reader_user
    password = config.clickhouse_password if writer else config.clickhouse_reader_password
    if (
        not config.clickhouse_host
        or placeholder(password)
        or not user
        or user == "default"
        or config.clickhouse_user == config.clickhouse_reader_user
    ):
        raise EvidenceError("search_not_configured")
    return clickhouse_connect.get_client(
        host=config.clickhouse_host,
        port=config.clickhouse_port,
        username=user,
        password=password,
        secure=config.clickhouse_secure,
        connect_timeout=10,
        send_receive_timeout=30,
    )


def eligible(snapshot: dict) -> list[dict]:
    return [row for row in snapshot["items"] if row["current"] and row["decision"] != "retracted"]


def deliver(config: Settings, limit: int = 20) -> int:
    store = EvidenceStore(config.database_url)
    with store.connection() as conn:
        events = conn.execute(
            "SELECT event_id,project_id FROM outbox WHERE delivered_at IS NULL "
            "AND payload->>'kind'=%s ORDER BY created_at LIMIT %s",
            (KIND, limit),
        ).fetchall()
    delivered = 0
    for event in events:
        snapshot = store.snapshot(event["project_id"])
        # Rebuild from the latest authoritative revision; delayed events cannot revert it.
        payload = json.dumps({"items": eligible(snapshot)}, separators=(",", ":"))
        if len(payload.encode()) > 16 * 1024**2:
            raise EvidenceError("projection_size_limit")
        archive = client(config, writer=True)
        try:
            archive.insert(
                "portable_evidence_snapshots",
                [[event["project_id"], snapshot["revision"], event["event_id"], payload]],
                column_names=["project_id", "revision", "event_id", "payload"],
            )
        finally:
            archive.close()
        with store.connection() as conn:
            conn.execute(
                "UPDATE outbox SET delivered_at=clock_timestamp() WHERE event_id=%s",
                (event["event_id"],),
            )
        delivered += 1
    return delivered


def embedding_identity(config: Settings) -> EmbeddingIdentity:
    if not config.evidence_embedding_identity_path:
        raise EvidenceError("semantic_index_not_configured")
    try:
        path = Path(config.evidence_embedding_identity_path)
        if path.stat().st_size > 65536:
            raise ValueError("Oversized identity")
        return EmbeddingIdentity.model_validate_json(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError("invalid_embedding_identity") from exc


async def build_vectors(config: Settings, project: int) -> dict:
    store = EvidenceStore(config.database_url)
    snapshot = await asyncio.to_thread(store.snapshot, project)
    rows = eligible(snapshot)
    if not rows or len(rows) > 1000:
        raise EvidenceError("semantic_index_requires_1_to_1000_items")
    identity = embedding_identity(config)
    catalog = load_catalog(config.inference_catalog_path)
    vectors, runs = [], []
    for offset in range(0, len(rows), 128):
        result = await embed(
            [r["text"] for r in rows[offset : offset + 128]],
            identity,
            config,
            catalog,
            project_id=project,
        )
        vectors.extend(result.pop("vectors"))
        runs.append(result)
    if (await asyncio.to_thread(store.snapshot, project))["revision"] != snapshot["revision"]:
        raise EvidenceError("workspace_changed_during_index_build")
    payload = json.dumps(
        {"identity": identity.model_dump(), "items": rows, "vectors": vectors, "runs": runs},
        separators=(",", ":"),
    )
    if len(payload.encode()) > 16 * 1024**2:
        raise EvidenceError("projection_size_limit")

    def save():
        archive = client(config, writer=True)
        try:
            archive.insert(
                "portable_vector_snapshots",
                [[project, snapshot["revision"], fingerprint(identity.model_dump()), payload]],
                column_names=["project_id", "revision", "identity", "payload"],
            )
        finally:
            archive.close()

    await asyncio.to_thread(save)
    return {"revision": snapshot["revision"], "items": len(rows), "quality_status": "not_evaluated"}


def load_snapshot(config: Settings, project: int, revision: int, identity: str | None = None):
    archive = client(config)
    try:
        table = "portable_vector_snapshots" if identity else "portable_evidence_snapshots"
        where = " AND identity={identity:String}" if identity else ""
        result = archive.query(
            f"SELECT payload FROM {table} WHERE project_id={{project:Int64}} "
            f"AND revision={{revision:UInt64}}{where} LIMIT 1",
            parameters={"project": project, "revision": revision, "identity": identity or ""},
        )
        if not result.result_rows:
            raise EvidenceError(
                "semantic_index_pending" if identity else "search_projection_pending"
            )
        return json.loads(result.result_rows[0][0])
    finally:
        archive.close()


async def search(config: Settings, project: int, query: Search) -> dict:
    state = await asyncio.to_thread(EvidenceStore(config.database_url).snapshot, project)
    identity = embedding_identity(config) if query.mode == "semantic" else None
    try:
        snapshot = await asyncio.to_thread(
            load_snapshot,
            config,
            project,
            state["revision"],
            fingerprint(identity.model_dump()) if identity else None,
        )
    except EvidenceError:
        raise
    except Exception as exc:
        raise EvidenceError("search_archive_unavailable") from exc
    vector = None
    if identity:
        identity.require_compatible(EmbeddingIdentity.model_validate(snapshot["identity"]))
        result = await embed(
            [query.query],
            identity,
            config,
            load_catalog(config.inference_catalog_path),
            project_id=project,
        )
        vector = result["vectors"][0]
    matches = []
    for index, item in enumerate(snapshot["items"]):
        if query.source_id and item["source_id"] != str(query.source_id):
            continue
        if query.kind and item["kind"] != query.kind:
            continue
        if vector is None:
            terms = query.query.casefold().split()
            score = (
                sum(term in item["text"].casefold() for term in terms) / len(terms) if terms else 0
            )
            if score == 0:
                continue
        else:
            other = snapshot["vectors"][index]
            if len(other) != len(vector):
                raise EvidenceError("semantic_index_invalid")
            denominator = math.sqrt(sum(v * v for v in vector) * sum(v * v for v in other))
            if denominator == 0 or not math.isfinite(denominator):
                raise EvidenceError("semantic_index_invalid")
            score = sum(a * b for a, b in zip(vector, other, strict=True)) / denominator
        matches.append({**item, "score": score})
    # A correction during the remote query must not return a stale successful answer.
    if (await asyncio.to_thread(EvidenceStore(config.database_url).snapshot, project))[
        "revision"
    ] != state["revision"]:
        raise EvidenceError("search_projection_pending")
    return {
        "revision": state["revision"],
        "mode": query.mode,
        "items": sorted(matches, key=lambda r: (-r["score"], r["id"]))[: query.limit],
        "quality_status": "not_evaluated",
    }


async def main(config, once=False):
    while True:
        try:
            count = await asyncio.to_thread(deliver, config)
        except Exception:
            # Retain unacknowledged events. Never log credential-bearing client exceptions.
            print("Evidence projection unavailable; unacknowledged events retained.", flush=True)
            if once:
                raise SystemExit(1) from None
            count = 0
        if once:
            return
        if not count:
            await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--build-vectors", type=int, metavar="PROJECT")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    config = Settings(_env_file=args.env_file)
    if args.build_vectors:
        if not args.live:
            parser.error("Vector construction requires explicit --live and real credentials")
        try:
            print(json.dumps(asyncio.run(build_vectors(config, args.build_vectors))))
        except Exception:
            raise SystemExit("Vector construction unavailable; prior index preserved.") from None
    else:
        asyncio.run(main(config, args.once))
