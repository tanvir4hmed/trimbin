# Deployment media library

Phase 3 implements `/media-library` and `/projects/<slug>/media`. The ingest screen links to it when storage is configured. This is the new media foundation; it does not yet feed the legacy analysis/placement routes or film timeline. Those consumers migrate in later phases. No AI call, Google storage, Firestore or Pub/Sub operation is made by this media path. Existing routes and the existing deployment workflow remain transitional.

## Configuration and authorization

Apply foundation migrations with `python tools/foundation.py migrate` using the API environment. Version 1 stays checksum-protected; numbered migration 2 adds sources, upload sessions and PostgreSQL project membership. The API and media worker use the least-privilege writer DSN. Configure private runtime settings, following `.env.example`:

```dotenv
TRIMBIN_PROFILE=development
TRIMBIN_INFERENCE_MODE=fixture
TRIMBIN_ORIGINALS_ROOT=D:/private-media/upload-store/originals
TRIMBIN_STAGING_ROOT=D:/private-media/upload-store/staging
TRIMBIN_PROXIES_ROOT=D:/private-media/derived
TRIMBIN_EXPORT_ROOT=D:/private-media/exports
TRIMBIN_ALLOWED_MEDIA_ROOTS=["D:/private-media/upload-store/originals","D:/private-media/camera"]
TRIMBIN_MEDIA_ROOTS={"camera":"D:/private-media/camera"}
TRIMBIN_MEDIA_ROOT_PROJECTS={"camera":[1]}
```

The paths are examples, not existing project data. Create the camera root deliberately. Configure the generated database/session secrets privately; never put a credential in this document. For password sign-in, set `TRIMBIN_TEAM_PASSES` to private `email:password` pairs. Use a strong unique password. A signed-in identity alone cannot access media: an operator must grant its PostgreSQL membership.

From the checkout root, with the API Python environment:

```powershell
api/.venv/Scripts/python.exe tools/media_project.py --env-file .secrets/foundation/runtime.env --project 1 --name "Editorial demo" --email editor@example.test --role owner
```

Replace the example identity with the configured sign-in identity. Roles are owner, editor and viewer. All can read; owner/editor can upload/index/cancel/retry; only owner can relink. Root grants additionally restrict which projects can register files inside each operator-provisioned mount. Root aliases and relative paths are stored, not absolute host paths. There is no HTTP endpoint that grants access to an arbitrary host folder. Legacy project membership is not silently imported; the operator grants the portable project explicitly.

