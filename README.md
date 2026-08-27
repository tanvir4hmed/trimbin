# Trimbin

**An assistant editor that never forgets.**

In film editing, the trim bin held every frame you cut away — and editors went back to
it constantly. Digital editing quietly threw that away. Trimbin brings it back: it
organises a shoot day on its own, surfaces only the shots that need a human eye, and
remembers every take it passed over and why.

Built for **Agentic Cinema: The Blockbuster Hackathon** — ClickHouse track.

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

## What it does

| | |
|---|---|
| **Organises the day** | Drop a shoot folder. Slates are read, takes are grouped, proxies are made. No forms, no manual logging. |
| **Narrows the work** | "Six of sixty-eight shots need your eye." The rest were clear calls. |
| **Catches mistakes early** | A clip belonging to another scene is flagged on arrival, not three weeks into the edit. |
| **Remembers everything** | Every take considered, every measurement, every reason, every human override — queryable years later. |
| **Plays the cut** | The selected portions stream as one continuous film. No render, no export. |

---

## What it refuses to do

No model has been trained on take selection, because the data has never existed — nobody
recorded which take an editor chose and why. **Trimbin does not claim to judge acting.**
It handles everything around that judgement and hands the editor a decision that takes
seconds instead of an hour.

Nothing is ever auto-rejected. A technically worse take is often the right take.

---

## How it decides

Judgement follows [Walter Murch's Rule of Six](docs/agents.md#the-framework), the standard
framework in film editing. Emotion (51%) and story (23%) are human territory and Trimbin
does not enter them. Rhythm, eye-trace, planarity and spatial continuity are progressively
more objective — that is where an agent earns its place.

Work splits by what is knowable:

- **Measured, not inferred** — exposure, focus, stability, audio levels, duration. Computed
  with ffmpeg in the same pass that builds proxies. Deterministic, cheap, and testable.
- **Observed by a model** — did the action complete, did the camera move land, does
  continuity hold against the other takes.
- **Left to a person** — whether the performance is right.

Measurements are **relative to the group, never absolute**. If all seven takes are handheld,
that is the language of the scene. If six are locked off and one is not, that one is
probably an accident.

---

## Architecture

```
Clients ──▶ API (Cloud Run) ──▶ Workflow (Pub/Sub + workers)
                                      │
                                      ▼
                          Agent Engine · ADK · 4 agents
                            Slate → Analyst panel → Assembly → Archivist
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
        ClickHouse — the logbook              Firestore — the whiteboard
        append-only history                   mutable state
        clips, decisions, embeddings          projects, members, jobs, notes
```

Two decisions worth naming:

**The workflow layer is not an agent.** Two hundred clips is an hour of processing with
failures in the middle. Agents answer questions; they are the wrong tool for driving a
long batch.

**MCP stays read-only.** A language model with write access to a production database is
one prompt injection away from a destructive query — and a clapperboard is untrusted input
a camera was pointed at. Writes go through a typed service. The Archivist calls MCP at
runtime on every search.

Full detail: [docs/architecture.md](docs/architecture.md)

---

## Stack

| Layer | Choice |
|---|---|
| Agents | Google ADK on Vertex AI Agent Engine |
| Model | Gemini 3.6 Flash — video, long context, caching |
| Embeddings | Gemini Embedding 2 — native multimodal |
| Analytics store | ClickHouse Cloud, via the official `mcp-clickhouse` server |
| Mutable store | Firestore |
| Media | Cloud Storage + Cloud CDN, uniform HLS proxies |
| Measurement | ffmpeg filters, in the proxy pass |
| API / Web | FastAPI · Next.js, both on Cloud Run |
| Infrastructure | Terraform — everything, with no exceptions |
| CI/CD | GitHub Actions with Workload Identity Federation |

---

## Repository layout

```
agents/       ADK agent code — one folder per agent, each with an AGENT.md contract
api/          FastAPI service
web/          Next.js application
clickhouse/   migrations, seed generator, showcase queries
infra/        Terraform — nothing exists outside this
eval/         accuracy harness and fixtures
docs/         architecture, agents, data model, security
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

Setup, required secrets and the one-time actions that cannot be automated:
[docs/deployment.md](docs/deployment.md)

---

## Accuracy

Trimbin publishes its own error rate at `/accuracy` — live, no account needed.

The override rate is deliberately reported in two halves. Disagreement on a *flagged*
call is the system working as designed; those were handed to a person on purpose.
Disagreement on a *confident* call is a real error. A single combined number would
flatter us and tell nobody anything.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
