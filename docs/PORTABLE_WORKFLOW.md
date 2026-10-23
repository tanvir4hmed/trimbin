# Reproducible Trimbin package

There is one application package: [production Compose](../deploy/production/compose.yaml), [API image](../deploy/production/api.Dockerfile) and [frontend image](../deploy/production/web.Dockerfile). The former portable overlay was archived outside Git. `app.portable` imports the same canonical application for compatibility and provides no second workflow.

Build both images from the repository root. Production uses immutable Git SHA image tags resolved to digests. `tools/package_portable.py` packages an exact Git commit with a checksum manifest and filters out secrets, original footage and local archives. Packaging is not runtime or quality acceptance.

Moving to studio hardware requires compatible Linux/container runtime, CPU/RAM/disk capacity, configured media mounts and private secrets. Token Factory remains an external dependency. Hosting open model weights locally is future work and is not paid for by Token Factory credit. Reproduce storage authorization, source hashes and frame/export tests after changing mounts or hardware. This deployment does not establish terabyte throughput or offline capability.
