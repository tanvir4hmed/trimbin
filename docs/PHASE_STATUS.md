# Phase status

Updated 23 October 2026 Asia/Dhaka. Current evidence is in [AWS cutover](AWS_CUTOVER.md). Older milestone reports and replaced configurations are preserved outside Git; earlier statements that the runtime still used GCP or that all real tests were deferred are superseded by this cutover.

| Phase | Current status |
| --- | --- |
| 1 Requirements, contracts and CI | Delivered; provenance and protected historical tag preserved |
| 2 Self-hosted foundation | PostgreSQL and ClickHouse deployed; permissions, transactions, migrations and recovery exercised |
| 3 Media | Filesystem originals, resumable upload, derivatives and scoped access verified on generated footage |
| 4 Models | Real NVIDIA/Token Factory vision and reasoning, Qwen embedding and CPU Whisper verified; comparative editorial quality still open |
| 5 Evidence | Real evidence, human annotations/selections, projection and semantic retrieval exercised |
| 6 Timeline | Canonical frame timeline, old Film API facade, revision conflict/replay and saved selection behavior verified |
| 7 Editable export | Native and FCP7 ZIP generation, frame mapping and manifest integrity verified; actual Premiere import/relink remains open |
| 8 Video render | Original-fed 1080p SDR output, source-frame correspondence, duration, tags and checksums verified on generated footage; wider format/fidelity acceptance remains open |
| 9 Integrated workflow/package | One application, immutable source identities and retained state across preflight redeploys; future on-premises installation is not claimed |
| 10 AWS cutover | Non-demo implementation and preflight runtime verification completed; final main push triggers CI and rollout, whose result is not polled |
| 11 Demo/submission | Separate next phase; recording, public judge access, final rule check and submission remain outstanding |

The live URL is https://trimbin.qleam.com. AWS infrastructure is Terraform-managed; the production Compose package is `deploy/production/compose.yaml`, and the entrypoint is `app.main`. Old GCP deployment/configuration and managed ClickHouse secrets have been retired. The owner authorized paid AWS hosting and real inference; no additional phase permission is needed for finishing this cutover.

Verification: Linux API 602 passed / 18 skipped; agents 122 passed; web 40 passed; API/agent lint and format, agent types, web types/build, generated schema, real provider calls and scoped runtime workflow checks. Recovery evidence and exact fixture scope are recorded in [AWS cutover](AWS_CUTOVER.md). A pushed commit is not a verified completion of its later deployment.

No recovered historical corpus or paid-model baseline was found. Quality superiority, Premiere compatibility acceptance, terabyte throughput and offline/local GPU operation are not claimed. The [quality strategy](QUALITY_STRATEGY.md) remains in force. Missing quality/NLE evidence prevents those submission claims, not truthful reporting of the running cloud workflow.

## Documentation reconciliation

The 23 October follow-up reconciles the active contracts, UX, security, setup and submission strategy with the AWS cutover. [README](../README.md) indexes every guide; the documentation check enforces this coverage. Four separate PNG/SVG diagrams, the English submission copy pack/checklist and a whole-application basic-usage cost calculation are included. Runtime baseline commit: d047555. No later deployment result, video publication, judge access or outstanding quality/NLE acceptance is inferred from this documentation update.
