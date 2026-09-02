import Link from "next/link";

export const metadata = {
  title: "Status · Trimbin",
  description: "What is running, what is measured, and what is not built yet.",
};

export const dynamic = "force-dynamic";

/**
 * The status page.
 *
 * Kept, and kept honest. A page that quietly omits what is missing is the same
 * overclaim as an accuracy figure computed over invented data, and this project
 * has already made that mistake once.
 *
 * It used to say there was no interactive product. There is one now, so the
 * page says that instead — and the list of what is still not earned stays,
 * because that half is the half worth publishing.
 */
export default async function StatusPage() {
  const corpus = await loadCorpus();

  return (
    <main className="shell prose">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Status</span>
        <h1>What is running, and what is not</h1>
        <p className="lede">
          Every claim on this page is checkable from an endpoint listed at the
          bottom. That is the only kind of claim worth making about a system that
          judges things.
        </p>
      </section>

      <section>
        <h2>Running</h2>
        <ul>
          <li>
            <strong>The measurement layer.</strong> Exposure, focus, stability,
            audio and freeze detection, computed with ffmpeg in the same pass
            that builds proxies. Tested against footage with faults planted at
            timecodes we chose — <Link href="/accuracy">results here</Link>, and
            they are the only earned numbers on this site.
          </li>
          <li>
            <strong>The panel.</strong> Three specialists and a chief, on the
            footage. It finds what measurement cannot: a take that stops
            mid-sentence, a whip pan that breaks eye-trace, a wall crossing the
            foreground.
          </li>
          <li>
            <strong>Upload, end to end.</strong> A clip uploaded to a signed URL
            is measured, read for a slate, embedded, encoded and playing through
            the CDN without anyone touching it.
          </li>
          <li>
            <strong>The application.</strong> A dashboard with a queue across
            projects, a shot screen with per-criterion reasoning and timecoded
            findings, timecoded comments, assignment and set status, the scene
            as a stringout, and EDL and marker export.{" "}
            <Link href="/projects">Open a public project</Link>.
          </li>
          <li>
            <strong>The archive and its queries.</strong> ClickHouse with vector
            and text indexes, reached by the agent through the official MCP
            server as a read-only user. It holds a generated corpus of several
            hundred thousand decisions, which proves the queries stay fast and is
            excluded from every published figure — a number computed over
            generated rows measures the generator.
          </li>
          <li>
            <strong>The deployment.</strong> Terraform, deployed by push, with
            the whole environment reproducible from an empty project.
          </li>
        </ul>
      </section>

      <section>
        <h2>Not earned yet</h2>
        <ul>
          <li>
            <strong>An editorial accuracy figure.</strong> It stays null until
            editors have overridden enough decisions to compute one. Null is not
            zero, and the interface keeps them apart.
          </li>
          <li>
            <strong>Embeddings on the generated corpus.</strong> Only
            worker-ingested clips carry one, so similarity search reaches the
            real rows and not the synthetic ones.
          </li>
          <li>
            <strong>Suggested Assembly.</strong> Trimbin provides ordered human
            selects and a Coverage Reel, not an automatic multi-shot edit. It
            stays out until editors explicitly approve that product boundary.
          </li>
          <li>
            <strong>Performance judgement.</strong> AI recommendations use
            observable technical, continuity and completion evidence. Acting
            and rhythm remain human reasons and are never presented as measured
            facts.
          </li>
        </ul>
        <p className="dim small">
          Listing these is deliberate. A status page that omits what is missing
          is worth nothing to the person reading it.
        </p>
      </section>

      {corpus && (
        <section>
          <h2>What the archive holds right now</h2>
          <div className="stats">
            <Stat label="Real clips" value={fmt(corpus.real.clips)} />
            <Stat label="Real hours" value={fmt(corpus.real.footage_hours)} />
            <Stat label="Generated clips" value={fmt(corpus.synthetic.clips)} />
            <Stat
              label="Generated hours"
              value={fmt(corpus.synthetic.footage_hours)}
            />
          </div>
          <p className="dim small">{corpus.synthetic.purpose}</p>
        </section>
      )}

      <section>
        <h2>Check it yourself</h2>
        <p>
          Nothing on this site is a rendering of numbers you cannot fetch
          directly.
        </p>
        <ul>
          <li>
            <a href="/api/public/eval">/api/public/eval</a> — results against
            planted faults, the earned numbers
          </li>
          <li>
            <a href="/api/public/accuracy">/api/public/accuracy</a> — editorial
            agreement, and what it says when there is not enough of it
          </li>
          <li>
            <a href="/api/public/scale">/api/public/scale</a> — real and
            generated counted apart
          </li>
          <li>
            <a href="/api/public/limits">/api/public/limits</a> — what a guest
            account may hold, from the code that enforces it
          </li>
        </ul>
      </section>
    </main>
  );
}

interface Corpus {
  real: { productions: number; clips: number; shots: number; footage_hours: number };
  synthetic: { clips: number; footage_hours: number; purpose: string };
}

async function loadCorpus(): Promise<Corpus | null> {
  const base = process.env.API_URL ?? "http://localhost:8080";
  try {
    const response = await fetch(`${base}/public/scale`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) return null;
    return (await response.json()) as Corpus;
  } catch {
    return null;
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="stat-value mono">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}
