# Data, timing and recovery contract

Phase 1 design for implementation in Phases 2–8. Existing second-based APIs remain unchanged until explicit adapters and migration checks exist. The examples describe the proposed v1 contract.

## Ownership

| Entity | Authority | Identity and invariants |
| --- | --- | --- |
| Project/membership | PostgreSQL | Project-scoped authorization on every API, worker and media operation |
| Source asset/version | PostgreSQL | Stable asset ID plus immutable version; root alias + relative path, content hash, size and measured stream metadata |
| Derivative | PostgreSQL registry + filesystem | Source version, recipe version, mapping metadata and complete/failed status; never an original substitute |
| Analysis generation | PostgreSQL lifecycle; ClickHouse evidence | Run ID, complete manifest and task/model/configuration identities |
| Human correction/selection | PostgreSQL + transactional outbox | Revision, actor, command receipt and exact evidence/source reference |
| Timeline revision | PostgreSQL | Immutable snapshot; optimistic current-revision pointer |
| Evidence/search projection | ClickHouse | Idempotent generation/event identities; scoped read-only retrieval |
| Jobs/export artifacts | PostgreSQL + filesystem | Durable lease, attempt, cancellation, pinned inputs and output checksum |

ClickHouse retains measured facts, observations, transcripts, moments, attempt proposals, comparison reasons and searchable evidence. It does not decode, store video bytes or play a timeline. PostgreSQL governs edit transactions, saved revisions and recovery. Short-lived diagnostics/activity may expire; evidence referenced by a saved edit or export must remain resolvable.

## Source and timeline timing

Store rational rates as positive integer numerator/denominator pairs, reduced to canonical form. Store timestamps as integer ticks with a rational seconds-per-tick timebase. Reject nonfinite values, negative durations, reversed ranges and project/source mismatches. Do not persist frame locations as repeatedly rounded decimal seconds.

For constant-rate media, source frame index `i` maps to `i * fps_den / fps_num` seconds from the registered video origin. Preserve source stream start PTS, camera timecode and drop-frame flag separately. Camera timecode labels are not elapsed seconds. For variable-rate sources, retain indexed frame presentation timestamps; do not multiply average FPS to infer a frame. Until a tested VFR conform path exists, block timeline export/render for those sources rather than approximating silently.

Ranges are half-open `[in, out)`: first included frame and first excluded frame. A range must contain at least one video frame and stay inside the measured source. Source timestamps and sequence timestamps have different timebases.

Sequence v1 contains a single gapless video cut track and linked source audio. It records schema version, project/sequence ID, revision, resolution, rational FPS, SDR color settings, audio sample rate and ordered occurrences. Each occurrence contains:

- Unique occurrence ID, source ID/version and source in/out frame indices.
- Integer sequence start/duration frames, explicit conform policy and audio link.
- Referenced attempt/evidence revisions, editor note, mute and finite basic gain.
- Audio stream/channel selection and measured source-to-video timestamp offset.

The initial mixed-rate policy preserves source playback speed and conforms by frame duplication/drop, without optical flow. Compute each duration once with exact rational arithmetic and nearest-frame rounding (positive half ties upward); record it in the snapshot. Sequence starts are cumulative stored durations. A nonempty source range that rounds to zero sequence frames is rejected. Show the quantization delta; it must not exceed half a sequence frame. Preview, XML and render must follow the same mapping, not independently choose durations. Mixed-rate export remains blocked until Phase 7/8 parity tests pass.

For output frame `k` of an occurrence, sample the source frame containing time `source_in_time + k / sequence_fps`, clamped to the included source range. Linked audio follows the same occurrence duration and measured timestamp offset; resample to the explicit sequence rate. Handling of endpoint padding/trimming must be identical between conform and render and reported where NLE import differs.

Example: at 24000/1001 FPS, source frames `[240,480)` are 240 frames, or 10.01 seconds. On a 24 FPS sequence this becomes 240 frames, or 10 seconds, under the declared rounding rule. Repeating that source creates a second occurrence with a new ID and sequence start 240; it does not reuse the first occurrence's identity.

## Revision and API semantics

