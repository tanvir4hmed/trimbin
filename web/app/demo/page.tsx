import Link from "next/link";

export const metadata = {
  title: "Demo project · Trimbin",
  description: "What is running, what is measured, and what is not built yet.",
};

export const dynamic = "force-dynamic";

/**
 * The demo page.
 *
 * There is no interactive demo project yet, and the honest thing is to say so
 * rather than dress the archive up as one. A page that implies a working editor
 * dashboard and delivers a table of generated rows is the failure mode this
 * whole product is built to avoid.
 */
export default async function DemoPage() {
  const corpus = await loadCorpus();

  return (
    <main className="shell">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Demo project</span>
        <h1>What is running, and what is not</h1>
        <p className="lede">
          Trimbin is mid-build. This page is a status report rather than a
          product tour, because the alternative is showing something that looks
          finished and is not.
        </p>
      </section>

      <section>
        <h2>Running, and measured</h2>
        <ul>
          <li>
            <strong>The measurement layer.</strong> Exposure, focus, stability,
            audio and freeze detection, computed with ffmpeg in the same pass
            that builds proxies. Tested against footage with faults planted at
            timecodes we chose — <Link href="/accuracy">results here</Link>, and
            they are the only earned numbers on this site.
          </li>
          <li>
            <strong>The archive and its queries.</strong> ClickHouse with vector
            and text indexes, holding a generated corpus of several hundred
            thousand decisions. That corpus proves the queries stay fast; it is
            excluded from every accuracy figure, because a number computed over
            generated rows measures the generator.
          </li>
          <li>
            <strong>The deployment.</strong> Everything here is Terraform,
            deployed by push, with the whole environment reproducible from an
            empty project.
          </li>
        </ul>
      </section>

      <section>
        <h2>Built, but not yet running end to end</h2>
        <p>
          The four agents, their prompts and their contracts are written and unit
          tested. They have not yet been run against real footage through a live
          model, so nothing on this site claims they have.
        </p>
        <ul>
          <li>Slate reading and take grouping</li>
          <li>The comparison panel and its supervising editor</li>
          <li>Assembly, in and out points, EDL and streaming playlist</li>
          <li>Natural-language retrieval over the archive</li>
        </ul>
      </section>

      <section>
        <h2>Not built</h2>
        <ul>
          <li>Upload for anyone but us</li>
          <li>The editor dashboard — review queue and assembly playback</li>
          <li>Sign-in, project switching, director notes</li>
        </ul>
        <p className="dim small">
          Listing these is deliberate. A demo page that quietly omits what is
          missing is the same overclaim as an accuracy figure computed over
          invented data, and this project has already made that mistake once.
        </p>
      </section>

      {corpus && (
        <section>
          <h2>What the archive holds right now</h2>
          <div className="stats">
            <Stat label="Real clips" value={fmt(corpus.real.clips)} />
            <Stat label="Real hours" value={fmt(corpus.real.footage_hours)} />
            <Stat
              label="Generated clips"
              value={fmt(corpus.synthetic.clips)}
            />
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
            agreement, currently empty and saying so
          </li>
          <li>
            <a href="/api/public/scale">/api/public/scale</a> — real and
            generated counted apart
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
