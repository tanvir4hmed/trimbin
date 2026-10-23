"""Rebuild the repository's editable SVG architecture diagrams (stdlib only)."""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
BLUE, ORANGE, GREEN, PURPLE = "#2563eb", "#c2410c", "#15803d", "#7c3aed"
INK, MUTED = "#14243b", "#52647a"
ICONS = {
    "browser": '<rect x="3" y="5" width="30" height="25" rx="3"/><path d="M3 12h30M8 8h1m4 0h1"/>',
    "cloud": '<path d="M9 28a7 7 0 0 1-1-14 10 10 0 0 1 19-2 8 8 0 0 1 1 16Z"/>',
    "shield": '<path d="m18 3 13 5v10c0 8-13 15-13 15S5 26 5 18V8Z"/><path d="m11 17 5 5 10-11"/>',
    "compute": '<rect x="8" y="8" width="20" height="20" rx="3"/><path d="M13 2v6m10-6v6M13 28v6m10-6v6M2 13h6m-6 10h6m20-10h6m-6 10h6"/>',
    "database": '<ellipse cx="18" cy="7" rx="13" ry="5"/><path d="M5 7v22c0 7 26 7 26 0V7M5 18c0 7 26 7 26 0"/>',
    "disk": '<rect x="4" y="5" width="28" height="27" rx="4"/><path d="M4 23h28m-22 5h2m5 0h2"/><circle cx="18" cy="14" r="5"/>',
    "code": '<path d="m12 8-9 10 9 10m12-20 9 10-9 10M21 4l-6 28"/>',
    "ai": '<rect x="8" y="7" width="22" height="24" rx="6"/><path d="M19 2v5M3 15h5m-5 9h5m22-9h4m-4 9h4M13 24h12"/><circle cx="14" cy="16" r="1"/><circle cx="24" cy="16" r="1"/>',
    "film": '<rect x="4" y="4" width="28" height="28" rx="3"/><path d="M10 4v28m16-28v28M4 12h6m-6 12h6m16-12h6m-6 12h6m-22-6h16"/>',
    "queue": '<rect x="4" y="4" width="23" height="8" rx="2"/><rect x="8" y="15" width="23" height="8" rx="2"/><path d="M12 28h20m-4-4 4 4-4 4"/>',
    "check": '<circle cx="18" cy="18" r="15"/><path d="m9 18 6 6L28 11"/>',
    "key": '<circle cx="11" cy="12" r="8"/><path d="m17 18 15 14m-9-8 5-5m-1 9 5-5"/>',
    "human": '<circle cx="18" cy="10" r="7"/><path d="M5 33v-4a13 13 0 0 1 26 0v4"/>',
    "export": '<path d="M15 5H5v27h26V22M18 3h15v15M33 3 16 20"/>',
}


class Diagram:
    def __init__(self, title, subtitle, height=1080):
        self.height = height
        symbols = "".join(
            f'<symbol id="{k}" viewBox="0 0 36 36">{v}</symbol>'
            for k, v in ICONS.items()
        )
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img">',
            f"<title>{escape(title)}</title><desc>{escape(subtitle)}</desc>",
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 10 5 0 10Z" fill="#62758c"/></marker>',
            symbols + "</defs>",
            '<rect width="1600" height="100%" fill="#f3f6fb"/>',
            '<rect width="1600" height="116" fill="#14243b"/>',
        ]
        self.text(50, 49, title, 32, "#ffffff", bold=True)
        self.text(50, 83, subtitle, 17, "#c8d6e8")

    def text(self, x, y, text, size=17, color=INK, bold=False):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="Arial,DejaVu Sans,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(text)}</text>'
        )

    def region(self, x, y, w, h, title):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#e8eef8" stroke="#b9c8dc" stroke-width="2" stroke-dasharray="8 6"/>'
        )
        self.text(x + 20, y + 30, title, 17, MUTED, True)

    def edge(self, points, label="", lx=0, ly=0, dashed=False):
        d = "M" + " L".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="#62758c" stroke-width="2.5" stroke-linejoin="round" marker-end="url(#arrow)"{dash}/>'
        )
        if label:
            width = len(label) * 8.6 + 16
            self.parts.append(
                f'<rect x="{lx - 8}" y="{ly - 18}" width="{width}" height="25" rx="5" fill="#f3f6fb"/>'
            )
            self.text(lx, ly, label, 15, MUTED)

    def node(self, x, y, w, h, title, lines, icon="compute", color=BLUE, tag=""):
        self.parts.append(
            f'<rect x="{x}" y="{y + 4}" width="{w}" height="{h}" rx="14" fill="#dbe3ef"/>'
        )
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="white" stroke="#cbd6e5"/>'
        )
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{color}"/>'
        )
        self.parts.append(
            f'<use href="#{icon}" x="{x + 17}" y="{y + 18}" width="34" height="34" fill="none" stroke="{color}" stroke-width="2"/>'
        )
        self.text(x + 65, y + 38, title, 21, INK, True)
        for i, line in enumerate(lines):
            self.text(x + 20, y + 69 + i * 23, line, 16, MUTED)
        if tag:
            self.text(x + 20, y + h - 14, tag, 13, color, True)

    def footer(self, lines):
        y = self.height - 68
        self.parts.append(
            f'<rect x="40" y="{y - 22}" width="1520" height="72" rx="12" fill="#e3eaf4"/>'
        )
        for i, line in enumerate(lines):
            self.text(60, y + i * 25, line, 16, MUTED)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{name}.svg").write_text(
            "\n".join(self.parts) + "\n</svg>\n", encoding="utf-8"
        )


