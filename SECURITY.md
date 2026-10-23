# Security policy and deployment boundary

Updated 23 October 2026. The canonical AWS deployment implements the controls described below; this is not a penetration-test or production-security certification. Exact test scope and remaining limits are in [cutover evidence](docs/AWS_CUTOVER.md).

- Provider keys, database/session credentials and owner passwords are encrypted in SSM and supplied through private per-service configuration. GitHub uses scoped OIDC for AWS deployment. Never commit credentials, state, original footage or the external reference archive.
- PostgreSQL membership authorizes project operations. Password sign-in issues a signed session and secure HttpOnly playback cookie; optional Google identity is separate from the application hosting stack. Expiring media capabilities are scoped and size-bounded where applicable.
- Media paths must resolve inside configured roots. Processing workers mount originals read-only; authenticated upload staging is writable and atomic promotion requires a common filesystem. Export rechecks source identities and never overwrites originals.
- PostgreSQL, ClickHouse and workers expose no public ports. ClickHouse writer and constrained SELECT-only reader are distinct; restored identities were tested for allowed reads and denied DDL. Application and query project filtering are still required.
- Public viewers use CloudFront HTTPS. The current edge-to-origin connection is HTTP restricted to AWS CloudFront origin ranges. Do not describe this as end-to-end TLS, an air gap, or isolation to this distribution alone. SSM replaces public SSH administration.
- Browser uploads and model frames/text cross network boundaries. Token Factory is external managed inference. Google Fonts is another browser request. Optional tracing/search/human-review partners are not active core integrations.
- Native/FCP7 output and rendered MP4 require project access, pinned revisions, validated source ranges and generated output paths. No untrusted text is interpolated into shell commands. Originals remain private unless explicitly cleared and shared.
- Quiesced daily backups retain databases and originals/exports in private versioned S3. Recovery requires protected credentials, source hashes and access checks. The single host is not highly available; backup/version retention must be monitored for both recovery and cost.

The pass endpoint uses an in-memory rate limit, not a distributed lockout. Frontend session storage and private-host administrator access remain trust boundaries. Broader security review, penetration testing and disaster recovery on a replacement host have not been certified.

Report suspected issues privately to the repository owner through an available GitHub private reporting channel. Never put secret values or private footage in public issues.
