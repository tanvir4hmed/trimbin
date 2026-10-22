# Editable timeline handoff

Phase 7 adds native timeline ZIP and FCP7 XMEML v5 ZIP exports to the portable timeline page. Both pin a saved revision and verify original hashes. No media file is copied, cut or re-encoded. A completed job means an artifact was written and checksummed; it does not mean Premiere import was tested. Final video rendering remains Phase 8.

## Use and package setup

Save the approved scene/film timeline, then choose Native timeline bundle or FCP7 XML bundle. Unsaved edits must be saved/discarded first. Export jobs show queued/running/succeeded/failed/cancelled states and scoped downloads. Request receipts prevent duplicate jobs on exact retries. Refreshing the page recovers the latest 30 jobs for that sequence. Earlier artifacts remain in storage; the list is not a retention policy.

Run `python -m app.exports.worker --env-file ../.secrets/inference/runtime.env` from `api/` with the API environment. The private env needs existing PostgreSQL/media settings and `TRIMBIN_EXPORT_ROOT`; no model credential is used. The portable [Compose package](../deploy/media/compose.yaml) includes the export worker on the internal foundation network, originals mounted read-only and its own writable artifact root. Supply `TRIMBIN_EXPORT_STORE` and set `TRIMBIN_EXPORT_ROOT=/media/exports` inside the containers. The API mounts the same artifact root read-only. This adds no cloud host and does not change the legacy deployment target.

The worker reuses PostgreSQL leases and cancellation. Output lives under a project/job/lease directory separated from originals. ZIP data is capped at 32 MiB; disk reserve checks apply. Hashing is streaming. A complete file is flushed before fenced publication. A crash, cancellation after writing, or uncertain database commit can leave an unreferenced attempt directory; retain it until an operator verifies it is unreferenced. There is no automatic retention deletion. Back up export storage with the matching operational database. Runtime crash/cancel/backup acceptance remains pending.

## Artifact and relinking

Each ZIP includes `timeline.json`, `roots.example.json`, `checksums.json` and instructions. The JSON contains the exact canonical snapshot, revision/hash, occurrence/evidence identities, source timing/audio metadata and root-alias/relative-path/hash mappings. It includes private editorial notes and filenames intended for the authorized editor, but no service credentials, cloud absolute paths or original bytes. Native JSON is the application's interchange manifest, not a directly importable Premiere project.

The XML ZIP also contains `timeline.xml` and `relink.py`. XML initially references a clearly artificial `/TRIMBIN_MEDIA/<alias>/<relative-path>` location. Extract the ZIP. Create `roots.json` mapping every alias to an absolute folder holding the matching originals, preserving subdirectories. Run `python relink.py --roots roots.json` with Python 3.11 or later. The helper validates paths and hashes every original before creating `timeline-relinked.xml`; it refuses to overwrite that output. It never uploads/copies/re-encodes footage. A local-root remap alone does not transfer the footage: the editing workstation must already have the matching originals available.

Import the relinked XML in Premiere, then check every source, occurrence, cut, timecode and audio track. Different source IDs and directory paths distinguish duplicate basenames. Repeated footage uses unique clipitem IDs with shared file references. Never resolve an ambiguous offline clip solely by its basename. No actual NLE import/relink result has been recorded yet.

## XML supported subset and explicit gates

Initial XML supports the canonical gapless cut track, repeated occurrences, trims, source camera timecode, linked first-stream audio, mute and attenuation. Rates are integer 24/25/30/50/60 or 24000/1001, 30000/1001 and 60000/1001, with equal source/sequence rates and dimensions. Sources require square pixels and no rotation; known interlaced media is blocked. Source metadata must have passed the Phase 6 CFR grid gate. Missing field-order metadata remains unverified rather than being declared progressive.

One mono/stereo audio stream is supported with zero audio/video timestamp offset. Mono is represented on both output channels; stereo channels remain separate linked clips. Sequence audio settings use 48 kHz and 32-bit depth; original audio is still referenced, not converted by this exporter. Actual NLE interpretation, sample-rate conversion, channel routing and sync require import tests.

Mixed-rate conform, scaling, nonzero audio offsets, multiple/multichannel audio streams, VFR, HDR, unsupported timecodes and unsupported rates fail explicitly for XML. Native JSON preserves the saved model including those pending interchange cases. Unsupported XML cases do not silently omit audio or change source/sequence timing. This is a bounded implementation, not complete Premiere compatibility.

Camera timecode is encoded separately from zero-based source in/out frames. Valid 29.97 drop-frame labels subtract skipped labels correctly; unsupported drop-frame rates/invalid labels are rejected. If camera timecode is absent, XML uses zero and the native manifest preserves null. No claim of recovered camera timecode is made. Fractional, repeated-source, audio and timecode behavior still needs verification in a recorded Premiere version.

The writer uses the standard library directly for this restricted contract; no unverified OTIO adapter dependency is required. Apple's archived [element catalog](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Elements/Elements.html) defines file references, clip links and rate/timecode fields; its [timing/effect notes](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Topics/Topics.html) distinguish source in/out from sequence start/end and describe linear audio gain. Adobe distinguishes modern FCPXML from the legacy XML interchange path in its [import guidance](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/migrate-from-final-cut-pro-x.html). These references guided implementation; they do not certify this exporter.

## Verification and next gate

Static lint/format, Python compilation, generated API types, frontend types, Compose YAML and documentation checks are performed. Deferred tests cover XML references/escaping/rates/timecode, rejection of unsupported offsets, immutable snapshot identity, exact request replay, authorization and relink hash/overwrite protection. Runtime test execution remains deferred at the owner's request, including worker/database/cancellation and actual bundle import. XML parsing is not DTD or Premiere validation. Record Premiere version, original hashes, source/sequence frames, linked audio/channel behavior and NLE-relinked results before making a compatibility claim.