def system():
    d = Diagram(
        "TRIMBIN / System architecture",
        "Current AWS cloud PoC • one application • human-approved editing • 23 October 2026",
    )
    d.edge([(360, 225), (450, 225)], "HTTPS", 371, 207)
    d.edge([(770, 225), (840, 225)], "HTTP", 778, 207)
    d.edge([(1160, 225), (1230, 225)])
    d.edge([(1000, 280), (1000, 360)], "/api", 1012, 326)
    d.edge([(840, 420), (770, 420)])
    d.edge([(1160, 420), (1230, 420)])
    d.edge([(610, 480), (610, 600)], "durable jobs / outbox", 625, 544)
    d.edge([(1160, 665), (1230, 665)])
    d.edge([(1160, 625), (1195, 625), (1195, 510), (1390, 510), (1390, 480)])
    d.edge(
        [(620, 730), (620, 780), (415, 780), (415, 840)],
        "sampled frames / text",
        415,
        771,
        True,
    )
    d.edge([(1000, 730), (1000, 840)], "source audio", 1014, 790)
    d.node(
        60,
        170,
        300,
        110,
        "Editor browser",
        ["Upload • review • timeline", "Preview • saved exports"],
        "browser",
    )
    d.node(
        450,
        170,
        320,
        110,
        "CloudFront + WAF",
        ["trimbin.qleam.com", "TLS viewer connection"],
        "shield",
        ORANGE,
    )
    d.node(
        840,
        170,
        320,
        110,
        "Nginx gateway",
        ["Only public host port: 80", "Routes web and API"],
        "cloud",
        ORANGE,
    )
    d.node(
        1230,
        170,
        310,
        110,
        "Next.js frontend",
        ["One editorial application", "Private project workspace"],
        "browser",
    )
    d.node(
        60,
        360,
        300,
        370,
        "Declared boundary",
        [
            "Originals stay on host storage.",
            "Browser uploads cross internet.",
            "Token Factory is external.",
            "No local GPU is provisioned.",
            "No zero-upload/offline claim.",
            "One host; no HA or autoscale.",
            "Quality / NLE gates stay open.",
        ],
        "shield",
        PURPLE,
    )
    d.node(
        450,
        360,
        320,
        120,
        "PostgreSQL 17",
        ["Projects • membership • edits", "Revisions • receipts • queue"],
        "database",
    )
    d.node(
        840,
        360,
        320,
        120,
        "FastAPI / app.main",
        ["Auth • scoped APIs • media", "One canonical film state"],
        "code",
    )
    d.node(
        1230,
        360,
        310,
        120,
        "ClickHouse 26.8",
        ["Evidence / search / history", "Writer + constrained reader"],
        "database",
        PURPLE,
    )
    d.node(
        450,
        600,
        710,
        130,
        "Independent worker containers",
        [
            "Media • editorial • evidence • projection • vectors",
            "Editable export • original-fed render • leases + retries",
        ],
        "queue",
    )
    d.node(
        1230,
        600,
        310,
        130,
        "Encrypted EBS",
        ["Originals • derivatives", "Exports • DB data • cache"],
        "disk",
        ORANGE,
    )
    d.node(
        60,
        840,
        710,
        140,
        "Nebius Token Factory / managed inference",
        [
            "NVIDIA Nemotron vision + reasoning",
            "Qwen embeddings • HTTPS outbound • metered usage",
        ],
        "ai",
        GREEN,
        "EXTERNAL SERVICE — NOT SELF-HOSTED ON THE AWS INSTANCE",
    )
    d.node(
        840,
        840,
        700,
        140,
        "CPU Whisper / same AWS host",
        [
            "large-v3 • int8 • bounded 16 kHz windows + VAD",
            "Persistent model cache • no separate speech API",
        ],
        "ai",
        PURPLE,
        "LOCAL PROCESSING ON THE DEPLOYMENT HOST",
    )
    d.footer(
        [
            "Arrows show principal calls/data paths; replies are omitted. Icons are schematic service glyphs, not vendor certification.",
            "Original-fed exports preserve source files; generated-fixture success does not prove general movie quality or Premiere acceptance.",
        ]
    )
    d.save("system-overview")


