# Evidence, review and search

The project's Evidence page runs grounded NVIDIA analysis on registered original sources. Source hashes, actual sample timestamps, allowed windows and citations constrain the returned observations. Sparse frame analysis is not exhaustive video understanding. Real production uses Token Factory; development fixtures remain explicitly labelled and cannot silently replace a failed call.

Notes, corrections, placements and selections are revisioned in PostgreSQL with command receipts. An editor can retract or correct a finding; later model generations cannot rewrite that human decision. Canonical timelines pin selected evidence and source timing. Shot/scene Film actions also write through this same authority.

The projection worker copies complete current snapshots to self-hosted ClickHouse. It acknowledges an outbox event only after publication and queues bounded automatic vector-index work for that revision. A dedicated vector worker uses the configured Qwen model and exact embedding identity. A changed workspace supersedes stale index work; credential/transport failure cannot be reported as a successful semantic search. Index jobs retry at most three times. Operators may explicitly rebuild with the documented [inference command](INFERENCE_SETUP.md).

Text search and semantic search use separate read-only credentials, explicit project filtering and matching revision/generation. They return pending/unavailable when an index is absent or incompatible. Fixed editorial retrieval uses this same ClickHouse service; it does not require Tavily or web search. ClickHouse indexes evidence/history and answers queries; FFmpeg and model workers perform media analysis.

The production package includes API, media/editorial/analysis/projection/vector/export/render workers. [Configuration](CONFIGURATION.md) and [architecture](ARCHITECTURE.md) describe access and network boundaries. Real generated-footage checks are recorded in [cutover evidence](AWS_CUTOVER.md); task-quality claims still require [paired evaluation](QUALITY_STRATEGY.md).
