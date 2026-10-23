# Phased build plan

Updated 23 October 2026 Asia/Dhaka. Work branch: main. Phases 1–9 implementation is committed. The owner asked to revise Phase 10 as one complete application/infra/data/AI cutover and move demo production into a separate Phase 11. This is planning only: no Phase 10 resources, migrations or deletions are authorized yet. The owner will choose the coding model when implementation starts.

Latest plan revision: do not ship the Phase 9 portable entrypoint as a parallel product path. Phase 10 must unify the product onto one canonical runtime, then retire every replaced legacy runtime/configuration in the same coordinated cutover. Keep existing auto-deploy disabled until its replacement workflow is ready. New infrastructure remains Terraform-managed. Do not provision, migrate, delete, publish, or make paid calls before Phase 10 is explicitly started and its host/model/budget inputs are known. Phase 11 is the demo and submission package, after Phase 10 acceptance. Read [Product direction](PRODUCT_DIRECTION.md) and [Quality strategy](QUALITY_STRATEGY.md) before implementation.

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

Before each phase, present its scope, observable result and any paid/external dependency. The owner approves that phase. Implement and report actual results and remaining limitations. The latest owner instruction defers runtime tests for Phases 4 through 7; keep static checks and automatic CI, record all acceptance gaps, and do not spend live credits. If a major choice changes scope or cost, return with the concrete changed proposal. No blanket permission to execute all phases is inferred.

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

Phase 7 implementation: revision-pinned native/FCP7 export jobs, original hash verification, authenticated artifacts and local relink helper. XML scope is deliberately bounded; mixed-rate, scaling and nonzero audio-offset interchange remain blocked pending parity verification. Actual Premiere acceptance remains pending. See [editable export setup](EDITABLE_EXPORT_SETUP.md).

## Phase 8 Original-resolution scene and film rendering

Scope: pinned timeline render jobs that read originals, perform validated cuts/timebase/audio handling, encode a new output at explicit resolution/FPS/quality, report progress/cancel/error and keep useful export provenance. Implement preflight disk/codec/source checks and cleanup of owned temporary files. Provide an initial MP4 H.264/AAC preset, plus another quality preset only if tested and licensed appropriately.

Outputs: playable high-resolution scene/film output from the same approved timeline, with camera originals unchanged.

Acceptance: original hashes unchanged, output resolution/rate/duration correct, cut frames and audio sync correct, restart/cancel behavior sound, export destination cannot overwrite input, and missing/unsupported HDR/bit-depth cases are explicit. No preview proxy silently substitutes for a missing original. High resolution is not a bit-identical/lossless guarantee.

Credentials: no paid AI key required for rendering an existing approved timeline. Hardware acceleration is optional until validated; CPU rendering provides the correctness reference.

## Phase 9 Complete cloud workflow and portability verification

Scope: complete the editor-facing cloud workflow, verify the reproducible package on a clean test deployment with changed media roots/service addresses, run focused regression/security/recovery checks, compare with the frozen baseline and measure resource use on a stated corpus. Test bounded memory/temp disk, indexing, search, timeline interaction and export. Record observed host/codecs/model configuration honestly. No local GPU trial, customer installation, autoscaling or production-scale load test is required. Use an approved disposable test host or isolated development deployment; a paid cloud resource is never implicit.

Outputs: demonstrated cloud ingest to real analysis/review to timeline to both exports; package redeployment and persistence evidence; measured quality/resource results; future studio dependency list.

Acceptance: no saved-work loss, scope leakage or invalid conform; task-quality and export gates pass; deployment-relative paths/endpoints work after restart/redeploy. Clearly separate software portability demonstrated in cloud from future hardware suitability and no-upload operation. A small demo cannot establish terabyte throughput. Local installation and offline mode are not advertised as delivered and are not release gates.

## Phase 10 Unified application, data and infrastructure cutover

Purpose: replace the old GCP/managed-AI application and the separate Phase 9 portable route with one complete application on one selected, Terraform-managed runtime. The deployed product must not require editors to choose between old and new APIs, project stores, upload routes, queues, AI providers or frontends. Phase 9 packaging is a build/rehearsal aid only; it is not a second production edition.

The owner will select one coding model for this entire phase when build starts. Resume from pushed `main` at the approved phase boundary; preserve the protected `agentic-cinema-final-submission` tag and all phase commits. Never reset/rebase away prior work. No model calls, production changes, resource creation or credential-value retrieval are implied by this plan.

### Phase 10 sequence and hard gates