def infrastructure():
    d = Diagram(
        "TRIMBIN / AWS infrastructure",
        "Terraform-owned runtime in us-east-1 • main-push release • encrypted persistent data",
        1180,
    )
    d.region(
        450,
        365,
        1090,
        620,
        "EC2 / trimbin • m7i-flex.xlarge • 4 vCPU / 16 GiB • no GPU",
    )
    d.edge([(360, 230), (450, 230)], "OIDC", 371, 211)
    d.edge([(770, 230), (840, 230)])
    d.edge(
        [(610, 175), (610, 145), (1385, 145), (1385, 175)],
        "signed role permits release publication",
        860,
        140,
    )
    d.edge([(1000, 305), (1000, 350), (1000, 425)], "pull exact digest", 1015, 344)
    d.edge([(1540, 230), (1575, 230), (1575, 885), (1510, 885)], "", dashed=True)
    d.edge([(380, 480), (490, 480)], "HTTP :80", 392, 464)
    d.edge([(790, 480), (850, 480)])
    d.edge([(640, 425), (640, 405), (1350, 405), (1350, 425)])
    d.edge([(1000, 555), (1000, 605), (640, 605), (640, 650)], "state + jobs", 660, 598)
    d.edge([(1000, 555), (1000, 650)])
    d.edge(
        [(1150, 510), (1180, 510), (1180, 620), (1350, 620), (1350, 650)],
        "source files",
        1200,
        612,
    )
    d.edge([(640, 780), (640, 835)])
    d.edge([(1000, 780), (1000, 835)])
    d.edge([(1150, 890), (1180, 890), (1180, 715), (1210, 715)])
    d.edge(
        [(820, 940), (820, 1020), (220, 1020), (220, 830)],
        "daily stopped-writer database + media backup",
        265,
        1012,
    )
    d.node(
        60,
        175,
        300,
        130,
        "GitHub main",
        ["Required CI / public source", "Build API + web images"],
        "code",
    )
    d.node(
        450,
        175,
        320,
        130,
        "Scoped IAM role",
        ["GitHub OIDC; main only", "No stored AWS access key"],
        "key",
        ORANGE,
    )
    d.node(
        840,
        175,
        320,
        130,
        "Amazon ECR",
        ["Immutable Git SHA tags", "Host pulls image digests"],
        "compute",
        ORANGE,
    )
    d.node(
        1230,
        175,
        310,
        130,
        "Private S3 release",
        ["Exact commit + checksum", "SSM dispatch to the host"],
        "disk",
        ORANGE,
    )
    d.node(
        60,
        425,
        320,
        130,
        "CloudFront / WAF",
        ["HTTPS browser connection", "Existing DNS + certificate"],
        "shield",
        ORANGE,
    )
    d.node(
        60,
        690,
        320,
        140,
        "Private S3 backup",
        [
            "PG dump + CH native backup",
            "Originals + export objects",
            "Versioned; separate state bucket",
        ],
        "disk",
        ORANGE,
    )
    d.node(
        490,
        425,
        300,
        130,
        "Nginx",
        ["Only host-published service", "Security group: CF ranges"],
        "cloud",
    )
    d.node(
        850,
        425,
        300,
        130,
        "FastAPI",
        ["Scoped APIs + auth", "Provider egress when needed"],
        "code",
    )
    d.node(
        1210,
        425,
        300,
        130,
        "Next.js",
        ["Web UI via Nginx", "Separate app container"],
        "browser",
    )
    d.node(
        490,
        650,
        300,
        130,
        "PostgreSQL",
        ["Internal Docker data network", "No public database port"],
        "database",
    )
    d.node(
        850,
        650,
        300,
        130,
        "ClickHouse",
        ["Internal Docker data network", "Read/write roles separated"],
        "database",
        PURPLE,
    )
    d.node(
        1210,
        650,
        300,
        130,
        "Encrypted disk",
        ["40 GiB root + 200 GiB data", "Persistent EBS /srv/trimbin"],
        "disk",
        ORANGE,
    )
    d.node(
        490,
        835,
        660,
        105,
        "Media / AI / index / export workers",
        ["Separate containers; PostgreSQL leases and fenced completion"],
        "queue",
    )
    d.node(
        1210,
        835,
        300,
        105,
        "SSM / runtime",
        ["Remote rollout + secret read", "No public SSH port"],
        "key",
        ORANGE,
    )
    d.footer(
        [
            "ECR + release S3 + SSM are authorized by the scoped deploy role. SSM encrypted runtime credentials stay outside Git.",
            "CloudFront-to-origin is HTTP, not end-to-end TLS. Single host; no load balancer, NAT gateway, managed DB or autoscaling.",
        ]
    )
    d.save("aws-infrastructure")


