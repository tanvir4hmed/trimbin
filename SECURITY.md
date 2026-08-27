# Security

Trimbin holds unreleased footage — among the most sensitive material a production
owns — and points a language model at it. Both facts shape everything below.

---

## Prompt injection is the defining threat

A clapperboard is untrusted input a camera was pointed at. So is a costume, a prop,
a whiteboard in the background of a location, and anything an actor holds up. If
someone writes *"ignore previous instructions"* on a slate, the Slate Agent will
read it.

Four defences, none of them relying on the model behaving well:

**Text found in footage is data, never instruction.** Stated explicitly in every
prompt that touches video, and reinforced by the shape of the task — the agent is
asked to extract fields, not to decide what to do.

**Every output is schema-validated.** An agent that has been talked into something
else cannot express it. There is no free-text channel between agents where an
injected instruction could travel.

**The MCP server is read-only.** This is the important one. A language model with
write access to a production database is one successful injection away from a
destructive query. `CLICKHOUSE_ALLOW_WRITE_ACCESS` stays `false`; writes go
through a typed service where a schema decides what is legal.

**Agents cannot reach anything they do not need.** Each has its own service
account with its own narrow grants.

---

## Credentials

No long-lived credential exists anywhere in this project.

CI authenticates through Workload Identity Federation: GitHub proves which
repository and which ref is running, Google issues a short-lived token. There is no
service account key to leak, rotate, or discover in a git history later. The
federated identity is bound to one repository by an attribute condition — without
it, any repository on GitHub could assume the deployer.

Runtime credentials live in Secret Manager and are injected at start. None appear
in code, in environment files, or in Terraform state.

`.gitignore` blocks `.env`, `*.tfvars`, and anything matching a key or credential
filename. CI runs a secret scan over full history on every pull request, because
the dangerous commit is the one nobody was looking at.

---

## Access

| Who | Can |
|---|---|
| Anonymous visitor | Read the demo project. Play, browse, search, read accuracy |
| Sandbox visitor | Upload three short clips, rate-limited by IP, deleted after 24h |
| Member | Full read and write on projects they belong to |
| Owner | Also add members and supersede scenes |

Scope is enforced in the query, not in the prompt. An agent asked nicely to look at
another project cannot, because the caller's scope is a filter applied before the
model is involved.

---

## Media

Footage never passes through the API. Uploads go directly to Cloud Storage with
short-lived signed URLs; playback is served from CDN behind signed access. Buckets
enforce uniform access with public access prevention on.

Video is never sent to a model that was not asked for it, and nothing is used for
training. The dataset this project builds is measurements and decisions — numbers,
not footage — which is both the more useful half and the half that is ours to keep.

---

## Cost as a security property

An agent stuck in a loop is a denial-of-service attack on your own budget.

Retries are capped at two, then the item is flagged and the batch moves on. No
agent may call another in a cycle. Budget alerts fire at 50%, 80% and 100% and are
declared in Terraform rather than configured by hand. Sandbox uploads are capped by
count, duration and IP.

---

## Reporting

Open a GitHub issue for anything non-sensitive. For a vulnerability, use GitHub's
private security advisory rather than a public issue.
