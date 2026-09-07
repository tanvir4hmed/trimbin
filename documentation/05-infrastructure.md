# Infrastructure

The repository declares deployment infrastructure in Terraform and release workflows in GitHub Actions.

## Runtime

- Cloud Run web, API and media-worker services.
- Separate web image; shared API/worker image with distinct entrypoints.
- Cloud Storage originals, proxies and artifacts.
- Pub/Sub ingest/analysis work with retry/dead-letter infrastructure.
- Firestore operational documents.
- ClickHouse Cloud analytical storage and a restricted MCP reader.
- Secret Manager configuration; Google Cloud authentication through deployed identities.

The load balancer serves the application and media routes. Proxies are delivered independently of application playback commands.

## Release

The main-branch workflow, also available by workflow dispatch, runs checks before deployment, applies infrastructure and migrations, builds commit-tagged images and updates services. Workload Identity Federation supplies short-lived deployment credentials rather than a checked-in service-account key.

Migrations run in order and verify expected objects and reader restrictions. CI also applies migrations to a fresh ClickHouse instance. Commit-tagged images support a specific rollback target.

## Operations

Processing failures must remain visible in job/item state. Invalid media and infrastructure failures are different outcomes. Duplicate footage is identified by content hash and retained for review; it is not silently discarded.

Server work can continue independently of the browser. Browser transfer cannot survive every closure without reacquiring local file access. Source transitions can buffer even when no database call is required.

Deployment concurrency reduces overlapping applies; it does not make interruption impossible. Service-level permissions, retention configuration, cost limits and recovery behaviour must be reviewed against the deployment rather than inferred from a successful build.
