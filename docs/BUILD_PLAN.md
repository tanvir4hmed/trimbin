# Build and release plan

The owner authorized completion of all remaining non-demo AWS cutover work on main on 23 October 2026. This supersedes earlier placeholder-only and per-phase approval boundaries for this cutover. Do not ask another permission question before finishing this authorized scope. Demo recording/submission is a separate phase. Preserve the protected historical tag and do not rewrite Git history.

| Phase | Deliverable |
| --- | --- |
| 1 | Requirements, design, source provenance, archive and CI |
| 2 | Configuration, PostgreSQL revisions/jobs/outbox, self-hosted ClickHouse |
| 3 | Filesystem media registry, resumable upload, derivatives and scoped access |
| 4 | NVIDIA/Token Factory adapters, model identities and evaluation tooling |
| 5 | Grounded evidence, human correction/selections and retrieval |
| 6 | Canonical scene/film timeline and exact timing |
| 7 | Native and FCP7 editable export |
| 8 | Original-fed video render for the documented SDR subset |
| 9 | Complete workflow integration and reproducible source package |
| 10 | One canonical AWS runtime, actual configuration, provider validation, retirement of replaced GCP/managed tooling, runtime acceptance and main-push deployment |
| 11 | Later demo recording, English walkthrough, public judging access and submission |

Phase 10 execution order: preserve references outside Git; map all useful editorial functions to the new authority; configure actual providers; provision named trimbin AWS resources with Terraform; deploy a preflight build; verify migrations, roles, real calls, upload/review/timeline/both exports, source integrity and recovery; configure GitHub OIDC/Variables/Secrets; remove obsolete deployment paths and secrets; commit and push main. The workflow itself performs rollout checks. Do not poll deployment after that final push.

The prior source/media systems were already deleting or absent. The cutover does not fabricate a recovered film corpus. The new owner workspace and explicitly generated verification footage are distinguished from historical project data. Source recovery remains an inventory limitation, not an excuse to invent rows or destroy backups.

Quality targets remain unchanged: no accepted critical-task regression for cost or convenience, and no superiority claim without paired footage evaluation. Schema validity, generated fixtures, speed and successful deployment do not establish better model quality. Original hashes, human authority, explicit unsupported export cases and accurate provenance remain required. Premiere acceptance and cleared-footage comparison are open until independently demonstrated.

Current evidence and constraints are maintained in [AWS cutover](AWS_CUTOVER.md) and [phase status](PHASE_STATUS.md). Detailed contracts remain in [data contract](DATA_CONTRACT.md), [model contract](MODEL_CONTRACT.md), [export contract](EXPORT_CONTRACT.md), [architecture](ARCHITECTURE.md), [UX](UX_DESIGN.md) and [quality strategy](QUALITY_STRATEGY.md).
