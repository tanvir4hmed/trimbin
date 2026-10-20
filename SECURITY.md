# Security policy

This repository is undergoing a planned architecture update. The controls below are requirements for the new build; they do not certify that the existing runtime implements them.

- Keep provider keys, database passwords, session keys and deployment credentials in GitHub Actions Secrets and ignored local configuration. Public environment variables must never contain credentials.
- Original footage and the local reference archive must be excluded from Git, build contexts, container images and published artifacts.
- Deployment media ingest must restrict filesystem access to configured roots, expose only project-authorized assets, mount processed originals read-only and prevent path traversal or symlink escape. Upload staging is a separate authenticated writable area.
- Public demo media must be cleared for sharing. Private originals and proxies require authenticated media access; an unguessable URL is not authorization.
- Disclose browser-to-host uploads and data sent to inference, tracing or human-review services. The cloud submission is not offline. Any future offline edition needs its own no-network verification.
- Use separate application and read-only retrieval database identities. Background jobs must validate callers and enforce project scope independently of deployment-provider IAM.
- Validate source ranges and export requests; do not insert untrusted text into shell commands. Export must not overwrite originals.
- Record runtime and export provenance without secrets. Preserve work recovery, version conflicts and backups; cleanup must not delete source versions referenced by saved edits.

Report a suspected issue privately to the repository owner through GitHub's available private reporting channel. Do not include secret values or private footage in public issues.
