# Trimbin

**An AI-assisted footage archive and review desk for editorial teams.**

Trimbin ingests a shoot day, reads slates, asks a person to verify uncertain
placements, analyses every take across its full duration, and presents the
results as timecoded evidence. Editors—not the model—choose the source ranges
that stand for each shot. Those ranges play shot-by-shot as a Coverage Reel,
while every machine finding, correction, selection and comment remains
queryable in ClickHouse.

Built for **Agentic Cinema: The Blockbuster Hackathon — ClickHouse track**.

**Live:** [trimbin.qlitch.com](https://trimbin.qlitch.com) ·
[Anesthesia example project](https://trimbin.qlitch.com/projects/narrative-anesthesia-9) ·
[product guide](https://trimbin.qlitch.com/guide) ·
[verification](https://trimbin.qlitch.com/accuracy)

## What is live

- Four-stage ingest: add files, read slates, verify matches, commit.
- Direct-to-Cloud-Storage resumable uploads, parallel transfer, pause/cancel,
  persisted batch recovery, bounded transient retry and visible failures.
- Slate evidence, manual placement, create-shot and unassigned paths; nothing is
  moved or deleted without a person confirming it.
- Full-duration overlapping-window analysis with timecoded technical,
  continuity and completion findings.
- A three-pane shot-review cockpit with A/B playback, one issue lane per take,
  exact-moment seeking, and Confirm / Dismiss / Adjust finding actions.
- Multiple ordered source ranges from one or many takes for a single shot.
- A Coverage Reel that plays the chosen ranges in shot order and exposes gaps.
- Segment-level natural-language search with playable ranges through the
  official read-only ClickHouse MCP server.
- Timecoded threaded comments, optimistic revisions and append-only history.
- CMX3600 EDL and marker exports using original filenames and measured source
  frame rates when available.

Signed-out visitors can inspect open productions without seeing crew email
addresses. Any signed-in guest can work like an editor in an open production:
upload, review, correct, select and comment. Delete remains owner/uploader scoped.

## Product boundary

Trimbin is not an NLE and does not make a final edit. It does not judge acting,
choose emotional beats, or silently reject footage. Its recommendation is based
only on observable technical quality, continuity and completion evidence. A
human chooses the ranges; the app organizes the evidence and remembers why.

## Architecture

```text
Browser ── resumable upload ──▶ Cloud Storage / CDN
   │                                  │
   └──▶ Cloud Run API ──▶ Pub/Sub ──▶ Cloud Run worker
              │                        ffmpeg + Gemini
              ├── Firestore: mutable operational state
              └── ClickHouse: immutable events, read models, search
                         ▲
                         └── official mcp-clickhouse (read-only retrieval)
```

Firestore owns mutable project, shot, ingest and current-selection state.
ClickHouse owns immutable placement/analysis/finding/decision events, derived
read models and hybrid retrieval. Cloud Storage owns media bytes. Interactive
playback, scrubbing, A/B switching, upload progress and authentication never
wait on ClickHouse.

The API and worker are separate Cloud Run entrypoints from one image: web
requests scale independently from long ffmpeg/Gemini jobs without introducing a
microservice per feature.

## Agent system

The runtime uses the `google-genai` SDK against Gemini on Vertex AI with typed
Pydantic response contracts. Slate identification, full-take analysis, segment
description and archive query planning have narrow responsibilities. The
workflow itself is deterministic orchestration, not an agent: jobs can retry
without repeating settled steps.

The model never emits executable SQL. Retrieval selects parameters for fixed
query shapes, executed through the official `mcp-clickhouse` server as a user
whose `readonly = 1` setting is verified during deployment.

## Repository

```text
agents/         agent contracts, prompts and tests
api/            FastAPI API and Pub/Sub worker
web/            Next.js application
clickhouse/     append-only schema migrations and views
infra/          Terraform for Google Cloud and ClickHouse integration
documentation/ product and technical documentation with diagrams
eval/           deterministic evaluation fixtures
```

Start with [documentation/README.md](documentation/README.md). Deployment notes
are in [docs/deployment.md](docs/deployment.md).

## Verification

The release gate runs API, agent and browser-logic tests, formatting, lint,
static typing, a production web build, ClickHouse migration checks and deployed
smoke checks. Real-footage QA uses the Anesthesia project linked above; generated
scale rows are isolated from published product figures.

## Data and license

The example uses **Filmed Scenes** by Yilmaz, Rietdijk, Primett, Mukhina,
Lotman & Tikka (2025), [doi:10.5281/zenodo.15767853](https://doi.org/10.5281/zenodo.15767853),
licensed CC BY 4.0. Source attribution remains with the project data.

Code is licensed under the [Apache License 2.0](LICENSE).
