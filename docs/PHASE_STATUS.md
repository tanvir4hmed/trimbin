# Phase status

Updated 21 October 2026 Asia/Dhaka.

Latest owner direction: revise the plan for a complete cloud-hosted editorial PoC now; implement through individually approved phases. Future studio hardware/software packaging is the direction, not a requirement to install locally during this hackathon. Kubernetes, autoscaling and local GPU certification are deferred. The owner approved Phases 1 and 2, then authorized Phase 3 after the credit/account discussion. Preserve automatic deployment and do not wait for deployment completion; all new infrastructure is Terraform-managed.

| Phase | Status | Approval and evidence |
| --- | --- | --- |
| 0 Planning and archive | Updated locally | Rules, FAQ and overview rechecked. Cloud PoC scope, improvement ledger, network boundaries and future hardware claims aligned. Previous 53-file archive retained. No runtime or workflow changes in this update. |
| 1 Specifications design and CI control | Complete; included in the start milestone | UX/data/model/export contracts, capability and baseline evidence matrix, workflow/network diagrams, Terraform rollout design, main CI coverage and external archive. Local checks passed; see verification below. |
| 2 Configuration and self-hosted foundation | Implemented; local checks passed; container acceptance pending CI | Shared configuration, PostgreSQL revisions/jobs/outbox, pinned database package, recovery tools and CI lifecycle checks. The unapplied GCP target was subsequently archived as an incorrect hosting assumption. Docker/WSL unavailable locally; no paid resources provisioned. |
| 3 Deployment media ingest and processing | Implemented; local checks passed; database/container acceptance pending | Owner authorized phase start. Mounted roots, resumable upload, source integrity, derivatives, scoped playback, PostgreSQL jobs and media UI. |
| 4 NVIDIA adapters and quality evaluation | Adapter/evaluation implementation delivered; runtime tests deferred | Owner approved placeholder credentials and testing later. Model selection, live calls, speech path and comparative quality remain pending. |
| 5 Evidence review and retrieval | Not approved | Preserve corrections and durable editorial state. |
| 6 Canonical scene and film timeline | Not approved | Shared selected-range preview/export snapshot. |
| 7 Editable timeline export | Not approved | Actual Premiere import/relink validation required. |
| 8 Original-resolution video rendering | Not approved | Original-fed render and audio/frame correctness required. |
| 9 Complete cloud workflow and portability verification | Not approved | Full workflow, clean redeploy, root/endpoint remapping, persistence and measured quality; no actual studio install required. |
| 10 Deployment cleanup and submission | Not approved | Explicit host budget, rollout, judge access, final config retirement and publication scope. |

Existing deployment workflows still target the previous runtime and remain enabled as explicitly requested. Moving old agent documentation matches the backend path filter. Push success will not be reported as verified deployment success. No new credentials or resources were provisioned in Phase 1. The protected baseline tag remains recoverable. The 53-file reference archive is now outside Git at `D:\NVIDIA\archive\2026-10-20`, with all original hashes verified.

## Phase 1 verification

- `python tools/check_docs.py`: all local links in 17 active documents resolve; no tracked archive.
- `actionlint 1.7.12 -shellcheck= -pyflakes=`: all GitHub Actions workflow syntax/semantics pass. External shell/Python linters were not installed or run by this command.
- `terraform fmt -check -recursive infra`: pass; no Terraform resource changes made in this phase.
- `git diff --check`: pass.
- External archive: all 53 manifest file hashes match before and after moving outside the checkout.

Backend/frontend runtime suites and cloud deployment were not executed locally for this documentation/CI-trigger change. Existing runtime checks remain in GitHub CI. No model-quality, NLE-import or rendered-video result is claimed. Per owner instruction, deployment completion will not be polled after push.

## Scope change from the earlier plan

The previous plan made local-PC demonstration and a hybrid local-to-Nebius path central acceptance requirements. The owner has replaced that with a complete cloud-hosted application that demonstrates a portable foundation. Customer hardware installation, offline inference, GPU purchasing and scaling are future work. Quality, original integrity, editorial authority, both exports, honest provenance and meaningful competition-platform use remain required.

A cloud PoC is complete when its declared editorial workflow and release gates pass. This is not a claim that every future product benefit, NLE feature or physical package has been delivered. Read PRODUCT_DIRECTION.md and SUBMISSION_STRATEGY.md before proposing additional scope.