1. **Freeze the inventory before coding the destructive parts.** Enumerate all legacy data and consumers: Firestore collections/revisions/memberships/jobs; GCS originals, proxies and artifacts; Pub/Sub pending/dead-letter messages; managed ClickHouse service and its database/table contents; Terraform state/backups; model catalogs/prompts/evaluation artifacts; OAuth/team identity mapping; and external exports. Use operator access in each account. Record counts, bytes, hashes, owners, retention and legal rights without printing secret values. GitHub secret-name inventory is not secret-value access or proof a provider account still works.
2. **Resolve the data-recovery gate.** On 23 October, read-only GCP checks found project `trimbin` in `DELETE_REQUESTED`, billing disabled, and no application Cloud Run, VM, GCS bucket or load-balancer assets in the successful Cloud Asset Inventory result. Direct Cloud Run/storage queries against that deleting project returned `CONSUMER_INVALID`/404. IAM, Workload Identity, service-usage and logging metadata remained. The `essential-science-lpr8b` project could not be fully inventoried with this account's permissions. Managed ClickHouse is a separate provider and its current service/data state was not verified. These results do not establish that deleted GCP data is recoverable. Locate and restore real backups or obtain provider-side inventory before declaring a complete data migration. If a source is irretrievable, stop and obtain the owner's explicit decision on what historical records may be absent; never fabricate or silently seed replacement records.
3. **Map every feature into the single target.** Create a route/service/config matrix from old feature to canonical implementation. Migrate useful current UI and editorial behavior into the PostgreSQL/filesystem/Nebius-capable app. Port old Firestore-only operations that remain required, or retire a feature only with a written owner-approved scope decision. Replace GCS signed transfer with the controlled media library, Pub/Sub with PostgreSQL jobs/outbox where semantics match, managed ClickHouse with the self-hosted ClickHouse service, and Vertex/Gemini with the evaluated selected model adapter. Preserve Google OAuth only if the owner still chooses it as an identity mechanism; it must not imply Google Cloud application hosting. Do not trade off model or export quality.
4. **Build one runtime and one configuration contract.** Move the Phase 9 route implementations into the canonical API/UI and make every supported editor journey use those same project identities, memberships, filesystem media IDs, PostgreSQL state/jobs, self-hosted ClickHouse projections, selected AI adapters, timelines and exports. Remove the parallel `app.portable`/portable overlay as a production entrypoint once the canonical entry works. Replace GCP Terraform/workflows, Cloud Run/GCS/Firestore/PubSub/managed ClickHouse provisioning, and Vertex/Gemini runtime setup that the chosen target replaces. Keep only separately justified identity or external services. Generate a credential/variable retirement map; do not delete shared credentials merely because their names look legacy.
5. **Provision and rehearse one complete target.** After the owner approves platform, exact host budget, model identity/access and retention, write Terraform for all required hosts/network/volumes/secrets/ingress and deploy a disposable copy of the complete canonical application. Do not expose a partial parallel editor. Verify fresh installation, configured endpoints/roots, real model calls, migrations, ClickHouse permissions and indexes, source integrity, queue recovery, authorization and both exports. Record actual model/version/license, machine, image digests and limits.
6. **Snapshot, copy, reconcile and prove.** Quiesce all old writers and queue publishers. Take verified, restorable snapshots of every source system and media volume; keep an untouched rollback copy outside the new deployment. Import into mapped target records with stable IDs, explicit legacy-to-new identity mapping, idempotent checkpoints and a final delta pass. Verify per-project record counts/revisions, source hashes/bytes, attachments, completed/pending job dispositions, timeline references, ClickHouse projection revision and account access. Rebuild derived proxy/vector indexes from preserved originals/evidence where safe; preserve their model/config provenance. Reopen the editor only after mismatches are zero or a specific owner-approved exception is logged. Never delete the only copy during import.
7. **Make one coordinated cutover.** Put the old editor into read-only/maintenance mode, apply final delta, deploy the already rehearsed single target, switch the single public route/domain and worker dispatch, then perform the full acceptance checklist. Freeze writes again and roll back to the preserved compatible system/snapshot if any integrity or quality gate fails. Do not accept edits in two systems and attempt a later merge.
8. **Retire replaced infrastructure/configuration after acceptance.** First prove the deployed canonical app and recovery no longer read the old stores/providers; then disable old workflow triggers, remove obsolete SDK/config references and GitHub Secrets/Variables, and retire remote resources only when ownership, backups, billing and rollback state are verified. The GCP project is already deletion-requested and its billing is disabled; do not issue another destroy blindly. Recheck managed ClickHouse independently. Keep truthful provenance and licensing. Remove obsolete code/config from the active path, not the protected historical tag or Git history.

