# Trimbin documentation

Trimbin is an editorial preparation and decision workspace. It organizes footage, records timecoded evidence, supports human review and multi-take portion selections, and previews those selections across a production.

[Live application](https://trimbin.qlitch.com)

| Document | Contents |
|---|---|
| [Product](01-product.md) | Workflow, terminology and editorial boundaries |
| [Architecture](02-architecture.md) | Services, storage responsibilities and consistency |
| [Agents](03-agents.md) | Observation, comparison and retrieval |
| [Archive](04-archive.md) | ClickHouse evidence, placement and analytical views |
| [Infrastructure](05-infrastructure.md) | Deployment, media delivery and operations |
| [Verification](06-verification.md) | Measurement definitions and release checks |

The workflow is **Footage → Scenes & shots → Shot Review → Film Preview**. Search, activity and review measurements support that work. A technical observation is evidence to verify, not an objective judgement of acting or storytelling.

Original recordings, confirmed shot selections and saved film sequences are separate resources. Changing a sequence does not move footage or overwrite the team's shot selections.
