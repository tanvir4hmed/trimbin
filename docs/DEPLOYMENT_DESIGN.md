# Deployment and recovery

The selected host is AWS us-east-1, m7i-flex.xlarge (4 vCPU, 16 GiB), with encrypted 40 GiB root and 200 GiB gp3 persistent data volume. Terraform under `infra/aws` owns networking, compute, disk, ECR, SSM, release/backup buckets, IAM/OIDC and the imported existing CloudFront distribution. Its pre-existing certificate, WAF and root-domain DNS are retained external prerequisites. The CNAME for trimbin.qleam.com already targets the reused distribution; no second domain is required.

Bootstrap state bucket with `infra/aws/bootstrap`; initialize application state with:

```powershell
terraform '-chdir=infra/aws' init '-backend-config=bucket=trimbin-tfstate-552794253321' '-backend-config=key=trimbin/terraform.tfstate' '-backend-config=region=us-east-1' '-backend-config=use_lockfile=true'
terraform '-chdir=infra/aws' plan
```

Existing state is encrypted/versioned in S3. Do not reinitialize an empty state and recreate resources. Do not destroy the protected data volume or buckets. Existing certificate/WAF IDs are intentionally retained in configuration to avoid deleting unrelated or plan-required resources.

The sole production package is [Compose](../deploy/production/compose.yaml). `configure.py` reads `/trimbin/runtime` from encrypted SSM and writes private configuration. No credential values are baked into images, committed, or exposed to frontend JavaScript. The first owner credential is in the operator's ignored `.secrets/aws/access.json`.

Every main push invokes `.github/workflows/deploy-trimbin.yml`: required CI, API/frontend image builds, ECR publication under exact Git SHA, source checksum, SSM rollout and readiness verification. The host pulls exact digests, migrates PostgreSQL/ClickHouse, starts all workers and gateway, verifies local readiness/frontend and updates `/opt/trimbin/current`. Failed readiness restores previous image references when available; schema rollback is not automatic. Add only backward-compatible migrations while older images may be needed. The final push is not polled by the coding agent; the workflow reports its own result.

Database ports stay on the internal container network. SSM administration replaces SSH keys. Original files and databases live under `/srv/trimbin`; root disk replacement must reattach the protected data volume rather than format it. Bootstrap formats only an empty newly attached device and mounts by UUID.

Daily `trimbin-backup.timer` stops writers, dumps PostgreSQL and takes native ClickHouse backup, then copies backups and originals/exports to versioned private S3. A backup should include an operator inventory of any externally mounted library roots; those cannot be assumed present on a replacement host. Credentials remain in SSM and are not included in media backups. Proxy caches can be regenerated.

Recovery: provision a replacement compatible host, attach a restored volume snapshot or restore an immutable S3 backup into empty database containers, restore PostgreSQL with pg_restore, restore ClickHouse with its native RESTORE command, restore originals before starting workers, reapply only unapplied migrations, verify source hashes, membership, revisions and pending jobs, then point the same CloudFront origin at it. Never restore over the only good copy. Restore rehearsals must use a separate database/path.

AWS hosting, EBS, public IPv4, S3 and transfer incur charges separately from partner credits. This is a single-host installation with bounded concurrent workers, no GPU and no autoscaling. Exact account prices vary; assess current AWS pricing before increasing disk/instance size. Persistent data and versioned backups continue costing money when containers stop.
