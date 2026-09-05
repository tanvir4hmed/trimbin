# Architecture

![Infrastructure](diagrams/infrastructure.svg)

## Shape

Three deployed services, one image.

| Service | What it is | Why it is separate |
|---|---|---|
| `web` | Next.js App Router | Renders the interface. Scales to zero between sessions. |
| `api` | FastAPI | Owns authorisation, curation and search. Never runs a mutation inline. |
| `worker` | Same image, different entrypoint | ffmpeg and the agents. Minutes of work per clip, which must not block a request. |

The worker is the same container as the API with its command overridden. One build,
one set of dependencies, one thing to keep in step — and no second Dockerfile that
drifts from the first.

## Three stores, three jobs

Splitting state across three systems is a cost, and it is paid deliberately.

**ClickHouse — what happened.** Every decision, finding, placement, segment and
correction, appended and never updated. Reads are analytical: *every rejected take
across four productions with its reason* is a column scan over millions of rows,
which is the query this database is shaped for.

**Firestore — what is true right now.** Projects, membership, jobs, revisions.
Small mutable documents read by key, with optimistic concurrency on a `rev` field.
Putting these in ClickHouse would mean a mutation on every rename.

**Cloud Storage — the bytes.** Masters, proxies, deliverables. Neither database
holds media.

The rule that keeps this honest: **operational state is mutable, history is not.**
A project can be renamed. A decision cannot be un-made — only superseded by
another decision, which is itself a row.

## The paths that matter

### Footage never passes through the application

The browser asks the API for upload tickets and sends bytes directly to storage by
resumable signed URL. A 4K master is tens of gigabytes; routing it through a
request handler would occupy a container for the length of the upload and cap the
system at roughly one shoot at a time.

Storage takes the bytes. The API takes the facts.

### Nothing slow happens inside a request

Ingest publishes one message per clip and returns. The worker downloads, measures,
reads the slate, encodes a proxy and hands the clip to verification — reporting
each stage as it starts, because a progress bar that does not move is
indistinguishable from a system that has stopped.

At-least-once delivery is safe because repeated work is recognised rather than
repeated. Ingest fingerprints the bytes, so the same footage arriving twice under
two names is identified as a duplicate instead of ingested twice. Analysis runs
carry a run key and a completed run is not re-run. A clip that cannot be processed
goes to a dead-letter topic rather than disappearing, and stays visible as
unresolved rather than silently absent from the count.

### No mutation is ever in an interactive path

`ALTER TABLE … UPDATE` in ClickHouse rewrites whole parts, runs asynchronously and
is capped in flight. One in a request handler is a screen that hangs under load.
There are none — and a test asserts that no service module contains one, because
this is the kind of rule that erodes quietly.

## One rule, in one place

Three defects in production QA had the same cause: a rule written down more than
once, and the copies disagreeing.

- Two settlement paths, so a clip could be placed by one and not the other.
- Three implementations of *does this shot still need a person*, which gave three
  different answers about the same shot — the tree saying everything was decided
  beside a queue that listed nothing and a cockpit asking for a decision.
- A hardcoded project id deciding read access in five different routes.

Each is now a single function. `services/settlement.py` is the only way a clip is
placed. `services/assessment.py` decides shot status; the frontend's `lib/shot.ts`
does nothing but name which of those statuses mean a person is wanted, and a test
pins it exhaustively so a new status cannot silently fall through to "nobody is
needed". Access is `projects.open_to_readers(project)` — a rule, not an id.

## Types across the boundary

The frontend's types are generated from the API's OpenAPI schema. A release gate
regenerates them and fails if the checked-in file differs, so an endpoint whose
shape changed cannot ship against a frontend that still believes the old one. It
caught a missing field the first time it ran.

## What is tested, and how

`tools/release-check.sh` is one command for eleven gates: API tests, agent tests,
lint, formatting, generated-schema freshness, the frontend test suite, typecheck,
production build, Terraform format and validate, and migration numbering.

CI runs the same eleven and adds two that need infrastructure a laptop does not
have: a secret scan, and every migration applied to a throwaway ClickHouse
container from empty.

Two things about it are deliberate.

**It prints what it cannot check.** A browser pass over a shot URL, a public
project a signed-out visitor can actually open, and migrations applied against
production are named as *not covered here* — because a green check that implies
more than it verified is worse than no check.

**Frontend rules are run, not read.** An earlier version of the regression suite
asserted on source text: it read `.tsx` files from Python and checked a phrase was
present. That passes whenever the phrase exists and fails whenever somebody renames
a variable. Those rules are pure functions, so they are now called with real
inputs. Writing them that way immediately found a bug greps could not see — the
control that chose a take in the cockpit was a click handler on the element
wrapping the video, so pressing play on one take silently reassigned the choice.

## Failure, and what it looks like

| Failure | What happens |
|---|---|
| A clip breaks ffmpeg | Dead-letter topic. The clip stays visible as unresolved footage. |
| A model call fails | The rows are still the answer. Search returns them with a plain sentence instead of a written one. |
| Search is unavailable | Said out loud. A failed search dressed as an empty one tells somebody their archive is empty, which is a different and wrong thing. |
| A migration will not parse | The branch fails. It cannot reach production. |
| A deploy is bad | Every image is tagged with its commit, so a rollback targets a specific build rather than a moving tag. |

## Security posture

Authentication to Google is Workload Identity Federation: GitHub proves which
repository and ref is running, Google issues a short-lived token. **No service
account key exists** to leak, rotate, or find in a git history two years from now.

Search runs as a separate read-only ClickHouse user with its own resource limits.
The deploy verifies that this user can read and — explicitly — that it *cannot*
write, because a grant that looks right and is not would undo the one boundary
that matters when a model is involved in composing a query.

Secrets live in Secret Manager with per-service IAM. A secret scan runs on every
push.
