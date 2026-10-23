# Trimbin

Film footage review, grounded AI evidence, human selections, frame-based timelines and original-fed export.

Public application: https://trimbin.qleam.com. The canonical application runs on AWS CPU compute with PostgreSQL, self-hosted ClickHouse and encrypted filesystem storage. NVIDIA Nemotron vision/reasoning and Qwen embeddings run through Nebius Token Factory. CPU Whisper provides speech transcription. Token Factory credit does not pay for AWS infrastructure.

Large originals remain on deployment storage. Browser uploads and outbound model frames/text still cross the internet in this cloud installation. Moving the package beside studio SSD/NAS is a future installation option, not a claim that this cloud release operates offline or has demonstrated terabyte throughput.

One frontend and API serve projects, scenes/shots/takes, review, search, media, evidence, timelines and exports. Retained editorial services now use PostgreSQL documents and durable jobs; media identities bridge into the same source registry. `app.portable` is only a compatibility import of `app.main`. There is no separate production editor.

- [Deployment and current evidence](docs/AWS_CUTOVER.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Deployment and recovery](docs/DEPLOYMENT_DESIGN.md)
- [Build phases](docs/BUILD_PLAN.md)
- [Status and limitations](docs/PHASE_STATUS.md)
- [Product direction](docs/PRODUCT_DIRECTION.md)
- [Competition requirements](docs/REQUIREMENTS.md)
- [Quality strategy](docs/QUALITY_STRATEGY.md)
- [Media workflow](docs/MEDIA_SETUP.md)
- [Evidence review](docs/EVIDENCE_SETUP.md)
- [Timelines](docs/TIMELINE_SETUP.md)
- [Editable exports](docs/EDITABLE_EXPORT_SETUP.md)
- [Rendered video](docs/RENDER_SETUP.md)

The old source tag is preserved. Historical footage/state was not recovered from the deleting old cloud project; the new installation creates a real owner workspace, not fabricated production history. Runtime smoke tests do not prove better model quality or Premiere compatibility. Those acceptance gates remain explicit.

## License

Source: [Apache 2.0](LICENSE). Models, codecs, datasets and footage have their own licenses. Preserve notices and asset rights.
