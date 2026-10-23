# Product direction

Owner decision: 20 October 2026, Asia/Dhaka. This supersedes the earlier requirement to install and demonstrate a local PC edition during this hackathon. The owner subsequently authorized completion of the remaining non-demo AWS cutover in one continuous execution; see BUILD_PLAN.md.

## What we are delivering now

A complete working editorial application, demonstrated in a cloud-hosted proof of concept. Cloud infrastructure is our development and demonstration environment for an architecture intended to become deployable inside an editing company's network. We are not installing a customer workstation, buying hardware, or proving offline operation in this submission.

Complete means the declared workflow works end to end: persistent source media, real AI analysis, evidence review, human corrections, selected-range scene/film assembly, saved revisions, editable timeline handoff and original-resolution video export. It does not mean every professional NLE feature or a production-certified hardware appliance. A diagram, simulated analysis or future portability story cannot replace a functioning editorial experience.

## Why revisit the existing project

Large movie-footage collections make transfer and remote storage burdensome, especially where fast, inexpensive connectivity is unavailable. The earlier implementation also exposed provider-specific infrastructure dependencies, recurring inference costs, incomplete final delivery, and the need to preserve source timing and human decisions through retries and re-analysis. These are the engineering problems motivating this edition; claimed customer prevalence and financial savings still need evidence.

Reuse the valuable editorial foundation and substantially expand it. The improvements are portable self-hosted state and media processing, NVIDIA open-model task adapters with measured quality, durable analysis and correction handling, and a shared timeline feeding both exports. The hackathon provides a practical route to evaluate NVIDIA models through Nebius and demonstrate those improvements with a real product.

## Cloud experiment and future studio package

The initial deployment uses a single host or small fixed set of hosts, private service networking, persistent media volumes, self-hosted ClickHouse, PostgreSQL and media workers. No Kubernetes, autoscaling, multi-region design or GPU purchase is in the current scope. Components have configurable endpoints and paths, so moving them later does not require rewriting editorial logic.

The submitted inference route uses Nemotron through Token Factory for the proposed Best Apps and Agents track. This is an external managed service, not an inference process automatically inside our private network. If a quality-critical modality needs another endpoint, verify access, licensing, cost and its role before committing to it; the meaningful Token Factory route remains required for our track.

Future delivery could bundle the software, installation/support and suitable NVIDIA hardware for an editing company or individual. SSD/NAS capacity follows the customer's corpus; storage throughput, temporary space and network bandwidth still affect operation. Hardware sizing must be based on exact models, precision, concurrency and measured workload. Open models make self-hosting possible subject to their licenses; serving costs and hardware requirements do not disappear.

We will not require an actual on-premises installation or local GPU benchmark to finish this hackathon. Those belong to future product validation. Cloud deployment can demonstrate reproducible software packaging and deployment-relative storage; it cannot certify performance on a customer's GPU or prove that their footage never leaves their premises.

## Scope of claims

| Claim | Evidence needed in this edition |
| --- | --- |
| Working cloud edition | Reproducible deploy, real model execution and full editorial-to-export demonstration |
| Portable software foundation | Explicit service interfaces, configurable roots/endpoints, clean redeployment with persisted state and no hardcoded host paths |
| Originals preserved | Source identities/hashes, read-only processing and original-fed exports |
| Better editorial AI quality | Frozen baseline outputs, held-out footage and editor assessment under the quality strategy |
| Future private studio operation | Architecture and documented remaining dependencies; clearly labeled future validation |
| Offline operation, specific workstation performance, terabyte throughput or lower ownership cost | Not claimed from this cloud PoC; require separate measurements |

Demo footage is uploaded or staged on the cloud host. Required model inputs leave the app's private service network for Token Factory. Disclose both boundaries. Do not describe the present demonstration as zero-upload, air-gapped or a completed physical product.

## Quality and human authority

Quality remains non-negotiable: evaluate current suitable models on actual editorial tasks, preserve critical categories, and do not trade quality for lower price or easier implementation. Competition and license compliance must also pass. Any unresolved gap is reported honestly, not hidden behind a cheaper model, sparse sampling or old cached output. See [quality strategy](QUALITY_STRATEGY.md).

AI organizes slates, observes dialogue/actions, retrieves source-grounded moments, compares takes and proposes bounded edits. Findings must cite real intervals and express uncertainty. Editors correct and approve creative decisions. Deterministic software owns frame arithmetic, source access, job recovery and export construction. Manual editing, playback and export of an approved timeline should not need a new model call per interaction.

## Submission explanation

Explain the progression as: an existing editorial prototype exposed practical obstacles; this edition addresses them with a complete portable software workflow and open-model integration, validated in a cloud experiment; a future studio hardware/software package can build on that foundation. Only mark an obstacle solved when the actual demonstrated scope supports it. Future deployment benefits are motivations and hypotheses, not completed customer outcomes.

Preserve truthful provenance and mandatory change disclosure. See [submission strategy](SUBMISSION_STRATEGY.md) for the old-to-new evidence matrix and [build plan](BUILD_PLAN.md) for the phase order.
