# Phased build plan

Updated 21 October 2026 Asia/Dhaka. Work branch: main. The owner authorized Phase 6 canonical scene and film timeline assembly. Continue with placeholder credentials and deferred runtime testing; static checks, commit and push are included.

Latest owner instruction: implement Phase 6 on main; preserve automatic deployment and stop without waiting for deployment. All new infrastructure remains Terraform-managed. No new paid resources or live model experiments are included. Read [Product direction](PRODUCT_DIRECTION.md) and [Quality strategy](QUALITY_STRATEGY.md) before making build decisions.

## Why this edition exists

Large movie files, transfer constraints and the earlier workflow's infrastructure and delivery gaps motivate this expansion. Deliver the complete editorial workflow in a cloud-hosted experiment with portable self-hosted services. Staged/uploaded originals reside on the deployment storage. Future studio SSD/NAS and suitable GPU hardware can build on the same interfaces; actual on-premises installation is outside this hackathon. The PoC must deliver a coherent user experience, not only an architecture diagram. See SUBMISSION_STRATEGY.md for the improvement/evidence ledger.

Open models provide a route to self-hosted inference and lower recurring API dependence. Quality must improve on the preserved paid-model workflow: no critical-task regression is accepted for cost, implementation simplicity or deadline convenience. First evaluate quality, then verify competition and license compatibility; both must pass. Optimize cost and speed only among quality-passing choices. Neither cost savings nor superior output is assumed from openness or model version alone.

The comparison is the preserved baseline: stronger source ownership, tested analysis quality, reliable revision handling and useful delivered files. Repainting an existing interface or renaming a provider is insufficient evidence of this product change.

## Agreed decisions

- Work on main, preserving the already pushed baseline milestone.
- Deliver a working cloud edition with deployment-relative media roots and reusable service contracts. Local installation, certified hardware, offline proof, Kubernetes and autoscaling are deferred. Initial hosting uses one host or a small fixed deployment; no scaling platform is required.
- Retain ClickHouse and self-host it. Do not spend the migration budget replacing all its queries merely to avoid a managed-service charge.
- Use PostgreSQL as the proposed portable operational store and durable job queue. Preserve transaction, outbox, command receipt and revision semantics when replacing provider-specific services.
- Keep camera originals unchanged and use them for final render. Proxies are for analysis/playback, with a validated mapping back to source timing.
- Target Best Apps and Agents with meaningful Nemotron calls through Token Factory. Compare current suitable models and supported modalities against quality gates; do not assume account availability, a rented GPU budget or that one model covers all tasks.
- Target measured improvement beyond the paid-model baseline. Do not trade away hard examples, temporal/image/audio evidence, critical-task accuracy or export fidelity to fit a cheaper model or smaller machine.
- Preserve human creative authority. AI may propose source-grounded sequences; the editor approves or changes them.
- Deliver both editable timeline export and playable high-resolution scene/film output. First interchange target is Premiere through tested FCP7 XML.
- Replace active documentation, diagrams and obsolete branding with current evidence. Keep needed provenance and license notices accurate.
- Credentials go to GitHub Secrets; configuration goes to Variables. Missing optional credentials must not stop independent local work.

## Planning work completed

Re-read the official rules, overview and FAQ; inventoried actual workflow/configuration references; checked remote secret names without values; moved 53 prior reference files into an external local archive at `D:\NVIDIA\archive\2026-10-20` and verified SHA256 preservation. New planning documents replace stale entry points. The latest revision removes actual local installation and scaling from this submission, adds the cloud package and improvement evidence ledger, and retains quality/export gates. No application migration, secret deletion, deployment or paid provisioning was performed. Planning documents are included in the Phase 1 milestone commit.

## Phase approval process

Before each phase, present its scope, observable result and any paid/external dependency. The owner approves that phase. Implement and report actual results and remaining limitations. The latest owner instruction defers runtime tests for Phases 4 through 6; keep static checks and automatic CI, record all acceptance gaps, and do not spend live credits. If a major choice changes scope or cost, return with the concrete changed proposal. No blanket permission to execute all phases is inferred.

The owner approved the first implementation phase including commit/push, with existing push-triggered deployment preserved. Stop after push; do not poll deployment. Later phase proposals should state whether they include push and any new provisioning. Existing deployment is authorized by this instruction; new paid infrastructure is not.

## Phase 1 Specifications design and main CI control

