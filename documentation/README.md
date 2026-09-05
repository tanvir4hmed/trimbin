# Trimbin — Documentation

An assistant editor that compares every take of a shot, says which part of each is
safe to use, and keeps the reason for every decision in an archive you can ask
questions of years later.

**Live:** [trimbin.qlitch.com](https://trimbin.qlitch.com)

---

## Contents

| Document | What it covers |
|---|---|
| [Product](01-product.md) | What Trimbin does, who it is for, and a worked example from footage to decision |
| [Architecture](02-architecture.md) | How the system is put together and why each part is shaped that way |
| [Agents](03-agents.md) | The five agents, their charters, and what each may and may not do |
| [The archive](04-archive.md) | The ClickHouse data model, and why an edit decision is a fact rather than a field |
| [Infrastructure](05-infrastructure.md) | Every deployed service, how a change reaches production, and what happens when one fails |

## Diagrams

| Diagram | |
|---|---|
| [Infrastructure](diagrams/infrastructure.svg) | Every deployed service and how they connect |
| [Agent design and flow](diagrams/agents.svg) | The five agents and the path a take takes through them |
| [The archive](diagrams/clickhouse.svg) | Event tables, the read models over them, and how current state is derived |
| [Processing workflow](diagrams/workflow.svg) | Footage in, decision out, across browser, API, worker and editor |

---

## The idea in one paragraph

A feature shoot produces thirty to a hundred hours of footage. Two hours reach the
screen. The other ninety-eight are kept but not usable — not because the footage is
bad, but because the reasoning behind every choice lived in one editor's head and
left when they did. Trimbin does the assistant editor's daily job: logging,
grouping, triage. The notes are a by-product of the work rather than extra work,
and the result is an archive where "why was take 4 chosen over take 6" is a
sentence typed into a box.

## The principle everything rests on

**Every measurement is relative to its group, never absolute.**

Seven dark takes of a night scene are a night scene, not seven faults. Six
locked-off takes and one handheld is probably one accident. An absolute threshold
cannot tell those apart; a ratio against the setup's own median can.

This is enforced everywhere, and it is what makes an honest answer possible: run
against twelve professionally shot takes, measurement finds nothing wrong with any
of them — because there is nothing wrong with any of them.

## What it will not do

It never decides where a cut goes, and it never judges acting. Those are story
questions and they belong to a person. Nothing is auto-rejected: a technically
worse take is often the right take.
