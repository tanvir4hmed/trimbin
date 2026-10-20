"""Credential-free configuration preflight; never claims network/model health."""

import argparse
import json

from trimbin_agents.config import Settings

REQUIRED = {
    "api": ("operational_store", "evidence_writer", "sessions"),
    "worker": ("operational_store", "evidence_writer"),
    "retrieval": ("evidence_reader",),
    "inference": ("reasoning",),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=REQUIRED, default="api")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)
    report = settings.capabilities()
    print(json.dumps({"profile": settings.profile, "capabilities": report}, indent=2))
    return int(any(report[name]["status"] == "unavailable" for name in REQUIRED[args.service]))


if __name__ == "__main__":
    raise SystemExit(main())
