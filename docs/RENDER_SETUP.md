# Original-fed video render

The `renders` worker consumes durable `timeline_render` jobs from the same canonical timeline revision used by editable export. It reads originals, verifies hashes and timing, renders in bounded scratch space and publishes a checksummed MP4. Originals are mounted read-only and never cut or overwritten. No LLM call is needed to render human-approved ranges.

The current supported recipe is H.264/AAC, explicit Rec.709 SDR, limited-range 8-bit yuv420p, one source/sequence rate and resolution, and mono/stereo audio. It preserves the sequence's original dimensions for this supported subset. HDR, unspecified color profiles, mixed-rate/scaled renders and unsupported audio layouts are rejected explicitly. They are not silently down-converted. High resolution does not mean bit-identical or lossless export.

The runtime generated-footage test exported 1920x1080 at 24 fps for exactly three seconds. Its first rendered frame corresponds to original frame 24; measured first-frame PSNR was approximately 52.26 dB on that generated fixture. This is a narrow technical check, not movie-quality superiority, complete audio acceptance or professional NLE equivalence.

The API grants an expiring project-scoped download ticket after successful rendering, with an artifact SHA256 for verification. Missing/changed sources, exhausted scratch space, cancellation and unsupported cases remain visible. The default scratch limit is a bound for small work; size it deliberately for longer jobs and monitor disk/RAM. This installation has not established terabyte throughput.

See [export contract](EXPORT_CONTRACT.md), [timeline setup](TIMELINE_SETUP.md) and [deployment/recovery](DEPLOYMENT_DESIGN.md).
