# Data, timing and recovery contract

Current data/timing contract, reconciled 23 October 2026. PostgreSQL, self-hosted ClickHouse and filesystem media are deployed. Retained second-based Film API calls translate to the same canonical frame timeline. Normative invariants below are distinguished from the tested subset in [cutover evidence](AWS_CUTOVER.md).

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

Current API routes (the public gateway adds `/api`; the application itself has no `/v1` prefix):

| Operation | Application route |
| --- | --- |
| Register allowed mounted source | `POST /media-library/{project}/sources` |
| Begin/resume/complete upload | `/media-library/{project}/uploads` and its upload-ID routes |
| Analyze registered evidence | `POST /evidence/{project}/analyze` |
| Verify source timing | `POST /timelines/{project}/sources/{source_id}/timing` |
| Save/read timeline | `POST /timelines/{project}/{sequence_id}/revisions`, `GET /timelines/{project}/{sequence_id}?revision=N` |
| Export editable revision | `POST /editable-exports/{project}/sequences/{sequence_id}` |
| Render saved revision | `POST /renders/{project}/sequences/{sequence_id}` |
| Observe/cancel export work | Sequence job listings and `/editable-exports` or `/renders` project/job cancellation routes |

The old Film API remains a compatibility facade, not a second writable state. Conversion from seconds requires verified source timing; invalid later ranges roll back the complete command. See the API OpenAPI schema and setup guides for request bodies rather than inventing a second interface.

## Durable work

Jobs transition `queued → running → succeeded / failed / cancelled`; retryable failures return to queued within a bounded attempt policy. Workers claim with transactional row locking, owner/lease token and expiry. Heartbeats extend a lease. Completion requires the current lease token, so a stale worker cannot publish over a recovered job.

Outbox consumers tolerate duplicate delivery. An event ID identifies one projection update; retries cannot count it twice. ClickHouse queries must use the completed generation and deduplicated/latest event view, not assume insert deduplication alone guarantees exactly-once delivery.

Write output to a job-owned temporary path, verify it, then atomically publish on the same filesystem. Recovery handles a file published before the database receipt using the job identity and checksum. Cancellation races resolve transactionally: a succeeded artifact remains succeeded; cancellation never deletes an already delivered artifact or an original.

## Retention and migration

Retain current valid evidence, human corrections, all saved revisions needed by users and every pinned export dependency. History is not required to run inference on each playback. UI pagination (for example twenty visible versions) is not a retention policy. Purge only unreferenced derivatives/diagnostics through a dry-run reference report and an explicit retention policy.

Migrate in dependency order: projects and memberships → source versions → evidence generations → corrections/selections → timeline revisions → outstanding jobs. Preserve old IDs through a mapping table; compare counts and reference integrity before switching readers. Failed runs never become the active complete generation. Keep old data/configuration until a verified cutover and rollback decision. No historical corpus was available to import during the AWS cutover; do not interpret a fresh owner workspace as migrated movie data. Retired configuration was hash-preserved outside Git.

## Implemented Phase 5 evidence state

PostgreSQL migration 003 adds immutable evidence items, analysis run manifests/results, run/item associations and latest-request fences. The `evidence_workspace/current` revisioned document stores active scope heads, manual note IDs, correction overlays, selected effective snapshots and source scene/shot/take placements. Every editor command includes project membership, actor, command UUID and expected revision. A receipt replays the exact command; a changed payload or stale revision conflicts. State, version, receipt and outbox event commit atomically.

A correction cannot switch the source or exceed its registered duration. A later decision-only correction preserves earlier text/range edits. Selection pins effective evidence, source hash, range and evidence revision; later retraction or correction does not silently change that saved selection. Re-analysis never rewrites overlays. Changed model findings get new identities including generation provenance; old corrected findings remain historical for explicit reconciliation. Identical output is not assumed semantically equivalent across generations.

Analysis publishes only after every requested window validates and the worker still holds its lease. A newer request prevents an older completed run becoming active. Failed/cancelled work preserves the previous head. The complete input manifests include actual sampled frame timestamps/hashes, task output, model/prompt/schema identity and retry metadata. Canonical comparisons use pinned selected text. CPU Whisper is integrated into the retained editorial analysis path; exhaustive attempt segmentation and speech accuracy remain unvalidated, and not every canonical evidence item has an automatic transcript.

ClickHouse migration 032 stores complete project/revision snapshots. Transactional outbox delivery is retryable and reader credentials are SELECT-only. Queries require the current PostgreSQL revision and a compatible embedding identity; stale/missing data cannot masquerade as an empty successful search. Whole-snapshot limits and exact cosine scoring are bounded PoC behavior, not a production ANN or terabyte benchmark. [Evidence setup](EVIDENCE_SETUP.md) records the operational limits.

## Implemented Phase 6 canonical timeline

`canonical_timeline` documents use independent keys `film` or `scene-<key>`. Existing `state_documents`, immutable `state_versions`, receipts and outbox support atomic saves. `timeline-v1` stores sequence settings, ordered unique occurrence IDs, half-open integer source frames, exact source FPS and computed integer sequence positions/durations with rational quantization deltas. Source hash, verified grid metadata, first audio stream/channels/sample rate/video offset, camera timecode string and selected evidence are pinned. Explicit save records editor approval. Current v1 supports linked first-stream audio, mute and attenuation from -60 to 0 dB; separate tracks and amplification remain outside this implementation.

`source_timing` is a project/source/hash-keyed cache of bounded ffprobe frame-grid validation. Average FPS alone never authorizes conform. Timecode is preserved as a label; drop-frame parsing and actual NLE conform are Phase 7 gates. A saved revision can be read without overwriting it; historical evidence can be restored even after removing the current selection. Preview and both exporters read the same immutable snapshot, with `source_frame()` defining per-frame mapping. Browser proxy playback remains approximate. Routes and limitations are in [timeline setup](TIMELINE_SETUP.md).

## Implemented Phase 7 editable artifacts

`timeline_export` jobs pin sequence key, immutable revision, snapshot SHA-256, exporter version and format. Enqueue uses project writer membership and command receipts; workers revalidate the canonical snapshot and original hashes before building a bounded ZIP. Complete artifacts publish under lease fencing with relative path, size and SHA-256 in the job result. Downloads check project membership, successful job state and artifact hash. Native manifests preserve exact canonical state and media alias/relative-path mappings; FCP7 emits only the documented supported subset. A separate local relink helper verifies originals before rewriting XML file references. [Editable export setup](EDITABLE_EXPORT_SETUP.md) defines format limits and the pending NLE acceptance gate.