## Phase 2 verification and limits

- API regression: 521 passed, 23 skipped (5 new real-PostgreSQL tests require Docker/service access; 18 pre-existing skips).
- Agent regression: 120 passed; lint, formatting and mypy passed.
- Terraform portable environment: backend-free initialization and validation passed; no plan/apply or remote change.
- Local credentials generated without outputting values; ignored paths verified. API/agent configuration references archived externally.
- Real database migrations, concurrent writes/leases, role isolation, persistence and backup/restore are required by the added CI job; they were not run on this Windows host because Docker and WSL are absent. These checks are not reported as passing.
- No live model calls, provider-secret registration, application data migration or legacy infrastructure retirement occurred. Existing auto-deploy remains enabled; no deployment polling after push.

Phase 3 was subsequently authorized and implemented below. Phase 4 was subsequently approved with runtime tests deferred. Full release requires the declared model-quality, source-integrity and export gates.

## Phase 3 verification and limits

- API regression: 552 passed, 30 skipped (11 real-PostgreSQL tests require the disposable database, one Windows symlink test requires permission, and 18 are pre-existing skips). Generated FFmpeg footage validates fractional frame rates, source hashes, proxy frame count/duration, delayed audio mapping and source timecode. Path/range/ticket and subprocess-limit tests also pass.
- Frontend: typecheck, 40 tests and production Next build pass, including the media page and upload-prefix integrity checks.
- Agents: 120 tests, Ruff lint/format and mypy pass. API Ruff lint/format passes.
- Real PostgreSQL tests now include a worker-to-derivative publication check as well as source identity, upload crash/replay, lease fencing and permission checks. These are included in the CI foundation job; no passing CI/database/container result is claimed here.
- Five files from the unapplied GCP host draft were archived outside Git at `D:\NVIDIA\archive\2026-10-21-phase3-gcp-draft`, with SHA256 verification. No live GCP resource, remote secret or Terraform state was changed. Hosting/provider choice remains pending; all new provisioning must use Terraform.
- New media paths, membership and worker configuration are opt-in. Legacy analysis/timeline consumers and existing push deployment remain transitional. This phase does not deliver final exports or prove a complete migrated workflow.
- No live model calls or new provider credentials were used. Token Factory's separate 25 USD email and Toloka's 50 USD credit remain pending; neither blocks these media checks.
- `npm ci` reports 13 dependency audit findings (4 moderate, 7 high, 2 critical). These existing dependency findings were not resolved by an unrelated forced upgrade; deployment readiness still requires triage.

Commit/push delivery is separate from deployment acceptance. Do not poll deployment after push. The owner subsequently approved Phase 4 with dummy placeholders and deferred testing.

## Phase 4 implementation and deferred acceptance

- Implemented grounded task contracts, explicit fixture records, Token Factory chat/image transport, model discovery, bounded retries/errors, run provenance and generation hashes. Structured outputs cannot invent allowed source/candidate IDs or exceed source windows.
- Added embeddings with explicit model/revision/precision/deployment/normalization/index identity and dimension checks; no index activation occurs here.
- Added frozen-manifest checks, paired recording-group evaluation with uncertainty, critical-regression detection, WER helper and blind A/B review artifacts. Synthetic examples are not baseline outputs or quality results. Human review, provenance audit and full pipeline verification remain mandatory.
- Added operator CLI, configuration-only status endpoint and setup instructions. Live runs require both a real key and explicit enablement; dummy values fail preflight. Current runtime defaults make no external inference call. No new GitHub secret was populated with a fake value.
- Prepared eight deferred contract/transport/evaluation tests. At owner request, no local runtime suite, fixture execution, model discovery, benchmark or live call was run. Static lint/format, Python syntax, agent typing, generated API types and documentation checks are recorded separately from runtime acceptance.
- Speech serving remains unavailable pending a verified audio adapter. Original-frame extraction/full-window orchestration and durable editorial evidence integration remain Phase 5 work. No best/latest model is claimed without account discovery and quality evidence.
- Two prior configuration Git blobs were preserved outside Git at `D:\NVIDIA\archive\2026-10-21-phase4-config-reference`, with hashes. No functioning legacy analysis files were retired while later consumers still depend on them.
- Existing CI/deployment remains enabled and may execute checks after push. No deployment polling, paid hosting, provider credential validation or complete editor cutover is included.
