# Trimbin

**An assistant editor that never forgets.**

In film editing, the trim bin held every frame you cut away — and editors went back to
it constantly. Digital editing quietly threw that away. Trimbin brings it back: it
organises a shoot day on its own, surfaces only the shots that need a human eye, and
remembers every take it passed over and why.

Built for **Agentic Cinema: The Blockbuster Hackathon** — ClickHouse track.

**Live:** [trimbin.qlitch.com](https://trimbin.qlitch.com) ·
[the workspace](https://trimbin.qlitch.com/project/1) ·
[try it on your own footage](https://trimbin.qlitch.com/sandbox) ·
[our error rate](https://trimbin.qlitch.com/accuracy)

Nothing needs an account.

---

## The problem

A feature shoot produces 30–100 hours of footage. About two hours reach the screen. The
other 98 are not deleted — they sit in bins and on archive tape. But the moment picture
locks, three things vanish for good:

- **The reasoning.** Why take 4 and not take 5 lived only in the editor's head.
- **Findability.** Reopening a two-year-old project needs the same software, the same
  version, relinked media, and someone who remembers.
- **Institutional memory.** Nothing lets a production ask what it has already shot.

Trimbin does the assistant editor's daily job — logging, grouping, triage — and keeps the
notes as a by-product. The archive is not extra work anyone has to do. It accumulates
because the work happened.

---

## What runs today

Verified against the deployed system, not asserted from the code.

| | |
|---|---|
| **Ingest, end to end** | A clip uploaded to a signed URL is measured, read for a slate, embedded, encoded and playing through the CDN in about a minute — no account needed for the sandbox. |
| **Measurement** | Exposure, focus, stability, audio and freeze detection with ffmpeg, in the same pass that builds the proxy. Every finding carries a timecode. |
| **Slate reading** | A board on the front of a clip becomes scene, shot and take. No board is *said to be* no board, and the take is left ungrouped rather than guessed at. |
| **The panel** | Three specialists and a chief compare every take of a setup and write a verdict per take — including the rejected ones, with reasons. |
| **The workspace** | Scene → setup tree, six criteria side by side, every take openable, findings that seek the player to the moment they describe. |
| **Overrides** | An editor picks a different take and says why. Recorded as a new decision beside the panel's, never over it. |
| **Retrieval** | A question in plain language returns takes with their reasons, and the query that produced them. |

## What is not built

Stated because a demo that omits this is the same overclaim as an invented accuracy figure,
and this project made that mistake once already.

- **The assembled cut.** Selected portions do not yet stream as one continuous film, and
  there is no EDL export.
- **Browser upload for a signed-in project.** The API is proven; the form exists only in
  the sandbox.
- **Any accuracy figure.** The number is null, not zero — see below.
- **Sign-in on this deployment**, pending one console step
  ([docs/oauth-client.md](docs/oauth-client.md)).
- **Cloud Trace spans per agent call**, and keyboard shuttle controls.

---

## What it refuses to do

No model has been trained on take selection, because the data has never existed — nobody
recorded which take an editor chose and why. **Trimbin does not claim to judge acting.**
It handles everything around that judgement and hands the editor a decision that takes
seconds instead of an hour.

Nothing is ever auto-rejected. A technically worse take is often the right take.

---

## How it decides

Judgement follows Walter Murch's Rule of Six, the standard framework in film editing.
Emotion (51%) and story (23%) are human territory and Trimbin does not enter them. Rhythm,
eye-trace, planarity and spatial continuity are progressively more objective — that is
where an agent earns its place.

Work splits by what is knowable:

- **Measured, not inferred** — exposure, focus, stability, audio levels, duration. Computed
  with ffmpeg. Deterministic, cheap, testable.
- **Observed by a model** — did the action complete, did the camera move land, does
  continuity hold against the other takes.
- **Left to a person** — whether the performance is right.

Measurements are **relative to the group, never absolute.** If all seven takes are handheld,
that is the language of the scene. If six are locked off and one is not, that one is
probably an accident.

Every finding uses a **closed vocabulary** — an enum passed to the model as its response
schema, so a specialist selects from the taxonomy rather than inventing. That was added
after the panel produced thirty-nine distinct codes across twelve takes with no two
agreeing, which made the archive unqueryable and silently broke scoring.

---

## What the real footage showed

Twelve takes from a published, openly licensed dataset
([Zenodo 15767853](https://doi.org/10.5281/zenodo.15767853), CC BY 4.0) went through the
whole pipeline.

**Measurement found nothing wrong with any of them** — every take within a few percent of
its setup median. That is the correct answer: competent takes have nothing technical to
separate them, and a system that manufactured a confident winner from that would be lying.

**The panel found what measurement could not.** A take that stops mid-sentence. A whip pan
that breaks eye-trace. A wall crossing the foreground for the first sixteen seconds. An
extra stoop to pick up shoes that no other take has.

Every setup came back below the review margin and was flagged for a person. Four out of
four went to a human, which is the honest outcome for four close calls.

---

## Accuracy

Published live at [`/accuracy`](https://trimbin.qlitch.com/accuracy), per project, no
account needed.

**It currently says nothing, and that is deliberate.** Accuracy here means "confident
decisions no editor overturned". No editor has overturned anything yet, so the figure is
**null — not zero**. A system with no measurements is not a system that is wrong every
time, and the interface keeps those apart.

The dataset cannot fill the gap either: its annotation file is an empty template, every
take `pending`, every issue column blank. There is no ground truth to score against. **The
first real figure arrives the first time an editor disagrees with the system.**

What *is* earned is the evaluation set: faults planted at timecodes we chose, and
**6/6 found, 0 false alarms, every timecode within tolerance.** That is a fact rather than
an agreement, and it is the only number on the site with evidence behind it.

The override rate is reported in two halves. Disagreement on a *flagged* call is the system
working as designed. Disagreement on a *confident* call is a real error. One combined
number would flatter us and inform nobody.

---

## Architecture

```
Browser ──▶ Cloud Run: API ──▶ Pub/Sub ──▶ Cloud Run: worker
                │                               │  ffmpeg · Gemini · embeddings
                │                               ▼
                │                     Cloud Storage ──▶ Cloud CDN (/media)
                ▼
    ┌───────────┴───────────┐
    ▼                       ▼
ClickHouse Cloud        Firestore
the logbook             the whiteboard
clips · decisions       projects · members · jobs
embeddings · findings   sandbox quotas
```

Four decisions worth naming.

**The workflow layer is not an agent.** Two hundred clips is an hour of processing with
failures in the middle. Agents answer questions; they are the wrong shape for driving a
long batch. The worker is a plain Pub/Sub consumer that scales to zero.

**Nothing writes SQL but us — and nothing runs it as an admin.** Two separate
questions, and the first version of this got both wrong at once.

Retrieval runs on a fixed query shape with the model choosing only parameters, so the
statement is always ours. It executes through the official `mcp-clickhouse` server, as the
ClickHouse track requires the database to be used at runtime, connecting as
`trimbin_reader` — SELECT on ten named objects, under a profile with `readonly = 1 CONST`.

That user is new. The wrapper opened for weeks with a comment naming a read-only database
user as its primary defence and there was none: the connection was the admin one and a
keyword regex was the only thing in the way. A regex over SQL is a filter, not a boundary.
Every deploy now proves the reader can read and cannot write before anything ships.

**The panel watches proxies, not originals.** That is fairness before cost — proxies are
encoded to one contract, so a model comparing them is comparing footage rather than being
swayed by which take happened to be shot at 4K.

**Every decision is a new row.** An override never edits the panel's verdict. Both are true
things that happened, and collapsing them would erase the disagreement — which is the only
signal this system has about its own quality.

---

## Stack

| Layer | Choice |
|---|---|
| Models | Gemini 3.6 Flash (video, long context) via Vertex AI, **global endpoint** |
| Embeddings | `gemini-embedding-2`, 768 dimensions, natively multimodal |
| Agent framework | None. The `google-genai` SDK directly, with pydantic response schemas. |
| Analytics store | ClickHouse Cloud — clips, decisions, embeddings; reached at runtime through the official `mcp-clickhouse` server |
| Mutable store | Firestore — projects, members, jobs, sandbox quotas |
| Media | Cloud Storage + Cloud CDN, uniform HLS proxies |
| Measurement | ffmpeg filter graph, one decode, two branches |
| API / Web | FastAPI · Next.js 15, both on Cloud Run |
| Scheduled work | Cloud Scheduler → an OIDC-authenticated route |
| Infrastructure | Terraform — everything except one OAuth client Google will not expose |
| CI/CD | GitHub Actions with Workload Identity Federation, no long-lived keys |

**On the agent framework:** the plan called for Google ADK on Agent Engine, and the manifest
listed it. Nothing imported it. The agents are four prompts with typed contracts calling
`generate_content` with a response schema, which is what they turned out to need — and on a
scale-to-zero worker, a dependency the code does not use is cold-start latency for nothing.
Removed rather than left in to look impressive.

---

## Repository layout

```
agents/       one folder per agent, each with an AGENT.md contract and its prompts
api/          FastAPI service and the ingest worker (one image, two entrypoints)
web/          Next.js application
clickhouse/   migrations and the seed generator
infra/        Terraform — nothing exists outside this
eval/         measurement and misplacement harnesses
docs/         deployment, and the one thing Terraform cannot create
```

---

## Running it

Everything is declared in Terraform. There is exactly one manual step, and it is itself
Terraform: the state bucket cannot be created by the configuration that stores state in it.

```bash
# once, by hand
cd infra/bootstrap && terraform init && terraform apply

# thereafter — push to main
git push
```

One value is not Terraform's, and cannot be: Google exposes OAuth client creation through
its API only for organisation-internal consent screens, and this project has no
organisation. See [docs/oauth-client.md](docs/oauth-client.md) — everything downstream of
that one console step is automated.

Setup and required secrets: [docs/deployment.md](docs/deployment.md).

---

## Tests

278 tests across the API and the agents. They cover the shapes that go wrong quietly:
a normalisation that flattens real ratios into placeholders, a quota that returns a
plausible integer while allowing everything through, an enum that stringifies to its class
name and matches nothing.

```bash
cd api && .venv/bin/python -m pytest tests -q
cd agents && .venv/bin/python -m pytest -q
```

Three bugs in this codebase were found by *using* the deployed system rather than reading
it, and each had passed its tests: signed URLs that could not be signed, a queue that never
said which project a clip belonged to, and a signed upload URL missing the header it
required. That is why the rule here is that a thing is done when it runs end to end and a
person can use it.

---

## Data sources

- **Filmed Scenes** — Yilmaz, Rietdijk, Primett, Mukhina, Lotman & Tikka (2025), Zenodo,
  [doi:10.5281/zenodo.15767853](https://doi.org/10.5281/zenodo.15767853), CC BY 4.0.
  Twelve takes across four camera setups. Attribution is recorded in the archive beside
  the rows it produced.
- **Blackmagic Fusion training material** — analysed locally, never published or
  redistributed. It is given away freely and still owned by Blackmagic.
- **Generated rows** — several hundred thousand, at `project_id >= 900000`, to show the
  queries stay fast at scale. Excluded from every published figure *at the view*, not by a
  filter someone has to remember to write.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