Scope: turn the proposals into reviewable product, data, model, UX and export contracts; define hosted project startup, controlled upload/staged-media flows, timeline screens and error states; regenerate architecture/workflow diagrams from those contracts. Establish the current implementation/capability matrix, actual paid-output baseline availability, held-out evaluation design and the improvement criteria before selecting cheap/easy substitutes. Preserve working behavior worth retaining. Refine the new README/security/setup structure around the current product without stale competition branding. Preserve legal notices.

Make credential-free CI run on all pushes, including main, and pull requests; preserve the existing deployment triggers and manual-only destroy workflow. Avoid concurrency cancellation between standalone CI and the reusable deployment gate. Document the current imperative image rollout gap and the Terraform-owned target. Do not delete remote resources. Commit/push is included; deployment completion is not monitored.

Outputs: approved contracts, screen/workflow design, architecture diagrams, dependency order, credential-free CI and documented Terraform rollout path.

Acceptance: main checks are triggered, ordinary checks need no paid secrets, the existing automatic deployment path is preserved as requested and its transitional runtime is disclosed, documentation identifies proposed versus implemented capabilities, and the local archive is absent from commit/build payloads. Product direction, no-quality-concession policy and comparative evaluation criteria are traceable in every core specification. No runtime data-schema conversion yet.

Credentials: none for design/local checks; authenticated GitHub access for approved push.

## Phase 2 Unified configuration and self-hosted foundation

Scope: implement the new settings registry, `.env.example`, per-service capability checks and configuration tests. Create pinned portable service definitions for development and the fixed cloud deployment for ClickHouse and PostgreSQL with volumes, separate writer/reader users, migrations, health checks and backup/restore instructions. Support private local protocol settings rather than assuming a hosted HTTPS endpoint. Introduce operational repository/job interfaces and transactional schema compatible with existing revisions/outboxes.

Select an approved host/provider before preparing Terraform-managed infrastructure and bootstrap/rollout definitions following [deployment design](DEPLOYMENT_DESIGN.md). Preserve push-triggered deployment while replacing ownership deliberately; do not use imperative cloud mutations as the new source of infrastructure truth. Creating new paid resources still requires an approved host/budget.

Register available provider/deployment credentials in GitHub Secrets only when actually supplied; generate fresh self-hosted database and session secrets through ignored files or direct secure input. Optional integrations are disabled by missing keys. Record the exact legacy retirement map privately; remote secret removal waits for verified cutover.

Outputs: reproducible development foundation and one authoritative configuration contract.

Acceptance: clean startup/restart, migration compatibility including indexes, read-only isolation, persisted state after restart, recoverable backup, and no-secret fixture tests. Runtime imports must not require cloud credentials merely to test pure business logic.

Dependencies: container/runtime installation may be required on this PC; Docker is not currently on PATH. Installations occur only within the approved phase. No paid host is provisioned by default.

## Phase 3 Deployment media ingest and processing

Scope: add deployment-mounted allowed-root registration plus authenticated controlled demo upload/staging, stable source IDs/fingerprints, rational rates and source timecode/audio metadata, resumable indexing, duplicate detection, safe local range delivery and media relinking. Adapt FFmpeg proxy/sprite/audio work to local sources and durable jobs. Bound temporary storage and CPU work; add useful unsupported-codec and missing-file outcomes. Original mounts are read-only; derivatives use separate roots.

Outputs: footage on the deployment volume enters the dedicated media library, with durable playback references and metadata for later timeline/export consumers. Legacy editorial routes migrate in later phases. A browser on another computer uploads/stages footage explicitly; its local path is not a server path. No customer-PC installation is required.

Acceptance: unchanged source hashes; duplicate basenames distinguished; folder moves/root remapping; no symlink/path escape; interrupted job recovery; source/proxy timing checks; missing media and unsupported formats visible. A small controlled corpus is sufficient for engineering acceptance, not a terabyte throughput claim.

Credentials: none beyond local database/session setup. Existing FFmpeg and ffprobe are available on this PC, but exact codec support needs validation.

## Phase 4 NVIDIA task adapters and quality evaluation

Scope: implement account model discovery, task-specific payload/schema adapters, explicit fixture/nebius modes and a documented future self-hosted endpoint contract, provider errors/timeouts and new cache/index generation identities. Benchmark current suitable image/video/audio/reasoning/embedding candidates following QUALITY_STRATEGY.md. Establish a cleared gold set and freeze actual paid-model baseline outputs before comparing replacements. A code tag or generated fixture is not a substitute for those outputs. Verify denser or original-detail analysis where proxy/sampling choices could lose critical evidence.

Quality measurements: slate correctness/abstention, action coverage, timing error, false continuity claims, attempt boundaries, transcript accuracy for the actual language, retrieval relevance, valid-output rate, latency, retries and cost per source minute. Difficult editorial cases get independent human annotation where possible. Optional partner services can help but are not required to collect an initial owner-reviewed set.

