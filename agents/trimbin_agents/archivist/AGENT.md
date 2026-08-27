# Archivist Agent

## Purpose

Turn a question written in ordinary language into a query over the archive, and
answer it — or say plainly that nothing matches.

This is the only agent a person talks to directly, and the only one on a
user-facing latency budget.

## Contract

| | |
|---|---|
| **Input** | `contracts.query.QueryRequest` — a sentence, plus project scope |
| **Output** | `contracts.query.QueryResult` — matches with context, or an honest empty |
| **Reads** | `clips`, `decisions` via `mcp-clickhouse` |
| **Writes** | Nothing. Ever |
| **Model** | `gemini-3.6-flash` · structured output · no video input |

## Why no video

By the time a question is asked, every clip has already been watched, measured and
described. Search runs over what was recorded, not over the footage — which is why
an answer takes a second instead of a minute.

## Hybrid retrieval

A question like *"alternate shots for the rainy window scene under 4 seconds"*
decomposes into three kinds of constraint, and ClickHouse serves all three:

| Part of the question | Mechanism |
|---|---|
| "rainy window scene" | Vector similarity over clip embeddings |
| "alternate shots" | Structured filter on `decisions.outcome` |
| "under 4 seconds" | Structured filter on `duration_s` |

No separate vector database, no separate search engine. One store, one query.

## MUST NOT

- **Never invent a result.** When nothing matches, say so and offer to widen the
  constraint. A plausible wrong answer here is worse than no answer, because the
  person will act on it.
- **Never have write access.** The MCP server runs read-only. A language model
  with write access to a production database is one prompt injection away from a
  destructive query, and question text is untrusted input by definition.
- **Never answer outside the caller's scope.** A visitor sees the demo project.
  A member sees their projects. This is enforced in the query, not the prompt.
- **Never return a bare list.** Every match carries why it is a match — which
  shot, which decision, what the reason was.

## When nothing matches

Three responses, in order of preference:

1. **Near miss on a numeric constraint** — "nothing under 4 seconds; the closest
   are 5.1s and 5.4s." Offer them.
2. **Nothing in this project** — say so, and offer to look wider if the caller
   has access to more.
3. **Nothing anywhere** — say that, and stop. No consolation results.

## Failure modes

| Case | Behaviour |
|---|---|
| Question is ambiguous | Ask one clarifying question rather than guessing |
| Generated query is invalid | Retry once, then report a failure to search — never a false empty |
| MCP server unreachable | Report the outage plainly. Do not fall back to a direct connection that bypasses the read-only guarantee |
| Query exceeds timeout | Return partial results, labelled as partial |

## Cost profile

One short call to plan the query, one to phrase the answer. No video tokens. This
agent is cheap enough to be used freely, which is the point — an archive nobody
queries is a filing cabinet.
