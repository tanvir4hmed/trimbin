# Capability and evidence matrix

Updated 23 October 2026. “Verified” refers to the documented generated-footage AWS preflight, not general film-production certification. See [AWS cutover](AWS_CUTOVER.md) for exact evidence and limitations.

| Area | Implementation | Verification / remaining limit |
| --- | --- | --- |
| Projects and membership | PostgreSQL-backed [document adapter](../api/app/foundation/documents.py) and operational services | Real transactions, membership revocation, revision conflict, replay and rollback tests |
| Media | [Media library](../api/app/routes/media_library.py), [chunk/range files](../api/app/routes/files.py), filesystem storage | Upload, hashes, derivatives and scoped access verified; no remote browser-folder access |
| AI | [Runtime adapter](../agents/trimbin_agents/runtime.py), [inference runner](../api/app/inference/runner.py) | Real NVIDIA vision/reasoning, Qwen 768-dimensional vectors and local CPU Whisper; sampled analysis, paired quality not proved |
| Evidence | [Evidence store](../api/app/evidence/store.py), [projection](../api/app/evidence/projection.py), [vectors](../api/app/evidence/vectors.py) | Human edits, durable projection and semantic search verified; no optional external human-review dependency |
| Scene/film | [Canonical timeline](../api/app/timeline), [Film facade](../api/app/services/film_canonical.py) | One authority shared by retained Film API and timeline/export screens; real revision/replay tests |
| Editable output | [Exports](../api/app/exports) | Native/FCP7 bundles, frame mapping and hashes verified; actual Premiere import/relink pending |
| Video output | [Renders](../api/app/renders) | Original-fed 1080p SDR fixture output verified; no lossless/all-NLE/HDR claim |
| State recovery | [Backup script](../deploy/production/backup.sh), [production bootstrap](../tools/production_bootstrap.py) | Quiesced backup and isolated restores; full replacement-host disaster recovery not certified |
| Hosting | [AWS Terraform](../infra/aws), [production package](../deploy/production/compose.yaml) | Actual CPU host, encrypted persistent disk, private databases, HTTPS viewer ingress; single host and HTTP origin leg |
| Automation | [CI](../.github/workflows/ci.yml), [main deploy](../.github/workflows/deploy-trimbin.yml) | OIDC/Variables/runtime configured; final push starts checks/build/rollout; no post-push polling |
| Evaluation | [Quality strategy](QUALITY_STRATEGY.md), [evaluation tooling](../eval) | Contract/fixture checks pass; real-movie held-out comparison and old paid-output bundle absent |

## Preservation and claims

The source reuses the useful editorial foundation and significantly expands it. Retired references/configuration are hash-preserved outside Git, never bundled with original footage or credentials. License notices and truthful prior-work disclosure remain. The historical tag proves a code boundary, not a successful model-quality comparison.

No proprietary source corpus has been recovered from GCP. Future studio SSD/NAS deployment, self-hosted GPU inference, zero-upload operation, terabyte throughput and lower total ownership cost remain future validation. Token Factory remains external managed inference; AWS hosting has separate costs. Optional partner credits are not mandatory for the declared workflow.