Outputs: validated adapters, recorded model IDs/revisions and a task-to-model decision showing which candidates pass the baseline quality gates. Cost/speed comparisons are secondary results among passing candidates, not reasons to accept a failed quality gate.

Acceptance: contract validation rejects invented IDs/out-of-bounds times; no old cached result masquerades as new inference; vectors are versioned and corpus/query compatibility is checked. Better-than-baseline claims require held-out task evidence and editor assessment; no critical category is hidden by an average gain elsewhere. Real inference quality and actual Nebius execution must pass before release. If no eligible open-model pipeline meets the target, report the gap and investigate rather than relaxing the gate or silently introducing a required closed model.

Credential lane: without keys, finish adapters against explicit recorded/synthetic fixtures and report real-model acceptance as pending. Independent later phases may proceed after owner approval, while release stays blocked on the real gate. Local GPU benchmarking is future work and is not a submission blocker. This PC has Intel Arc and approximately 32 GB RAM, not an enumerated NVIDIA GPU. A cloud GPU experiment is optional only after a separate access/budget decision; Token Factory credit is not assumed to fund it.

## Phase 5 Grounded evidence review and retrieval

Scope: connect completed analysis to findings/moments/attempts, slate placement, comparison and scoped structured/text/vector retrieval. Preserve editor corrections and original source intervals through re-analysis. Port mutable editorial state to the operational repository with outbox delivery to ClickHouse. Recreate bounded quality reporting without assuming it measures recall or artistic correctness.

Outputs: analyze/find/review/correct/select works across the new storage and model boundaries.

Acceptance: authorization and project isolation; retractions and retries; failed runs retain previous complete evidence; stale writes rejected; reader cannot mutate the archive; unavailable models/search do not silently become empty successful results.

Credentials: fixture mode is adequate for deterministic integration checks; provider-dependent quality is inherited from the open Phase 4 gate.

Implementation status: the dedicated evidence workspace, revisioned commands, bounded analysis worker and ClickHouse projections are implemented. Runtime acceptance and real-model quality remain deferred. See [evidence setup](EVIDENCE_SETUP.md) for exact boundaries; automatic attempt segmentation and speech are not claimed.

## Phase 6 Canonical scene and film timeline

Scope: implement one precise timeline representation for selected ranges, linked audio, occurrence IDs, sequence settings and referenced evidence revisions. Build missing scene/project timelines from selected ranges; preserve intentional order and support trim/reorder/repeat/remove, undo/redo and explicit saved revisions. Preview and export consume the same saved snapshot. Add bounded AI draft proposals only if grounded adapters are ready; manual assembly must remain usable.

Outputs: a user can approve a scene or film timeline ready for both export routes.

Acceptance: same clip repeated at different ranges; fractional/mixed rates with explicit mapping; audio offsets; preserved saves after edits; failed saves/retries; missing sources flagged; draft acceptance does not overwrite another saved revision.

Credentials: none for manual assembly and deterministic preview.

Phase 6 implementation: canonical source-frame occurrences, rational conform, linked audio metadata, saved revision preview, manual arrangement and history restoration are added. Browser playback is approximate; actual conform/export acceptance remains pending. See [timeline setup](TIMELINE_SETUP.md).

## Phase 7 Editable timeline export

Scope: write native timeline manifests and a Premiere-compatible FCP7 XML path, using OTIO/adapters where their tested feature support fits. Keep source timebases, camera start timecode, occurrence identity, relative-root relinking and basic audio links. Existing scene EDL/CSV can remain a limited compatibility option, with their actual constraints documented.

Outputs: selected scene/film timeline exported without re-encoding original media, then reopened in the chosen NLE.

Acceptance: schema/structure checks plus an actual Premiere import and original-media relink in a recorded version; repeated sources, ranges, clip order, audio and fractional-rate positions must match. XML parsing alone is not NLE compatibility. Never promise every NLE format or interchange of unsupported effects.

Dependencies: actual NLE access may be delayed. Exporter development continues without it; Premiere validation remains visibly pending until tested.

## Phase 8 Original-resolution scene and film rendering

Scope: pinned timeline render jobs that read originals, perform validated cuts/timebase/audio handling, encode a new output at explicit resolution/FPS/quality, report progress/cancel/error and keep useful export provenance. Implement preflight disk/codec/source checks and cleanup of owned temporary files. Provide an initial MP4 H.264/AAC preset, plus another quality preset only if tested and licensed appropriately.