Phase 10 outputs: one canonical app/runtime and deployment workflow; complete inventory and migration ledger; reproducible Terraform deployment; tested restore and rollback evidence; confirmed secret/resource retirement; current architecture and feature matrix. **Demo video, narration, judge-specific walkthrough, public release/tag and submission publication are excluded from Phase 10.**

Phase 10 acceptance requires a real restored/counted data source or an explicit documented data-loss decision; no lost accepted writes; no split canonical projects; original files unchanged; no cross-project access; real selected-model execution; verified queue/restart/backup recovery; actual Premiere interchange and source-to-render frame/audio checks for claimed formats; agreed model-quality and license gates; and a single successful end-to-end run on the selected host. Static tests or the acceptance-register hash check alone do not pass these gates.

Dependencies are decisions/access, not placeholders: selected host/provider and written maximum budget; production model choice, access and licensing; account owner for ClickHouse/GCP inventory and backups; OAuth/team account policy; cleared footage and rights; actual NLE validation. If any source data cannot be restored or a critical quality/compatibility gate fails, report the exact gap and stop the cutover; do not delete the legacy recovery path to meet a date.

## Phase 11 Demo and submission (separate phase)

Start only after Phase 10 cutover acceptance. Use the single deployed canonical app, an approved cleared-footage demo project and a least-privilege judge account. Prepare and rehearse the real workflow: sign in/project → inspect indexed footage → show actual Nemotron run and source-grounded result → correct/select evidence → save and preview timeline → play the completed MP4 → show a Premiere-imported/relinked XML only if that exact build passed Phase 10 NLE checks. Identify precomputed analysis/render as completed runs; never present fixture output or edit out waiting in a way that implies live latency.

Capture the screen and narration as a separate activity. Build a factual English script/shot list and captions from the accepted application, record a public video under the official limit, then verify the final video has no secrets/private footage, readable text, clear audio and a working submission URL. Explain the old-to-new substantial update honestly and distinguish measured results from future studio/terabyte claims. Prepare repository/license/setup, public demo/test URL, judge credentials/access window, model/tool feedback and final English submission. Recheck official rules/FAQ/deadline at this phase; retain judge access through the required window. Do not publish or submit until explicitly authorized.

Phase 11 outputs: reviewed short demo video and script, judge walkthrough/access instructions, final measured evidence summary, prior-work disclosure and submission draft. Acceptance means every depicted action was observed on the accepted Phase 10 build; the video URL is publicly playable; the demo account is tested; submission text matches the evidence and rules.

## Dependency and schedule notes

Main engineering order remains 1 → 2 → 3 → 5 → 6 → 7 and 8 → 9 → **10 unified cutover → 11 demo/submission**. Phase 4 adapter work follows Phase 2. User requested the model choice only when Phase 10 implementation starts. Phases 10 and 11 are not yet authorized to execute; this plan update does not provision, migrate, delete, publish or call a model.

Earlier date estimates are stale; do not infer remaining time or promise a cutover. Phase 10 is a complete migration with explicit data-recovery and quality gates, not a deadline-driven partial release. Phase 11 begins only after acceptance.

Quality is not a deadline adjustment knob. If the evaluated pipeline does not beat the baseline on its declared goals while preserving critical-task quality, do not claim it does. Missing hardware/credentials are reported as unverified gates; they are not reasons to quietly choose an inferior substitute.

Keep customer/on-premises installation, hardware procurement/certification, fully offline inference, Kubernetes/autoscaling, advanced transitions, grading, titles, speed effects, automatic music, model fine-tuning, a native desktop shell and broad NLE coverage outside this delivery unless separately approved.

## Documents maintained with the build

Product direction, quality strategy, requirements, architecture, configuration and phase status start here. Phase 1 refines the evaluation protocol and adds the UX specification, data/timeline contract and current capability matrix. Later phases add reproducible development/package setup, the fixed cloud deployment runbook, tested export compatibility, measured quality/resource results, network boundaries and final submission guide. Every diagram must match the implemented path; no historical claims or conceptual screens are passed off as runtime proof.

Phase 8 implementation: original-fed SDR MP4 jobs, bounded lossless raw scratch, sample-boundary audio, progress/cancel and streamed downloads. Initial preset rejects mixed-rate/scaling/HDR/unknown color metadata. Runtime fidelity and the broader render release gate remain pending. See [render setup](RENDER_SETUP.md). Phase 9 was subsequently authorized.

Phase 9 implementation: scoped project discovery and `/studio` navigation, portable API entrypoint, locked-dependency image recipes, frontend/gateway Compose overlay, immutable complete-source packager and private acceptance register. Runtime testing remains deferred, so clean redeploy, recovery, quality and measured resource acceptance are pending. See [portable workflow runbook](PORTABLE_WORKFLOW.md). Phase 10 is the next approval boundary.
