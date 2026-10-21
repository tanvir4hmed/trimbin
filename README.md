# Trimbin

Trimbin is being expanded into a complete editorial application demonstrated as a cloud-hosted proof of concept. Editors inspect AI evidence, select source ranges, assemble scenes and a film timeline, then export an editable timeline or high-resolution video from unchanged originals on the deployment storage. The portable software foundation is intended for a future studio installation with suitable hardware; that installation is outside this hackathon.

The quality target is to improve on the preserved paid-model output, without accepting worse critical results to save cost or simplify implementation. Self-hosted open models provide a route away from recurring inference API bills; actual quality, hardware needs and total costs must be measured. Editors approve the creative decisions. The competition version also needs a genuine NVIDIA Nemotron operation on Nebius.

## Current status

Phases 2 and 3 add shared configuration, self-hosted databases, transactional jobs and a portable media library: controlled resumable uploads, mounted-source indexing, proxy/audio/sprite processing, scoped playback and verified relinking. The media routes use PostgreSQL membership and need no GCP or inference credentials. The older editorial workflow has not yet been migrated to these sources; Phase 4 now adds operator-facing Token Factory adapters and evaluation tooling, with runtime/live quality tests deferred. Phase 5 adds a dedicated grounded evidence workspace with durable review/corrections/selections and scoped text/vector retrieval; see [evidence setup](docs/EVIDENCE_SETUP.md). Runtime acceptance and live quality remain deferred. Phase 6 adds [canonical scene/film timelines](docs/TIMELINE_SETUP.md) and saved-revision preview; runtime acceptance and both full exports remain pending. A new cloud host has not been selected or provisioned. Working code is updated on `main` through approved phases.

- [Product direction and reasons for the expansion](docs/PRODUCT_DIRECTION.md)
- [Submission story, improvements and evidence](docs/SUBMISSION_STRATEGY.md)
- [Quality strategy and baseline comparison](docs/QUALITY_STRATEGY.md)
- [Build plan and phase acceptance](docs/BUILD_PLAN.md)
- [Product requirements and competition checks](docs/REQUIREMENTS.md)
- [Proposed architecture](docs/ARCHITECTURE.md)
- [Credentials and configuration plan](docs/CONFIGURATION.md)
- [Workflow and screen design](docs/UX_DESIGN.md)
- [Data, timing and recovery contract](docs/DATA_CONTRACT.md)
- [Model tasks and evaluation protocol](docs/MODEL_CONTRACT.md)
- [Editable and video export contract](docs/EXPORT_CONTRACT.md)
- [Current capability matrix](docs/CAPABILITY_MATRIX.md)
- [Terraform and deployment design](docs/DEPLOYMENT_DESIGN.md)
- [Foundation setup, configuration checks and recovery](docs/FOUNDATION_SETUP.md)
- [Media setup, limits and recovery](docs/MEDIA_SETUP.md)
- [Model adapter setup and deferred evaluation](docs/INFERENCE_SETUP.md)
- [Phase status](docs/PHASE_STATUS.md)
- [Security policy and planned controls](SECURITY.md)

Foundation setup is documented above. Tested model IDs, migrated demo access and export compatibility will be added with their corresponding verified implementations. Do not use the planning documents as a claim that these integrations currently run.

## License

Application source is covered by [Apache 2.0](LICENSE). Model weights, codecs, datasets and footage have separate terms. Preserve applicable notices and confirm asset rights before redistribution or training.
