# Architecture

## Services

| Service | Responsibility |
|---|---|
| Next.js web | Shared navigation, review cockpit, upload state and playback |
| FastAPI API | Authorization, commands, screen read models, retrieval and exports |
| Media worker | ffmpeg, slate reading, proxy generation and asynchronous analysis |

API and worker share an image with different entrypoints. Web has a separate image. This is a modular application with an asynchronous processing boundary, not a service per feature.

## Storage

| Store | Owns |
|---|---|
| Firestore | Projects, membership, jobs, shot state, revisions, finding delivery records and saved film sequence versions |
| ClickHouse | Media measurements, placements, analysis runs, segments/moments, findings, decision events and analytical retrieval |
| Cloud Storage | Original media, proxies, sprites and exported artifacts |

Source placement, shot selection and sequence occurrence are distinct relationships. Internal IDs remain stable while production labels are strings. A sequence references clip IDs and bounded source ranges, never copies source media into a new category.

## Consistency

Server commands enforce authorization and range validity. Revision preconditions reject stale saves. Film saves atomically write the current document and its immutable revision snapshot; command IDs recognize a replay of the latest save.

Finding actions commit operational state and a delivery record together. The working view overlays pending state while ClickHouse delivery catches up. This is not a claim that every write path shares one universal transactional outbox.

Finding commands also persist a scoped request receipt in that transaction. A retried action returns the original decision; reuse with different content is rejected. Attempt boundaries have independent immutable revisions and command receipts.

Analysis dispatch is reserved transactionally per recording. Worker execution tokens and renewed leases prevent duplicate active ownership and stale task-state updates. Expired tasks surface as stalled and can be explicitly retried; automatic dead-letter reconciliation is not implemented. Each execution writes a distinct analysis generation. Only completed generations become current, so incomplete re-analysis does not remove previous evidence. Explicit re-analysis uses a dispatch key; model, prompt, placement and editorial brief contribute to the analysis cache identity.

Scene structure creation is transactional. Placement remains append-only in ClickHouse, avoiding interactive sort-key mutations. Workers must not replay an automatic placement over a human correction.

## Playback and responsiveness

Uploads go directly from browser to storage. Long-running media work uses queued jobs. Search may wait on retrieval/model work and exposes its errors; it is not guaranteed to return within one second.

A loaded Film Preview contains source URLs and ranges. Play/pause/seek and range advancement do not request ClickHouse or Gemini. Source transitions can still buffer; browser playback is not a frame-perfect rendered master.

The frontend uses shared query caching and generated OpenAPI types. Project scope is explicit in navigation and retrieval. Switching projects must reset source-specific drafts and player state.

Project-wide coverage shares one metadata/comment snapshot across scenes, with bounded scene query concurrency. This removes repeated project-wide metadata reads, not every per-scene archive query.