Outputs: playable high-resolution scene/film output from the same approved timeline, with camera originals unchanged.

Acceptance: original hashes unchanged, output resolution/rate/duration correct, cut frames and audio sync correct, restart/cancel behavior sound, export destination cannot overwrite input, and missing/unsupported HDR/bit-depth cases are explicit. No preview proxy silently substitutes for a missing original. High resolution is not a bit-identical/lossless guarantee.

Credentials: no paid AI key required for rendering an existing approved timeline. Hardware acceleration is optional until validated; CPU rendering provides the correctness reference.

## Phase 9 Complete cloud workflow and portability verification

Scope: complete the editor-facing cloud workflow, verify the reproducible package on a clean test deployment with changed media roots/service addresses, run focused regression/security/recovery checks, compare with the frozen baseline and measure resource use on a stated corpus. Test bounded memory/temp disk, indexing, search, timeline interaction and export. Record observed host/codecs/model configuration honestly. No local GPU trial, customer installation, autoscaling or production-scale load test is required. Use an approved disposable test host or isolated development deployment; a paid cloud resource is never implicit.

Outputs: demonstrated cloud ingest to real analysis/review to timeline to both exports; package redeployment and persistence evidence; measured quality/resource results; future studio dependency list.

Acceptance: no saved-work loss, scope leakage or invalid conform; task-quality and export gates pass; deployment-relative paths/endpoints work after restart/redeploy. Clearly separate software portability demonstrated in cloud from future hardware suitability and no-upload operation. A small demo cannot establish terabyte throughput. Local installation and offline mode are not advertised as delivered and are not release gates.

## Phase 10 Deployment configuration retirement and submission

Scope: select/approve host and budget, package the tested services, inject secrets, cut over the automatic main deployment to the tested Terraform-managed package, migrate only the agreed demo data, verify access/backup/recovery, and retire obsolete configuration after proving no consumer needs it. Remove obsolete provider code/SDKs/variables from the active migrated path. Remote resource destruction is outside this phase unless specifically included in its approval.

Rewrite final docs/diagrams from actual behavior, scan obsolete branding and broken links, preserve licensing/provenance, record exact model/build/runtime evidence, create a new release tag, prepare demo/test access and English submission text, tool feedback and the 2 minute 45 second video. Include applicable prior-work/change disclosure accurately. Maintain free judge access through the judging period and plan the hosting balance accordingly.

Acceptance: public repository/license/setup verified; no secrets/media/archive leak; real qualifying inference trace; demo and video match behavior; both export claims supported; submitted commit recorded; old secrets removed only after a usage/rollback audit. Fixture-only execution is not a submission-ready result.

Dependencies: real Nebius credentials and remaining necessary model/host/NLE access. Missing Toloka/Tendem/LangSmith/Tavily integration does not alone block this core release. Submission publication or paid provisioning must be included in the approved phase scope.

## Dependency and schedule notes

Main engineering order: 1 → 2 → 3 → 5 → 6 → 7 and 8 → 9 → 10. Phase 4 adapter work follows Phase 2 and can overlap media engineering conceptually; no subagents are assumed. Each phase still receives its own approval. A pending live-model or NLE check can remain an explicit release gate while independent implementation proceeds.

There are approximately ten calendar days to the current deadline. Tentative checkpoint targets are specification/foundation on October 20–21, deployment-media ingest/model experiments on October 21–23, review/timeline on October 23–25, exports on October 25–27, integrated verification on October 27–28, and release/demo packaging on October 29 with October 30 contingency. These are targets, not a promise that a complete production migration fits. Stop and agree revised scope if foundation/model access or export compatibility misses a checkpoint; do not label partial work complete to meet a date.

Quality is not a deadline adjustment knob. If the evaluated pipeline does not beat the baseline on its declared goals while preserving critical-task quality, do not claim it does. Missing hardware/credentials are reported as unverified gates; they are not reasons to quietly choose an inferior substitute.

Keep customer/on-premises installation, hardware procurement/certification, fully offline inference, Kubernetes/autoscaling, advanced transitions, grading, titles, speed effects, automatic music, model fine-tuning, a native desktop shell and broad NLE coverage outside this delivery unless separately approved.

## Documents maintained with the build

Product direction, quality strategy, requirements, architecture, configuration and phase status start here. Phase 1 refines the evaluation protocol and adds the UX specification, data/timeline contract and current capability matrix. Later phases add reproducible development/package setup, the fixed cloud deployment runbook, tested export compatibility, measured quality/resource results, network boundaries and final submission guide. Every diagram must match the implemented path; no historical claims or conceptual screens are passed off as runtime proof.
