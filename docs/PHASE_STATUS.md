# Phase status

Updated 23 October 2026 Asia/Dhaka.

Latest owner direction: revise the plan for a complete cloud-hosted editorial PoC now; implement through individually approved phases. Future studio hardware/software packaging is the direction, not a requirement to install locally during this hackathon. Kubernetes, autoscaling and local GPU certification are deferred. The owner approved Phases 1 and 2, then authorized Phase 3 after the credit/account discussion. Preserve automatic deployment and do not wait for deployment completion; all new infrastructure is Terraform-managed.

| Phase | Status | Approval and evidence |
| --- | --- | --- |
| 0 Planning and archive | Updated locally | Rules, FAQ and overview rechecked. Cloud PoC scope, improvement ledger, network boundaries and future hardware claims aligned. Previous 53-file archive retained. No runtime or workflow changes in this update. |
| 1 Specifications design and CI control | Complete; included in the start milestone | UX/data/model/export contracts, capability and baseline evidence matrix, workflow/network diagrams, Terraform rollout design, main CI coverage and external archive. Local checks passed; see verification below. |
| 2 Configuration and self-hosted foundation | Implemented; local checks passed; container acceptance pending CI | Shared configuration, PostgreSQL revisions/jobs/outbox, pinned database package, recovery tools and CI lifecycle checks. The unapplied GCP target was subsequently archived as an incorrect hosting assumption. Docker/WSL unavailable locally; no paid resources provisioned. |
| 3 Deployment media ingest and processing | Implemented; local checks passed; database/container acceptance pending | Owner authorized phase start. Mounted roots, resumable upload, source integrity, derivatives, scoped playback, PostgreSQL jobs and media UI. |
| 4 NVIDIA adapters and quality evaluation | Adapter/evaluation implementation delivered; runtime tests deferred | Owner approved placeholder credentials and testing later. Model selection, live calls, speech path and comparative quality remain pending. |
| 5 Evidence review and retrieval | Implemented; runtime acceptance deferred | Owner approved Phase 5. Durable corrections/selections, analysis worker, scoped review/search, complete ClickHouse projections and setup documentation. Static verification recorded below. |
| 6 Canonical scene and film timeline | Implemented; runtime acceptance deferred | Owner approved. Frame-based scene/film snapshots, manual assembly, saved preview, undo/redo, history and timing verification path. |
| 7 Editable timeline export | Implemented for documented subset; runtime/NLE acceptance deferred | Native snapshot and FCP7 XML bundles, durable jobs, source hashes and relink helper. Mixed-rate/scaling/audio-offset XML gates remain open. |
| 8 Original-resolution video rendering | Implemented for documented SDR subset; runtime acceptance deferred | Owner authorized continue. Original-fed MP4, bounded scratch, jobs/cancel/progress and downloads. Fidelity gate remains open. |
| 9 Complete cloud workflow and portability verification | Integration/package implementation delivered; runtime acceptance deferred | Owner authorized Phase 9. Studio entry, scoped project discovery, portable API/package, acceptance register. No clean redeploy or quality result claimed. |
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

## Phase 5 implementation and verification boundary

Phase 5 adds the dedicated `/projects/<slug>/evidence` workspace on PostgreSQL membership, registered deployment media, and explicitly configured model modes. Editors can annotate moments/attempts, correct/accept/retract observations, place slate labels, preview ranges, pin selections and request evidence-based comparison/continuity review. Selected text is the reasoning input; this is not a second visual analysis or audio understanding claim. Source analysis uses bounded original-detail sampled frames. Fixture mode explicitly abstains without generating AI findings.

Complete generations publish with lease/latest-request fencing; failed or superseded work preserves the previous active head. Corrections remain revisioned and older corrected findings remain inspectable. Text and semantic retrieval use project-scoped complete ClickHouse snapshots and exact current revisions; missing/stale indexes return explicit unavailable/pending outcomes. Semantic builds and queries require real configured embeddings; none were called.

Static verification: Python Ruff lint/format, compilation, agent type checks, generated API types/frontend TypeScript, documentation links and diff hygiene are checked for this phase. Runtime pytest, browser acceptance, FFmpeg frame extraction, database/container migrations, outbox delivery, real model/vector execution and comparative quality remain deferred. Added tests cover correction/retraction preservation, replay/conflicts, immutable selections, role/project boundaries, source ranges, latest-run/cancellation fencing and window bounds; adding tests is not a passing result. Existing CI stays enabled and may execute runtime suites after push; no CI/deployment success is assumed or polled.

Prior documentation/package references were copied to `D:\NVIDIA\archive\2026-10-21-phase5` with a SHA-256 manifest outside the checkout. No credentials were archived. Existing legacy consumers remain until later migration; Phase 5 does not deliver the canonical film timeline or either full export. Phase 6 remains the next approval boundary.

## Phase 6 implementation and verification boundary

The portable `/projects/<slug>/timeline` page builds independent film/scene sequences from Phase 5 selections. It reuses operational revisions/receipts and the existing film editor's occurrence and undo/redo approach, with a new exact source-frame/rational-FPS contract. It does not migrate legacy decimal-second film data automatically. Saved versions pin evidence, source identity, audio stream/offset, sequence settings and computed duration/quantization. Historical restores produce new revisions; stale writes retain the draft. No model/API token is needed.

