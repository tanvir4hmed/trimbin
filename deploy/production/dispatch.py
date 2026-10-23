"""Construct a secret-free, exact-image SSM release command."""

import json
import os
import re
import subprocess

revision = os.environ["GITHUB_SHA"]
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise ValueError("A complete Git revision is required")
bucket = os.environ["RELEASE_BUCKET"]
registry = os.environ["ECR_REGISTRY"]
images = {}
for component in ("api", "web"):
    digest = subprocess.check_output(
        [
            "aws",
            "ecr",
            "describe-images",
            "--repository-name",
            "trimbin-" + component,
            "--image-ids",
            "imageTag=" + revision,
            "--query",
            "imageDetails[0].imageDigest",
            "--output",
            "text",
        ],
        text=True,
    ).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Release image digest missing")
    images[component] = f"{registry}/trimbin-{component}@{digest}"
path = "/opt/trimbin/releases/" + revision
commands = [
    "set -eu",
    f"mkdir -p {path}",
    f"cd {path}",
    f"aws s3 cp s3://{bucket}/{revision}/source.tgz source.tgz --only-show-errors",
    f"aws s3 cp s3://{bucket}/{revision}/source.sha256 source.sha256 --only-show-errors",
    "sha256sum -c source.sha256",
    "tar -xzf source.tgz",
    f"export TRIMBIN_APP_IMAGE={images['api']}",
    f"export TRIMBIN_WEB_IMAGE={images['web']}",
    "bash deploy/production/release.sh",
]
print(
    json.dumps(
        {
            "DocumentName": "AWS-RunShellScript",
            "InstanceIds": [os.environ["TRIMBIN_INSTANCE"]],
            "TimeoutSeconds": 1800,
            "Parameters": {"commands": commands, "executionTimeout": ["1800"]},
            "Comment": "trimbin release " + revision,
        }
    )
)
