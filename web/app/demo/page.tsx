import Link from "next/link";

export const metadata = {
  title: "Demo project · Trimbin",
  description:
    "A worked example: what the system decided, what it flagged, and why.",
};

export const dynamic = "force-dynamic";

/**
 * The demo project.
 *
 * A visitor arriving here has ten seconds of patience and no account, so the
 * page has to be useful before it is complete. Footage ingest is not wired to a
 * public project yet, and rather than showing an empty shell this page explains
 * what the system decided on the corpus that is loaded and points at the parts
 * that are genuinely live.
 *
 * Saying plainly what is not here yet is the same discipline as the accuracy
 * page returning null instead of zero. A demo that implies more than it does is
 * the one thing a system built around not overclaiming cannot afford.
 */
export default async function DemoPage() {
  const stats = await loadStats();

  return (
    <main className="shell">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Demo project</span>
        <h1>What the system decided</h1>
        <p className="lede">
          Every figure below is read from the archive as this page loads. The
          corpus is 400 productions worth of decisions — enough that the accuracy
          numbers mean something and the queries have to be fast rather than
          merely correct.
        </p>
      </section>

      {stats ? (
        <>
          <section>
            <div className="stats">
              <Stat label="Productions" value={fmt(stats.productions)} />
              <Stat label="Clips" value={fmt(stats.clips)} />
              <Stat label="Scenes" value={fmt(stats.scenes)} />
              <Stat label="Shots" value={fmt(stats.shots)} />
              <Stat label="Decisions" value={fmt(stats.decisions)} />
              <Stat label="Hours of footage" value={fmt(stats.footage_hours)} />
            </div>
          </section>

          <section>
            <h2>The shape of it</h2>
            <p>
              Of {fmt(stats.shots)} shots, the system settled the great majority
              on its own and sent the rest to a person. That ratio is the whole
              claim, and it is measured rather than asserted —{" "}
              <Link href="/accuracy">the accuracy page</Link> shows it alongside
              how often the confident calls turned out to be wrong.
            </p>
            <p>
              Each decision carries the reason recorded at the time, the
              measurements behind it, and the model and prompt version that
              produced it. Two years from now you can still tell which system
              formed an opinion and whether you would still trust it.
            </p>
          </section>
        </>
      ) : (
        <section>
          <p className="not-run">
            The archive is not answering right now. It idles to keep costs down
            and takes a moment to wake — reloading usually resolves it.
          </p>
        </section>
      )}

      <section>
        <h2>What is running, and what is not</h2>
        <p>
          The decision archive, the accuracy pages and the queries behind them
          are live and reading production data. The ingest path — upload, proxy
          generation, slate reading and comparative analysis — is built and
          tested but not yet wired to a public project, because letting anyone
          upload footage into a shared demo is a way to spend a credit budget
          rather than demonstrate anything.
        </p>
        <p>
          A sandbox with strict limits is the next thing on this page: three
          short clips, rate-limited, deleted after a day. Until it is here, this
          section says so.
        </p>
      </section>

      <section>
        <h2>Look at the data directly</h2>
        <p>
          Nothing on this site is a rendering of numbers you cannot fetch
          yourself.
        </p>
        <ul>
          <li>
            <a href="/api/public/accuracy">/api/public/accuracy</a> — the
            headline figure and everything it is made of
          </li>
          <li>
            <a href="/api/public/scale">/api/public/scale</a> — what the archive
            holds
          </li>
          <li>
            <a href="/api/public/eval">/api/public/eval</a> — results against
            footage with faults planted deliberately
          </li>
          <li>
            <a href="/api/public/reasons">/api/public/reasons</a> — why takes
            lose, and what editors say when they overrule that
          </li>
        </ul>
      </section>
    </main>
  );
}

interface Scale {
  productions: number;
  clips: number;
  scenes: number;
  shots: number;
  decisions: number;
  footage_hours: number;
}

/**
 * Read on the server so the page arrives with its numbers already in it.
 *
 * Returns null rather than throwing: a database that is waking up should give
 * the visitor a sentence explaining that, not an error boundary.
 */
async function loadStats(): Promise<Scale | null> {
  const base = process.env.API_URL ?? "http://localhost:8080";
  try {
    const response = await fetch(`${base}/public/scale`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) return null;
    return (await response.json()) as Scale;
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