Source timing preparation hashes originals and verifies a bounded decoded presentation-timestamp grid before authorizing CFR frame coordinates. Variable-rate, coarse/missing timing, HDR and oversized scan output fail explicitly. Browser proxy playback follows a saved revision, but remains approximate; it is not frame-accurate conform acceptance. Editable XML and final video remain Phases 7 and 8. AI draft acceptance is not exposed while the live grounding/quality gate is pending.

Static checks: Ruff lint/format, Python compilation, generated OpenAPI/TypeScript, frontend typecheck, documentation links and diff hygiene. Added deferred tests cover fractional conform/rounding, repeated occurrence identity, VFR rejection, audio offset, stale writes/replay, authorization and restoration after selection removal. No local pytest, FFmpeg scan, database/container, browser or export runtime acceptance was executed. Existing CI/deploy triggers remain enabled; deployment is not polled. Reference snapshots and hashes live outside Git in `D:\NVIDIA\archive\2026-10-21-phase6`.

## Phase 7 implementation and verification boundary

Revision-pinned native and FCP7 XML ZIP exports are available from the portable timeline page. Jobs reuse PostgreSQL receipts/leases/cancellation, hash originals and publish complete checksummed artifacts. Scoped authenticated downloads and a local hash-verifying root remap helper avoid embedding cloud host paths or packaging footage. No inference key or new cloud resource is required. The existing deployment trigger remains enabled; deployment is not polled.

XML currently supports same-rate/same-dimension CFR cuts, repeated occurrences, supported camera timecodes and aligned mono/stereo first-stream audio with mute/gain. Mixed-rate conform, scaling, nonzero audio offsets and other unsupported cases are explicit XML errors; native manifests preserve their canonical metadata. These limitations remain gates, not passing compatibility claims. Actual Premiere import/relink and frame/audio validation are pending.

Static verification: Ruff lint/format, Python compilation, generated API/TypeScript, frontend typecheck, Compose YAML, documentation links and diff hygiene. Added deferred format/relink and PostgreSQL export request tests. No local pytest, export worker execution, source scan, database/container or NLE test was run. Prior references and hash manifest are outside Git in `D:\NVIDIA\archive\2026-10-21-phase7`. Phase 8 original-fed rendering is the next approval boundary.

## Phase 8 implementation and verification boundary

Original-fed MP4 rendering pins the approved timeline revision and source hashes. The initial CPU preset uses lossless raw video/float PCM scratch and one H.264 CRF 18 slow / AAC 320 kbps delivery encode. Same-rate, same-dimension progressive square-pixel explicit Rec.709 limited-range 8-bit 4:2:0 footage is supported by the implementation; other formats are rejected, never silently downgraded. Mono duplication, stereo first-stream selection, source audio offsets, silence/mute and gain are explicit. This is lossy delivery, not a bit-identical copy or verified Premiere equivalent.

Jobs expose stages and completed cuts, cancellation and errors. Source hashes are checked before and after processing; complete output publication is lease-fenced. Downloads use short-lived scoped tickets and streaming file responses. Disk/time/threads are bounded by existing media configuration; defaults only suit small fixtures. No scale, throughput or runtime fidelity result is claimed.

Static checks cover Ruff, Python compilation, API schema/TypeScript, Compose parsing and documentation links. Deferred tests cover sample-boundary rounding, color rejection, original-frame trimming, silence and request replay/isolation. Actual FFmpeg, PostgreSQL, browser, cancellation/recovery and 4K fidelity acceptance were not run locally. CI/deploy triggers remain enabled and unpolled. Reference snapshots and hashes are outside Git in `D:\NVIDIA\archive\2026-10-22-phase8`. Phase 9 remains the next approval boundary.

## Phase 9 implementation and verification boundary

The `/studio` entry provides password sign-in and PostgreSQL-scoped project discovery, saved-work summaries and connected media/evidence/timeline/export navigation. Portable pages use their own shell without legacy project/dashboard queries. The portable API entrypoint mounts only the current workflow and auth routes; old code/dependencies remain for the existing deployed runtime and later retirement audit.

Added complete-source immutable Git packaging, frontend/backend locked-dependency image recipes, frontend/gateway Compose overlay, private configuration placeholders, and a clean-deploy/remap/recovery runbook. Packaging includes the frontend and license and excludes local private/media/archive files. No container was built or started, no paid host/model was used, and no existing deployment was cut over. Image digests, TLS ingress and per-service secret minimization still require cutover validation.

Added deferred package/evidence-policy tests and PostgreSQL-backed project isolation tests. Static checks cover Python lint/format/syntax, generated API types, TypeScript, Compose parsing, documentation links and diff hygiene. Reference snapshots/hashes are outside Git in `D:\NVIDIA\archive\2026-10-23-phase9`. Deployment remains enabled and will not be polled.

Phase 9 verification is not complete: the owner continues to defer runtime testing. The private evidence register starts with all gates pending; clean redeploy, changed roots/endpoints, live Nemotron, held-out baseline comparison, original-frame/audio/NLE correctness, browser flow, restart/restore and peak resource measurements must still run. The register checks evidence presence/hashes, not factual correctness. Do not equate implementation delivery with these release gates passing. Phase 10 remains the next approval boundary.