Run API and worker in separate terminals from `api/`:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --env-file ../.secrets/foundation/runtime.env --port 8080 --no-access-log
.venv/Scripts/python.exe -m app.media.worker --env-file ../.secrets/foundation/runtime.env
```

Start the existing Next development server and open `/projects/1/media`. Sign in with the configured local password account. The API and worker need PostgreSQL; model accounts and GCP credentials are unnecessary. Full legacy workspace screens still have their historical dependencies. The dedicated media page is available directly without opening those screens.

## Files and timing

Supported intake containers are MOV/MP4/M4V, MKV, AVI and MXF, subject to actual installed decoder support. Camera RAW, malformed files, absent video/timing and unsupported formats fail visibly. HDR PQ/HLG proxies currently fail explicitly because a validated tone-mapping path has not been implemented. This is not a claim of complete camera-format coverage.

Sources get stable UUIDs, streaming SHA256 fingerprints, rational timebase/frame rates, source start/timecode, video color/rotation metadata and audio-stream layout. Equal basenames remain distinct; equal content records a project-scoped duplicate relationship. Originals are read for measurement/processing and hashed again before atomic publication. Workers use originals directly without downloading or copying the entire source into temporary storage. Deliberate darkness/silence is not rejected as unusable footage.

The MP4 playback proxy uses H.264/AAC, keeps source timestamp spacing and records its offset mapping back to the original. It is bounded to 1280 pixels wide with no upscaling; it is not a final export or the guaranteed evidence input for fine visual detail. A sprite samples up to 100 frames. The first audio stream is extracted as FLAC with its source-origin mapping; metadata preserves the other streams for later task/export handling. Exact variable-frame-rate and broad codec compatibility still require a wider corpus; the small CFR fixture checks do not establish universal frame accuracy.

Registered directories must be operator-controlled. Reject traversal, Windows drive/ADS/device paths, symlinks and junctions below the configured root. Mount camera roots read-only and keep originals, staging, derivatives and export directories disjoint. Changing a root alias's configured physical location supports volume moves without changing stored source IDs. Relinking a source requires an identical SHA256 fingerprint. Do not modify indexed files in place; re-register changed footage as a new source.

## Upload and playback

Browser uploads are explicit transfers to deployment storage. A browser-local path is never interpreted as a server path. The default controlled-upload maximum is 8 GiB, with at most ten unfinished sessions per project. Larger already-mounted footage does not go through this demo upload limit; no terabyte throughput is claimed.

Requests contain at most 8 MiB per chunk. The server fsyncs bytes before committing the offset and chunk checksum. On retry it truncates uncommitted tail bytes to the committed offset. After refresh, reselect the file; the browser checks every previously received chunk hash before appending, rather than trusting filename/size/modified date. The pending-upload selector recovers sessions when browser storage is lost. Upload completion atomically renames into the originals root and transactionally registers the source/job; replay recovers a rename that preceded a failed commit. Staging and uploaded-originals roots **must be on the same filesystem**. Uploaded originals are never overwritten by completion.

Playback uses authorized single-range GET/HEAD responses. Native media elements receive five-minute HMAC tickets restricted to one project/source/file kind. A ticket remains valid until expiry even if membership changes; it does not grant other sources or original access when issued for a proxy. Keep access logs off or redact ticket query strings at the gateway. Responses are private and not cached by a public CDN. Renew an expired playback URL with Preview.

## Jobs, limits and recovery

One worker processes one media job at a time, with two FFmpeg threads by default. PostgreSQL leases fence stage/result publication and recover abandoned jobs. Completion publishes source metadata, derivative references and job success in one transaction. Each attempt writes a separate UUID directory. Failed/cancelled attempts remove only their owned derivative directory; never source files. If publication outcome is uncertain, preserve output rather than risk deleting committed media.

Cancellation is observed on the next lease heartbeat, at most approximately one third of the configured lease period under normal database response times. Expired workers cannot publish. Retry restarts processing for one source; hashing/encoding do not resume at an arbitrary byte/frame. Completed sources and uploads remain durable after process restart.

Default limits: 2 GiB of derivative/work output per attempt, 1 GiB free-disk reserve, 3600 seconds per FFmpeg operation. Polling enforces disk/lease/time limits and kills the child process on failure; transient overshoot is possible between checks. Large files that exceed these configured budgets fail visibly rather than reducing analysis/export quality. Normal output is persistent storage, not temporary free space. A hard process kill can leave an orphan attempt folder: stop workers and compare folders against `media_sources.derivatives.directory` before an operator removes any orphan. No automatic broad filesystem deletion is provided.

## Container package and host boundary

[Media Compose](../deploy/media/compose.yaml) attaches API/worker to the foundation's private network and limits each to 2 CPUs / 1 GiB RAM. It requires an explicit immutable application image, private container env file and operator-owned directories. Set the DSN host to `postgres` inside this network, and use these container paths:

- `/media/upload-store/originals` and `/media/upload-store/staging` on the same parent bind mount;
- `/media/derived` for derivative output;
- `/media/library` for the read-only operator footage mount.

Create directories beforehand and grant them to the application's container user. The API writes upload staging/promotion and reads derivatives; the worker sees upload originals and camera media read-only and writes derivatives. Databases remain private; the sample API port binds to host loopback. HTTPS ingress and complete app deployment belong to cutover. The manifest creates no cloud resource and does not choose a hosting provider. All eventual new infrastructure remains Terraform-managed.

Foundation backups currently cover the two databases only. Back up source and derivative volumes separately while writers are quiesced, together with the matching database snapshot and private configuration. Restore the same root aliases and verify hashes before reopening editors. Do not advertise database-only backup as footage recovery.

## Verification scope

Local tests use generated 320×180 footage, including 24000/1001 frame rate, source timecode and delayed audio. They check source hashes, proxy duration/frame count, audio sample rate and timing offsets; they also exercise path isolation, bounded range delivery, ticket scope/expiry, corrupt files and subprocess cancellation/disk limits. Windows could not create symlinks; that particular test runs in Linux CI.

The foundation CI tests use real PostgreSQL for upload restart/rename recovery, command replay, source duplicate identity, lease fencing, relinking and role isolation. This PC has no Docker/PostgreSQL runtime, so those database tests are skipped locally, not claimed as passed. Container startup and browser-to-database acceptance remain CI/test-deployment gates. No live model result, complete migrated editor, NLE import, rendered-film export or cloud deployment is claimed by Phase 3.
