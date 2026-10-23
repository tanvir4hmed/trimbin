# Export contract

Current export contract, reconciled 23 October 2026. Native/FCP7 ZIP export and original-fed MP4 render are implemented and exercised on generated footage. Both consume the same immutable [timeline revision](DATA_CONTRACT.md). Actual Premiere acceptance and wider fidelity/format validation remain open; see [cutover evidence](AWS_CUTOVER.md).

## Shared preflight

Authorize the project and snapshot; resolve every occurrence to its pinned original version; verify fingerprint, stream readability, in/out bounds, audio mapping, sequence settings and destination permissions. Export paths are server-generated under the allowed export root. Reject traversal, symlink escape, input/output aliasing and overwrites of originals.

Check space for output plus temporary files with a reserved margin. Report unknown estimates instead of inventing a size. Source mutation detected before or during work invalidates the job. An unchanged size/mtime alone is not a content-integrity guarantee.

Missing original media blocks final render. Editable handoff requires validated source metadata and a resolvable source manifest; missing media is shown explicitly and cannot be represented as a validated relink. Proxy-only viewing never changes those rules.

## Editable delivery

Produce native timeline JSON, FCP7 XML and a source relink manifest. Native JSON preserves complete application revision/evidence metadata; XML carries supported editorial timing and linked audio. FCP7 XML is not FCPXML. Interchange does not embed or re-encode originals.

Use unique file and clip-item identifiers, repeat-safe occurrences, source filename and source timecode, rational rate mapping including NTSC flags where applicable, explicit sequence settings and audio links. Root aliases map to user-chosen media locations at relink time; private absolute server paths do not belong in public exports by default.

Support cuts, ordering, supported trims, linked audio, mute and basic gain only after actual importer validation. Preserve richer app data in native JSON if the importer cannot express it; block unsupported handoff options rather than silently omitting audible/visible edits. No promise of every Premiere effect or every NLE.

Phase 7 acceptance: import into a recorded Premiere version, relink originals, compare sequence/source frame positions, repeated clips, order, audio layout and gain/mute. Parsing XML and opening an OTIO object are engineering checks, not Premiere acceptance. NLE access remains pending.

## Playable delivery

Initial preset: MP4 container, H.264 video, AAC audio, explicit width/height/FPS, SDR Rec.709 and supported 8-bit output. Fix encoder/version and preset settings in the job manifest. The deployed recipe uses libx264 CRF 18 and the slow CPU preset. A generated-fixture source-frame check passed; comprehensive editor/fidelity acceptance remains open. A CRF number is not proof of losslessness.

Use original source frames. Frame-accurate arbitrary cuts generally require decoding/re-encoding. No stream-copy guarantee. Preserve original pixel dimensions when sequence and source match; mixed dimensions require an explicit fit/letterbox choice, never hidden crop/upscale. HDR, unsupported color transforms, alpha and high-bit-depth preservation are blocked for the initial SDR preset until separately implemented and tested.

Audio uses measured offsets, explicit channel mapping, the declared sequence sample rate and bounded resampling. No silent stereo downmix of unsupported layouts; surface a channel-selection requirement. Gain cannot silently clip without a warning/preflight outcome. CPU rendering is the correctness reference; hardware encoders require separate fidelity checks.

## Output manifest and acceptance cases

Record source versions/hashes, timeline revision/hash, conform policy, exporter/build/FFmpeg version, encoder settings, output checksum, dimensions, FPS, duration, audio streams, warnings and verification result. Do not include secrets or private analysis payloads. Saved timeline provenance can reference model runs without requiring another inference call.

| Case | Required evidence |
| --- | --- |
| Two ranges from the same source, including repeats | Distinct occurrences and correct cuts/order |
| 24000/1001 source and 24 FPS sequence | Exact rational mapping and declared quantization; no cumulative drift |
| Audio offset, silence, mute and gain | Sample-aligned output within declared tolerance; matching NLE behavior |
| 4K source and matching sequence | Original-fed 4K output with unchanged source checksum |
| Missing/modified source or proxy-only asset | Blocked preflight, no substitute footage |
| Worker killed/restarted/cancelled | Recoverable state; no misleading complete artifact |
| Edit while export runs | Output still matches pinned earlier revision |
| HDR/VFR/unsupported audio layout | Explicit unsupported result until validated support exists |

For cuts, verify decoded frame correspondence at each boundary using distinguishable frame-number fixtures plus cleared real footage. For audio, use known impulses/offsets and measure alignment. Separately inspect compression quality on texture, motion and dark scenes. Exact sequence frame count and output metadata are necessary but insufficient. Both exporters must pass independently before claiming delivered scene/movie exports.
