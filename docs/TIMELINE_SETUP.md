# Canonical scene and film timelines

Phase 6 implements `/projects/<slug>/timeline`, linked from Evidence workspace. This is the portable source-frame timeline. Existing `/film` remains the legacy decimal-second workflow until explicit cutover; its automatic migration is not claimed. No paid AI key, new cloud host or new schema migration is needed. Use the PostgreSQL/media/session setup from [media setup](MEDIA_SETUP.md) and the selections from [evidence setup](EVIDENCE_SETUP.md).

## Editor workflow

1. Select ranges in Evidence workspace. Open the timeline and use `film` or an independent scene key such as `scene-01`.
2. Append selected ranges. Sources without a cached timing grid are hashed and scanned first. The UI appends nothing if any required source cannot be verified. Selection order is preserved; select/remove ranges deliberately for each scene or film.
3. Trim using source In/Out frame numbers (Out is exclusive), move up/down, repeat with a fresh occurrence ID or remove. Set name, resolution, sequence FPS, linked-audio mute/attenuation and notes. Undo/redo includes settings and arrangement; its bounded 100-entry draft history lasts for the page session.
4. Save the approved revision. Concurrent changes cause a conflict and retain the draft. Retry unchanged saves reuses the command UUID. Reload discards the draft only after an explicit browser confirmation. Drafts do not survive browser closure; there is an unload warning.
5. Preview or scrub the saved sequence. Unsaved edits do not change preview. Saved history can be brought back as a draft and saved as a new version; old versions remain immutable. Older versions are paginated, not deleted.

Manual assembly has no model dependency. AI draft proposals remain disabled pending real grounding/quality acceptance. No editable XML or rendered movie is produced by this phase.

## Timing, audio and source identity

Coordinates use half-open source frame ranges and integer sequence frames. Source FPS and timing offsets are reduced rational pairs. Sequence durations use positive half-up rounding once at save time; each occurrence records its quantization delta. Zero-frame results and duplicate occurrence IDs are rejected. Repeating footage is allowed with different occurrence IDs and ranges. The sequence is one gapless cut track, SDR Rec.709, 48 kHz linked audio, with a preserve-speed/drop-duplicate conform policy. Mixed-rate frame mapping uses exact arithmetic in `source_frame()`; NLE/render parity remains unverified until Phases 7/8.

The timing preparation endpoint verifies actual decoded presentation timestamps against the declared constant-rate grid within the source timestamp tick, with source hashes before/after. Unequal nominal/average rate, nonmonotonic or variable timestamps, coarse timing, unsupported HDR and missing audio timing fail explicitly. The existing subprocess capture limit is 1 MiB and the configured media timeout applies: long sources may hit the bound. The app does not silently replace this scan with average-FPS arithmetic. This bounded implementation is not a long-movie/terabyte performance claim; streaming grid verification is a later optimization requiring equivalent correctness.

Evidence microseconds initially expand outward to containing source-frame boundaries, clamped at source end. Editors can trim beyond the original selected interval within the verified source; pinned evidence still identifies the originating selection, not a claim that AI approved the expanded interval. Saved snapshots pin original hash, grid metadata, camera timecode label, first audio stream, channel count, sample rate and audio-to-video offset. Preview uses the existing first-audio-stream proxy. Channel selection, separate audio tracks, gain above 0 dB, HDR/color conversion and drop-frame timecode parsing are not implemented here.

The read route checks registry hashes and current source-path availability; unavailable sources are flagged and preview disabled. This is not a fresh integrity rehash on every playback. Export/render must rehash originals and validate pinned metadata before consuming them. Original files are never edited. Source relinking remains the media library's hash-verified operation.

## Snapshot interfaces

- `GET /timelines/{project}/{film-or-scene-key}` reads current revision; `?revision=N` reads an immutable version.
- `POST .../revisions` requires expected revision, command UUID, sequence and occurrence list. Membership, source scope and selected evidence are checked within the save transaction.
- `GET .../history?before=N` returns up to 30 earlier revisions.
- `GET .../selections` produces an unsaved ordered draft or a list of source timing prerequisites, never a partial successful draft.
- `POST /timelines/{project}/sources/{source_id}/timing` verifies/cache timing for an authorized writer. Two scans per API process can run concurrently; this is not a durable background queue.
- `GET .../frames/{frame}?revision=N` resolves a saved sequence frame to its occurrence/source frame using exact canonical mapping.

Future exports must pin the revision rather than fetch whichever revision is current. Timeline save events remain in the operational outbox; Phase 5's projector only consumes evidence events and does not need a timeline search projection. Existing repository transaction logic is reused with an optional caller-owned connection so authorization, validation, saved state and receipt are atomic.

## Verification boundary

Static code/type/schema/documentation checks are performed. Tests have been added for exact conform, repetition, audio offset, VFR rejection, receipts, stale writes, project/role boundaries and historical restore; the disposable PostgreSQL tests are included in the existing CI foundation rehearsal. Their runtime execution, real source-grid scanning, browser audio/seek behavior and export acceptance are deferred by owner instruction. Browser proxy playback follows the saved mapping but is approximate, including seeking, buffering and clip transitions; it is not a substitute for original-fed frame/audio validation. No deployment completion is claimed.