def ai():
    d = Diagram(
        "TRIMBIN / AI and tooling",
        "Source-grounded analysis • external managed models • deterministic editing and export",
        1100,
    )
    d.edge([(460, 245), (600, 245)], "read only", 485, 228)
    d.edge([(1000, 245), (1140, 245)], "audio", 1035, 228)
    d.edge(
        [(800, 310), (800, 370), (260, 370), (260, 435)],
        "timestamped original-detail JPEG frames",
        325,
        360,
    )
    d.edge([(460, 505), (600, 505)], "validated", 480, 488)
    d.edge([(1000, 505), (1140, 505)], "grounded", 1026, 488)
    d.edge([(1340, 575), (1340, 760)], "text vectors", 1354, 680, True)
    d.edge([(1340, 310), (1340, 435)], "transcript", 1354, 370)
    d.edge([(1140, 835), (1000, 835)], "768-dim", 1025, 818)
    d.edge(
        [(1140, 550), (1080, 550), (1080, 690), (800, 690), (800, 760)],
        "outbox snapshots",
        815,
        680,
    )
    d.edge([(600, 835), (460, 835)], "results", 490, 818)
    d.node(
        60,
        175,
        400,
        135,
        "Immutable originals",
        ["Registered source UUID + SHA256", "Measured stream timing / color"],
        "film",
    )
    d.node(
        600,
        175,
        400,
        135,
        "FFmpeg / ffprobe",
        ["Bounded decoding; preserve detail", "Preview proxies are separate"],
        "film",
    )
    d.node(
        1140,
        175,
        400,
        135,
        "CPU Whisper large-v3",
        ["int8 • VAD • 16 kHz windows", "Speech runs on this AWS host"],
        "ai",
        PURPLE,
    )
    d.node(
        60,
        435,
        400,
        140,
        "Nemotron 3.5 Super VL",
        ["Token Factory vision endpoint", "Eight images / request; batch inputs"],
        "ai",
        GREEN,
        "EXTERNAL HTTPS / METERED INFERENCE",
    )
    d.node(
        600,
        435,
        400,
        140,
        "Nemotron 3 Super",
        ["120B-A12B reasoning endpoint", "Merge batches; compare evidence"],
        "ai",
        GREEN,
        "EXTERNAL HTTPS / NO SILENT FIXTURE FALLBACK",
    )
    d.node(
        1140,
        435,
        400,
        140,
        "PostgreSQL evidence",
        ["Validated source/window references", "Human corrections + pinned selections"],
        "database",
    )
    d.node(
        60,
        760,
        400,
        150,
        "Editor + deterministic tools",
        [
            "Approve ranges; save a revision",
            "Native / FCP7 ZIP + original MP4",
            "Approved export needs no AI call",
        ],
        "human",
        BLUE,
    )
    d.node(
        600,
        760,
        400,
        150,
        "Self-hosted ClickHouse",
        [
            "Scoped text / vector retrieval",
            "Complete revisioned snapshots",
            "Indexes evidence, not video bytes",
        ],
        "database",
        PURPLE,
    )
    d.node(
        1140,
        760,
        400,
        150,
        "Qwen3 Embedding 8B",
        [
            "Token Factory • 768 dimensions",
            "L2 normalization; identity matching",
            "Query + corpus use same generation",
        ],
        "ai",
        GREEN,
    )
    d.footer(
        [
            "Tavily, LangSmith, Toloka and Tendem are optional credits, not active dependencies or verified integrations in this build.",
            "Sampling and ASR accuracy require evaluation. No paired superiority, exhaustive event recall, offline GPU or full NLE claim.",
        ]
    )
    d.save("ai-and-tooling")


