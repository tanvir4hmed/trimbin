# Phase status

Updated 21 October 2026 Asia/Dhaka.

Latest owner direction: revise the plan for a complete cloud-hosted editorial PoC now; implement through individually approved phases. Future studio hardware/software packaging is the direction, not a requirement to install locally during this hackathon. Kubernetes, autoscaling and local GPU certification are deferred. The owner has approved Phase 1, its milestone commit and push. Preserve automatic deployment and do not wait for deployment completion; all new infrastructure is Terraform-managed.

| Phase | Status | Approval and evidence |
| --- | --- | --- |
| 0 Planning and archive | Updated locally | Rules, FAQ and overview rechecked. Cloud PoC scope, improvement ledger, network boundaries and future hardware claims aligned. Previous 53-file archive retained. No runtime or workflow changes in this update. |
| 1 Specifications design and CI control | Complete; included in the start milestone | UX/data/model/export contracts, capability and baseline evidence matrix, workflow/network diagrams, Terraform rollout design, main CI coverage and external archive. Local checks passed; see verification below. |
| 2 Configuration and self-hosted foundation | Not approved | Portable fixed service package; PostgreSQL and ClickHouse; secure configuration. |
| 3 Deployment media ingest and processing | Not approved | Controlled upload/staging and mounted deployment roots, bounded jobs and source integrity. |
| 4 NVIDIA adapters and quality evaluation | Not approved | Nemotron through Token Factory; actual access and comparative quality pending. |
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
