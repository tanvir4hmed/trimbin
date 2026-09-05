# Verification

Everything on this page is checkable against the running system. Nothing is
rounded up, and nothing is asserted that a reader cannot confirm.

## ClickHouse at runtime, through the official MCP server

The ClickHouse track requires the database to be used at runtime via the official
`mcp-clickhouse` server. It is, and the deployment says so about itself:

```
GET https://trimbin.qlitch.com/api/public/mcp-evidence
```

```json
{
  "runtime": "official mcp-clickhouse over stdio",
  "identity": "dedicated ClickHouse read-only user",
  "project_scoped": true,
  "direct_fallback": false,
  "configured": true,
  "result_contract": "exact clip_id plus playable start_s/end_s"
}
```

`direct_fallback: false` is the field that matters. Every search an editor runs
goes through the MCP server; there is no path that quietly bypasses it when the
server is slow or unavailable. If MCP cannot serve the query, the search fails and
says so.

### How the boundary is actually enforced

Four layers, listed in the order they stop something — and two of them are
boundaries while two are merely courtesies. The code says which is which, because
a comment that overstates a defence is worse than no comment.

| | Layer | Boundary? |
|---|---|---|
| 1 | The MCP server refuses anything but `SELECT`, whatever statement arrives | **Yes** |
| 2 | The grant limits which objects a `SELECT` can even name | **Yes** |
| 3 | The project scope filter is appended by the application, never asked for in a prompt | No — a courtesy |
| 4 | A keyword pattern rejects the obvious before it costs a round trip | No — a courtesy |

`trimbin_reader` holds `SELECT` on named objects only — 34 of them at the time of
writing, each granted explicitly by the migration that creates it — and nothing
else, under a profile with `readonly = 1 CONST`. The `CONST` matters: it cannot be turned off
mid-session, which is the difference between a setting and a guarantee.

The model composes no SQL. It fills in a fixed shape, and the statement executes
through MCP as a user that cannot write. Every deploy verifies that this user can
read and — checked explicitly — **cannot** write, because a grant that looks
correct and is not would undo the only boundary that matters here.

## The published accuracy figure

```
GET https://trimbin.qlitch.com/api/public/accuracy
```

The figure is the share of confident decisions no editor later replaced, counted
from the event log. Shots the system flagged for review are excluded — those were
handed to a person deliberately, and counting them would flatter the number.

It carries its own definition and its own caveat in the response body, so the
figure cannot be quoted without them.

It is not self-reported and not calculated by the component being measured: an
override is an event written by the interface when an editor disagrees, and the
figure is a query over those events.

## Where there is no data

The interface shows zero, or nothing at all. It never displays a plausible number
it cannot source.

Synthetic rows used for testing are excluded at the schema level by the views the
application reads — `real_clips`, `real_decisions` — rather than by a filter in
application code that one query could forget. Test data cannot reach a figure
anybody is shown, public or private.

## What ships, and what checks it

A push to `main` is the only path to production. Six jobs run first, fifteen
checks between them, and a failure in any of them blocks the deploy:

| Job | Checks |
|---|---|
| **api** | Lint, format, tests, and that the frontend's generated types still match the OpenAPI schema |
| **agents** | Lint, format, types, tests |
| **web** | The frontend rule tests, typecheck, and a full production build — a page can typecheck and still fail to prerender |
| **migrations** | Every migration applied to a fresh ClickHouse container from empty, then verified |
| **terraform** | Format and validate |
| **secrets** | History scanned |

Migrations are the important one. Applying them to a throwaway server from nothing
proves the schema builds from empty rather than merely surviving on top of what
production already has — and it means a statement ClickHouse will not parse fails
on the branch instead of between a `DROP` and a `CREATE` in production.

The frontend tests are worth naming too. They exercise the pure rules — slug
resolution, the ingest resume fingerprint, which shot statuses still want a
person — by calling them with real inputs rather than checking that a phrase
appears in a source file.

## What the checks do not cover

Stated plainly by the release script itself, every time it runs:

- **A browser pass over every route, including a shot URL.** A green build says
  nothing about a runtime error in a React hook — neither the typechecker nor the
  production build can see one.
- **A public project a signed-out visitor can actually open.** That is data, not
  code, and no test can assert it into existence.
- **Migrations applied against production.** Only a deploy does that.

A check that implies more than it verified is worse than no check.

## Reproducing any of this

```bash
tools/release-check.sh          # eleven gates locally; prints what it cannot check
cd api && pytest                # the API and regression suites
cd web && npx vitest run        # the frontend rules
```

The live deployment answers `GET /api/public/health`, `/api/public/accuracy` and
`/api/public/mcp-evidence` without authentication, so every claim above can be
checked without an account.