def workflow():
    d = Diagram(
        "TRIMBIN / Media-to-export workflow",
        "One canonical timeline feeds both outputs • originals remain unchanged • human controls creative edits",
    )
    for x1, x2 in [(370, 450), (760, 840), (1150, 1230)]:
        d.edge([(x1, 245), (x2, 245)])
    d.edge([(1385, 320), (1385, 440)])
    for x1, x2 in [(1230, 1150), (840, 760), (450, 370)]:
        d.edge([(x1, 515), (x2, 515)])
    d.edge([(215, 590), (215, 710)])
    d.edge(
        [(215, 590), (215, 655), (605, 655), (605, 710)],
        "same saved revision",
        315,
        645,
    )
    d.edge(
        [(215, 860), (215, 925), (995, 925), (995, 860)], "editable bundle", 520, 916
    )
    d.edge([(760, 785), (840, 785)])
    d.edge([(1150, 785), (1230, 785)])
    rows = [
        (
            60,
            170,
            "01 / Upload or mount",
            [
                "Resumable 8 MiB chunks",
                "Allowed deployment roots",
                "Browser-local paths need upload",
            ],
            "film",
        ),
        (
            450,
            170,
            "02 / Register source",
            [
                "Source identity + SHA256",
                "Project-scoped access",
                "Probe timebase and color",
            ],
            "database",
        ),
        (
            840,
            170,
            "03 / Derive previews",
            [
                "Proxy • sprite • audio",
                "Durable processing job",
                "Keep originals immutable",
            ],
            "compute",
        ),
        (
            1230,
            170,
            "04 / Analyze originals",
            [
                "Nemotron visual evidence",
                "CPU Whisper speech path",
                "Provider errors stay visible",
            ],
            "ai",
        ),
        (
            1230,
            440,
            "05 / Human review",
            [
                "Inspect source-linked evidence",
                "Correct uncertain observations",
                "Failed rerun retains prior head",
            ],
            "human",
        ),
        (
            840,
            440,
            "06 / Select ranges",
            [
                "Pin source/evidence versions",
                "Exact allowed source intervals",
                "No fabricated missing footage",
            ],
            "check",
        ),
        (
            450,
            440,
            "07 / Save timeline",
            [
                "Order • trim • mute • gain",
                "Frame-based canonical revision",
                "Conflict + retry protection",
            ],
            "film",
        ),
        (
            60,
            440,
            "08 / Preflight",
            [
                "Recheck originals and hashes",
                "Validate timing / space / format",
                "Block unsupported inputs",
            ],
            "shield",
        ),
        (
            60,
            710,
            "09 / Editable handoff",
            [
                "Native JSON + FCP7 XML ZIP",
                "Manifest + relink references",
                "Premiere acceptance pending",
            ],
            "export",
        ),
        (
            450,
            710,
            "10 / Render video",
            [
                "Decode originals, not proxies",
                "Supported SDR H.264 / AAC",
                "Never cut the source files",
            ],
            "export",
        ),
        (
            840,
            710,
            "11 / Verify + download",
            [
                "Pinned snapshot / artifact hash",
                "Format + frame checks",
                "Scoped authenticated access",
            ],
            "check",
        ),
        (
            1230,
            710,
            "12 / Reopen + recover",
            [
                "Saved revisions persist",
                "Leases / bounded job retry",
                "Backup and restore evidence",
            ],
            "disk",
        ),
    ]
    for x, y, title, lines, icon in rows:
        d.node(x, y, 310, 150, title, lines, icon, GREEN if icon == "ai" else BLUE)
    d.footer(
        [
            "Every failure is a visible state; jobs cannot publish invalid partial evidence as success. Human edits survive re-analysis.",
            "Runtime checks used generated 1080p footage. Real-film quality, wider fidelity and actual Premiere import remain separate gates.",
        ]
    )
    d.save("editorial-workflow")


if __name__ == "__main__":
    system()
    infrastructure()
    ai()
    workflow()
    print("Wrote four editable SVG diagrams to docs/diagrams")
