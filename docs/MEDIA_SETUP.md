# Media ingest and storage

One [production Compose package](../deploy/production/compose.yaml) supplies the API, all workers, PostgreSQL and ClickHouse. All new and retained editorial routes use filesystem originals and the same PostgreSQL project/membership/source identities.

Users can upload bounded, resumable 8 MiB chunks from the browser. Staging and originals reside under one `/media` mount so final publication is an atomic rename; separate bind mounts fail with EXDEV even on the same underlying disk. Completed originals are never overwritten. The media worker fingerprints the original, probes timing/codecs/color and creates separate proxy, sprite and audio derivatives. Publication transactionally queues editorial ingestion using that same source UUID. The older upload interface registers its completed original in this same registry.

The public URL is https://trimbin.qleam.com; media routes require project access. Controlled tickets and secure playback cookies permit browser seeking/HLS. Upload grants are signed, expiring and size-bounded, and new chunks check available space. Project deletion/visibility and membership use the shared authority. Original path traversal and arbitrary host paths are rejected.

Mounted libraries are operator-configured named roots with explicit project access. The current cloud installation uses uploads on encrypted EBS. Pointing a cloud browser at a local PC folder does not make that folder available to the server. A future studio deployment would need an actual shared/mounted SSD/NAS path; that installation is not demonstrated here.

Source relinking requires an owner and the same content hash. Originals remain separate from expendable derivatives. Analysis/export refuse changed or unavailable sources instead of substituting proxy footage. Workers use bounded scratch and thread settings. Large source size does not remove temporary-space, indexing-time or paid-inference limits, and the generated test does not prove terabyte throughput.

Run the API and workers through the single production package. Development database tools remain in [foundation setup](FOUNDATION_SETUP.md); they are isolated test facilities, not another production editor. Recovery and backups are documented in [deployment design](DEPLOYMENT_DESIGN.md).
