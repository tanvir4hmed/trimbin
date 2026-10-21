# Grounded evidence workspace

Phase 5 implements `/projects/<slug>/evidence`, linked from the portable media library. It uses PostgreSQL project membership and the new media registry. It does not use the legacy editorial storage or provide a canonical film timeline yet. Manual annotations, placements, corrections, retractions and selections are durable. Observation/slate analysis and selected-text comparison/continuity run through the Phase 4 inference adapter. A model response is a proposal, never an automatic timeline edit.

## Setup and commands

Follow [foundation setup](FOUNDATION_SETUP.md), [media setup](MEDIA_SETUP.md) and [inference setup](INFERENCE_SETUP.md). Apply migrations using `python tools/foundation.py migrate` before starting the API/workers. PostgreSQL 003 and ClickHouse 032 are additive; previously applied migrations remain unchanged. Back up database and media volumes as described in the foundation/media runbooks. No existing project membership or original files are automatically imported from the legacy application.

From `api/`, with the API virtualenv and private configuration available:

```text
python -m app.evidence.worker --env-file ../.secrets/inference/runtime.env
python -m app.evidence.projection --env-file ../.secrets/inference/runtime.env
```

Both commands accept `--once` for operator diagnostics. The projection command exits unsuccessfully if delivery fails, and unacknowledged events remain pending. A worker processes one queued job at a time. The private env must include database/media/session configuration as well as model switches; the Phase 4 example alone does not provision these services.

The portable [Compose package](../deploy/media/compose.yaml) includes API, media worker, analysis worker and outbox projector. Supply an immutable application image plus all private volume/env paths. `TRIMBIN_MODEL_CONFIG_STORE` is a private directory mounted read-only at `/model-config` for API and analysis. Set catalog and embedding identity settings to their container paths. An empty directory is adequate for fixtures, but real inference requires a verified catalog. API and analysis have an egress bridge; database traffic stays on the existing internal network. This grants internet connectivity, not a destination allowlist. The adapter itself restricts the supported provider endpoint. The package creates no paid host, and does not replace existing deployment until cutover.

To build a current semantic snapshot explicitly (requires real credentials and costs tokens):

```text
python -m app.evidence.projection --env-file ../.secrets/inference/runtime.env --build-vectors PROJECT_ID --live
```

Set `TRIMBIN_EVIDENCE_EMBEDDING_IDENTITY_PATH` to a valid private Phase 4 EmbeddingIdentity JSON and configure the matching embedding profile in the model catalog. This command was not executed during Phase 5. Any workspace revision change requires a new semantic snapshot; it is not rebuilt automatically or silently charged. Query embedding also costs tokens. Text search requires no LLM call but does require the current ClickHouse projection.

## Review behavior

1. Index/upload a source in the media library and open Evidence workspace using an authorized project account.
2. Choose a completed source. Add a manual moment/attempt/observation or request visual/slate analysis. The displayed mode is explicit. Development fixture analysis publishes an abstention, not invented observations or a successful provider trace.
3. Correct source-relative ranges/text, accept or retract evidence, and assign scene/shot/take placement. Slate analysis uses the supplied label vocabulary; it does not silently apply model labels to placement.
4. Preview via the scoped proxy ticket and select ranges. Selection stores the effective source hash/range/text and evidence revision. Later changes do not silently update those pinned ranges; remove and reselect to adopt them.
5. Compare selected evidence or request continuity review with a brief. This passes selected text and source intervals to reasoning, not new video/audio analysis. Inspect result/provenance for rankings, findings, abstentions and errors. Comparison proposals do not reorder selections.
6. Search current evidence by text or semantic similarity. API filters also accept source ID and kind. Review counts are bookkeeping, not recall, quality scores or proof of completeness.

Expected revisions reject stale writes. Draft text stays in the page on conflict, and applying it to a newer revision is explicit. API command UUID receipts support exact retries. Browser drafts are not persisted across reloads; do not close the page with unsaved text. A lost network response may require checking current state before repeating an action. No automatic overwrite or blind conflict retry is implemented.

Re-analysis preserves correction overlays. A changed finding has a new generation identity; its old corrected version remains historical for editor reconciliation rather than attaching an old correction to a different assertion. Selected snapshots remain available even if their originating finding becomes historical/retracted. Current search excludes historical and retracted items. Human authority and source provenance take priority over pretending reconciliation is automatic.

## Analysis limits and provenance

Source requests use overlapping windows (default 30 seconds, 2-second overlap) and explicit sampling (default every 2 seconds). Frames are original-detail PNGs, decoded from originals with actual presentation timestamps; proxy frames are not substituted. Sparse frames cannot establish spoken dialogue or exhaustive action coverage. No automatic attempt-boundary model, speech transcription, cross-window finding consolidation or visual comparison pass is claimed. Moments and attempts can be authored/corrected manually.

Bounds: 256 windows per source request, 4,096 sampled frames per run, 32 MiB per frame, 128 MiB raw assets per window, plus the configured model frame/payload/context limits. HDR PQ/HLG analysis is blocked pending a verified color recipe. Unsupported/over-limit work fails visibly; the worker does not silently lower image detail or sample density. Current extraction decodes from the beginning for each frame to preserve PTS, so long footage can be slow. This is not evidence of terabyte throughput or a final production extraction strategy. Quality evaluation must determine appropriate sampling; no default is approved as better than baseline.

Original fingerprints are verified before inference and after processing. Manifests retain frame hashes/timestamps, source identities, configuration/model/prompt/schema versions, output and attempt metadata. Temporary frame derivatives are deleted on normal completion/failure. A process crash may leave its own `analysis/<run>/<lease>` directory for later operator cleanup; never delete originals or another active lease directory.

Jobs have one queue attempt to avoid automatically repeating paid analysis after a crash. Provider retries remain bounded by Phase 4 settings. Heartbeats/cancellation fence publication and further retry calls; an already in-flight network request may complete or time out and incur cost. Only a fully validated generation can become active. Failed, cancelled or superseded runs cannot replace previous complete evidence. An explicit successful abstention is a complete result, not a failure.

## Retrieval limits

PostgreSQL is authoritative. A transactional outbox projects complete snapshots into self-hosted ClickHouse. Delivery acknowledges only after insert; duplicate events remain safe, and old events rebuild the latest revision instead of replacing it with an old state. Retrieval uses separate SELECT-only credentials and parameterized project/revision filters. Missing/stale projections or unavailable services return an error, never an empty successful fallback.

Workspace evidence is bounded to 5,000 visible items and selections to 256. A comparison accepts 1–32 selected ranges. Text/vector snapshot payloads are capped at 16 MiB below the reader result limit. Semantic snapshots support 1–1,000 current items with exact cosine scoring; no ANN scalability claim. Embeddings preserve complete identity and query/corpus compatibility. Build failure keeps previous snapshots, but an old revision cannot answer a current query. No automatic deletion of historical runs or pinned evidence is implemented; plan backup/storage retention before production.

## Acceptance still pending

Runtime tests, database/container migration and role checks, outbox recovery, actual FFmpeg PTS extraction, browser conflict/retry handling, real model/embedding calls and held-out quality evaluation were deferred at the owner's request. Static checks alone do not establish any of these. Test sources were added for command/revision/scope/fencing and window behavior, and the database tests are wired into the existing CI foundation rehearsal. No passing CI or deployment result is claimed. Phase 6 will consume selected ranges into a canonical timeline; editable export and original-resolution rendering remain Phases 7 and 8.
