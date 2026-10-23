# Editable timeline export

The `exports` worker in the [single production package](../deploy/production/compose.yaml) consumes durable `timeline_export` jobs. Requests pin a saved canonical film/scene revision, so later editing does not change an export already queued. Originals are read-only; the API reads the artifact directory read-only. No model key is needed for an approved timeline export.

Native ZIP contains `timeline.json`, a root mapping example, instructions and per-file checksums. FCP7 ZIP adds `timeline.xml` and a relink helper. It references original media with hashes; it does not repackage full movies or promise to relocate terabytes automatically. Users relink approved source roots in their NLE/environment.

The generated 1080p/24 fps runtime test exported both ZIPs and verified their checksums. XML clip in/out 24/96 maps to a 72-frame sequence. This proves the tested structure and source mapping; it does not prove Premiere import or all NLE behavior. Mixed rates, scaling, audio offsets, timecode and XML subset constraints remain in [export contract](EXPORT_CONTRACT.md). External Premiere acceptance is still required before claiming equivalence to that editor.

Downloads require project authorization. Source hash changes, invalid ranges and missing originals stop export; proxies are never substituted. Job creation/cancel/retry and current metadata are shown in the canonical timeline interface. [Rendered video](RENDER_SETUP.md) is a separate output from the same saved timeline.