New mutation commands carry `command_id` and `expected_revision`. In one transaction, authorize, validate all references, compare the current revision, store the new snapshot, insert the command receipt and outbox events. Replaying the same command/body returns the original result. Reusing a command ID with a different body is a conflict. A stale expected revision returns HTTP 409 and current revision metadata; the client retains its draft.

Proposed API resources under `/v1/projects/{project_id}`:

| Operation | Resource | Result |
| --- | --- | --- |
| Register staged/allowed media | `POST /sources` | Asset and indexing job; validated server-relative root |
| Request analysis | `POST /sources/{id}/analysis` | Run/job IDs and selected configuration |
| Save timeline | `POST /sequences/{id}/revisions` | Immutable revision or conflict |
| Read revision | `GET /sequences/{id}/revisions/{rev}` | Snapshot and source availability |
| Export revision | `POST /sequences/{id}/revisions/{rev}/exports` | Preflight result and job ID |
| Observe/cancel job | `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | Scoped status or cancellation receipt |

These are proposed contracts, not existing endpoints. Keep old routes through an explicit compatibility adapter while consumers migrate. Conversion from old seconds requires source metadata and a recorded rounding report; missing metadata blocks migration of that item.

## Durable work

Jobs transition `queued → running → succeeded / failed / cancelled`; retryable failures return to queued within a bounded attempt policy. Workers claim with transactional row locking, owner/lease token and expiry. Heartbeats extend a lease. Completion requires the current lease token, so a stale worker cannot publish over a recovered job.

Outbox consumers tolerate duplicate delivery. An event ID identifies one projection update; retries cannot count it twice. ClickHouse queries must use the completed generation and deduplicated/latest event view, not assume insert deduplication alone guarantees exactly-once delivery.

Write output to a job-owned temporary path, verify it, then atomically publish on the same filesystem. Recovery handles a file published before the database receipt using the job identity and checksum. Cancellation races resolve transactionally: a succeeded artifact remains succeeded; cancellation never deletes an already delivered artifact or an original.

## Retention and migration

Retain current valid evidence, human corrections, all saved revisions needed by users and every pinned export dependency. History is not required to run inference on each playback. UI pagination (for example twenty visible versions) is not a retention policy. Purge only unreferenced derivatives/diagnostics through a dry-run reference report and an explicit retention policy.

Migrate in dependency order: projects and memberships → source versions → evidence generations → corrections/selections → timeline revisions → outstanding jobs. Preserve old IDs through a mapping table; compare counts and reference integrity before switching readers. Failed runs never become the active complete generation. Keep old data/configuration until a verified cutover and rollback decision. No remote deletion is part of Phase 1.

## Implemented Phase 5 evidence state

PostgreSQL migration 003 adds immutable evidence items, analysis run manifests/results, run/item associations and latest-request fences. The `evidence_workspace/current` revisioned document stores active scope heads, manual note IDs, correction overlays, selected effective snapshots and source scene/shot/take placements. Every editor command includes project membership, actor, command UUID and expected revision. A receipt replays the exact command; a changed payload or stale revision conflicts. State, version, receipt and outbox event commit atomically.

A correction cannot switch the source or exceed its registered duration. A later decision-only correction preserves earlier text/range edits. Selection pins effective evidence, source hash, range and evidence revision; later retraction or correction does not silently change that saved selection. Re-analysis never rewrites overlays. Changed model findings get new identities including generation provenance; old corrected findings remain historical for explicit reconciliation. Identical output is not assumed semantically equivalent across generations.

Analysis publishes only after every requested window validates and the worker still holds its lease. A newer request prevents an older completed run becoming active. Failed/cancelled work preserves the previous head. The complete input manifests include actual sampled frame timestamps/hashes, task output, model/prompt/schema identity and retry metadata. Comparisons use pinned selected text; automatic speech or exhaustive attempt segmentation is not implemented.

ClickHouse migration 032 stores complete project/revision snapshots. Transactional outbox delivery is retryable and reader credentials are SELECT-only. Queries require the current PostgreSQL revision and a compatible embedding identity; stale/missing data cannot masquerade as an empty successful search. Whole-snapshot limits and exact cosine scoring are bounded PoC behavior, not a production ANN or terabyte benchmark. [Evidence setup](EVIDENCE_SETUP.md) records the operational limits.
