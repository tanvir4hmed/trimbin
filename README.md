# Trimbin

Film footage review, grounded AI evidence, human-approved selections, frame-based timelines and original-fed export.

**[Open application](https://trimbin.qleam.com)** · **[Submission copy pack](docs/SUBMISSION_ARTICLE.md)** · **[All-tool cost estimate](docs/COST_ESTIMATE.md)** · **[Run / build / operate](docs/RUNNING.md)**

One AWS-hosted application uses PostgreSQL, self-hosted ClickHouse and encrypted filesystem media. NVIDIA Nemotron vision/reasoning and Qwen embeddings run through Nebius Token Factory; Whisper runs on the deployment CPU. One saved scene/film timeline feeds native/FCP7 editable bundles and supported original-resolution MP4 output.

![Trimbin system overview](docs/diagrams/system-overview.png)

## Diagrams and system design

| Separate diagram | View / download | Editable source |
| --- | --- | --- |
| Overall system | [PNG](docs/diagrams/system-overview.png) | [SVG](docs/diagrams/system-overview.svg) |
| AWS infrastructure, security and deployment | [PNG](docs/diagrams/aws-infrastructure.png) | [SVG](docs/diagrams/aws-infrastructure.svg) |
| AI models, deterministic tools and retrieval | [PNG](docs/diagrams/ai-and-tooling.png) | [SVG](docs/diagrams/ai-and-tooling.svg) |
| Media-to-review-to-timeline-to-both-exports flow | [PNG](docs/diagrams/editorial-workflow.png) | [SVG](docs/diagrams/editorial-workflow.svg) |

The [design atlas](docs/SYSTEM_DESIGN.md) displays all four images, component responsibilities, network connections and rebuild instructions. These show the current cloud PoC; future studio installation and local GPU hosting remain separate validation.

## Start here

Open an authorized project, ingest cleared footage, inspect real analysis, correct/select ranges, save a timeline revision and request editable output or a supported SDR render. Sign-in credentials are supplied privately; judge access is not embedded in this repository. [Running instructions](docs/RUNNING.md) cover local tests, image builds and operator prerequisites. Python 3.12, uv, Node.js 22/npm and FFmpeg are used; actual containers require Linux Docker Engine/Compose or a working Linux container backend.

Large originals stay on deployment storage. Browser uploads and outbound model frames/text still cross the internet in this installation. Future studio SSD/NAS placement does not mean this cloud release operates offline or proves terabyte throughput. The checked-in Terraform has account-specific domain/certificate/WAF prerequisites; it is not a generic one-click installer.

## Basic whole-application cost

| Category | Illustrative USD/month |
| --- | ---: |
| Hosting, disks, network identity, backup/registry storage and small-request allowance | $165.17 |
| All active vision/reasoning/embedding APIs | $2.56 |
| **Total before tax and promotional credits** | **$167.73** |

Assumes a continuously running 4 vCPU / 16 GiB host, current 40 + 200 GiB disks, small storage/traffic, 300 vision calls, 100 reasoning calls and explicitly declared token averages. It is not a measured cost per movie. Whisper, FFmpeg, PostgreSQL and ClickHouse share hosted compute; optional partner APIs are not used. Read the [bill of materials, quantities, formulas, official rates and credit treatment](docs/COST_ESTIMATE.md).

## Complete documentation index

Every active guide is linked below. Contracts specify required behavior; status/evidence distinguish implementation, generated-fixture checks and open acceptance gates.

### Product, requirements and submission

| Guide | Contents |
| --- | --- |
| [Product Direction](docs/PRODUCT_DIRECTION.md) | Motivation, current scope and future studio package |
| [Requirements](docs/REQUIREMENTS.md) | Competition/product requirements and acceptance policy |
| [Build Plan](docs/BUILD_PLAN.md) | Build phases and authorized cutover scope |
| [Phase Status](docs/PHASE_STATUS.md) | Current phase status and outstanding work |
| [Quality Strategy](docs/QUALITY_STRATEGY.md) | Quality policy and paired evaluation |
| [Submission Strategy](docs/SUBMISSION_STRATEGY.md) | Positioning and improvement ledger |
| [Submission Article](docs/SUBMISSION_ARTICLE.md) | Copy-ready English submission fields and cost table |
| [Submission Checklist](docs/SUBMISSION_CHECKLIST.md) | Video, judge access, rights and final submission tasks |

### System, implementation and operation

| Guide | Contents |
| --- | --- |
| [System Design](docs/SYSTEM_DESIGN.md) | Four illustrated system/infra/AI/workflow diagrams |
| [Architecture](docs/ARCHITECTURE.md) | Canonical application and network architecture |
| [Deployment Design](docs/DEPLOYMENT_DESIGN.md) | Terraform hosting, rollout and recovery |
| [Aws Cutover](docs/AWS_CUTOVER.md) | Actual inventory, preflight evidence and limitations |
| [Capability Matrix](docs/CAPABILITY_MATRIX.md) | Implemented features mapped to evidence and open gates |
| [Cost Estimate](docs/COST_ESTIMATE.md) | Every active tool/API: usage, unit rates and calculations |
| [Running](docs/RUNNING.md) | Hosted use, local checks/builds and operator prerequisites |
| [Configuration](docs/CONFIGURATION.md) | Variables, secrets and model identities |
| [Foundation Setup](docs/FOUNDATION_SETUP.md) | Disposable database development/CI and restore |
| [Portable Workflow](docs/PORTABLE_WORKFLOW.md) | Source package and portability boundaries |

### Editorial workflow and contracts

| Guide | Contents |
| --- | --- |
| [Ux Design](docs/UX_DESIGN.md) | Interaction design and implemented scope |
| [Data Contract](docs/DATA_CONTRACT.md) | Identity, timing, canonical revisions and recovery |
| [Model Contract](docs/MODEL_CONTRACT.md) | Tasks, provenance and evaluation protocol |
| [Export Contract](docs/EXPORT_CONTRACT.md) | Editable/render requirements and acceptance cases |
| [Media Setup](docs/MEDIA_SETUP.md) | Uploads, mounted roots and immutable originals |
| [Inference Setup](docs/INFERENCE_SETUP.md) | Model adapters, batching, speech and embeddings |
| [Evidence Setup](docs/EVIDENCE_SETUP.md) | Corrections/selections, projection and retrieval |
| [Timeline Setup](docs/TIMELINE_SETUP.md) | Canonical film/scene and retained Film API facade |
| [Editable Export Setup](docs/EDITABLE_EXPORT_SETUP.md) | Native/FCP7 generation and NLE limits |
| [Render Setup](docs/RENDER_SETUP.md) | Original-fed SDR render and fidelity limits |

## Source, automation and developer references

- [API source](api/app) · [Agents and prompts](agents/trimbin_agents) · [Web application](web)
- [Production Compose](deploy/production/compose.yaml) · [AWS Terraform](infra/aws) · [CI](.github/workflows/ci.yml) · [Main deployment](.github/workflows/deploy-trimbin.yml)
- [Model catalog](config/model-profiles.production.json) · [Embedding identity](config/embedding-identity.production.json) · [Placeholder environment example](.env.example)
- [SVG generator](tools/build_architecture_diagrams.py) · [PNG renderer](tools/render_diagrams.cjs) · [Source package tool](tools/package_portable.py) · [Evaluation tooling](eval)
- [Contributor/agent agreement](AGENTS.md) · [Security and privacy boundaries](SECURITY.md) · [Apache 2.0 license](LICENSE)

## Evidence and limitations

Recorded AWS preflight exercised real NVIDIA inference, uploads, human decisions, shared Film/timeline revisions, semantic retrieval, both editable bundles, original-fed 1080p render and isolated backup restore. Linux API: 602 passed / 18 skipped; agents: 122 passed; web: 40 passed. See the [cutover report](docs/AWS_CUTOVER.md) for scope. A pushed commit does not prove its later deployment completed; those runs were not polled after pushing.

Trimbin reuses and substantially expands an existing editorial codebase. The protected historical source tag and license provenance remain; retired references/configuration are archived outside Git. Historical movie data was not recovered or fabricated. Paired quality improvement and actual Premiere import/relink remain unverified. Current render supports a declared SDR subset, not every NLE feature. Demo recording and submission/judge-access preparation remain separate work.

## License

Source: [Apache 2.0](LICENSE). Models, codecs, datasets and footage retain their own terms. Preserve notices and asset rights.
