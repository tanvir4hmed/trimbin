import Link from "next/link";

/**
 * The front page.
 *
 * A visitor arrives with no context and roughly ten seconds of patience. The
 * job here is to say what this is, show that it is running, and get out of the
 * way — not to sell. Every claim on this page is checkable from another page on
 * this site, which is the only kind of claim worth making about an AI system.
 */
export default function Home() {
  return (
    <main className="shell">
      <section style={{ paddingTop: 64, paddingBottom: 20 }}>
        <span className="eyebrow">Agentic Cinema · ClickHouse track</span>
        <h1>An assistant editor that never forgets</h1>
        <p className="lede">
          In film editing, the trim bin held every frame you cut away, and
          editors went back to it constantly. Digital editing quietly threw that
          away. Trimbin organises a shoot day on its own, surfaces only the shots
          that need a human eye, and remembers every take it passed over and why.
        </p>

        <div style={{ display: "flex", gap: 10, marginTop: 26, flexWrap: "wrap" }}>
          <Link href="/demo" className="primary" style={{ textDecoration: "none" }}>
            Open the demo project
          </Link>
          <Link href="/accuracy" className="ghost" style={{ textDecoration: "none" }}>
            See how often it is right
          </Link>
        </div>
      </section>

      <section>
        <h2>What it does</h2>
        <div className="split">
          <article className="panel">
            <span className="panel-label">Organises the day</span>
            <p className="panel-detail" style={{ margin: "6px 0 0" }}>
              Drop a shoot folder. Slates are read, takes are grouped, proxies
              are made. No forms and no manual logging.
            </p>
          </article>
          <article className="panel">
            <span className="panel-label">Narrows the work</span>
            <p className="panel-detail" style={{ margin: "6px 0 0" }}>
              Six of sixty-eight shots need your eye. The rest were clear calls
              and nobody has to look at them.
            </p>
          </article>
          <article className="panel">
            <span className="panel-label">Remembers everything</span>
            <p className="panel-detail" style={{ margin: "6px 0 0" }}>
              Every take considered, every measurement, every reason, every human
              override — queryable years later.
            </p>
          </article>
        </div>
      </section>

      <section>
        <h2>What it will not claim</h2>
        <p>
          No model has been trained to judge which take an editor would choose,
          because that data has never existed — nobody recorded it. So Trimbin
          does not claim to judge acting. It handles everything around that
          judgement and hands the editor a decision that takes seconds instead of
          an hour.
        </p>
        <p>
          Nothing is ever discarded automatically. A technically worse take is
          often the right take, and a system that quietly drops it is worse than
          no system at all.
        </p>
      </section>

      <section>
        <h2>How it decides</h2>
        <p>
          Judgement follows Walter Murch&rsquo;s Rule of Six, the standard
          framework in film editing. Emotion and story are the top 74% and belong
          to a person; Trimbin does not enter them. Rhythm, eye-trace, planarity
          and spatial continuity are progressively more objective, and that is
          where an agent earns its place.
        </p>
        <p>
          Work splits by what is knowable. Exposure, focus, stability and audio
          are <em>measured</em> with ffmpeg — exact, cheap and repeatable, where
          asking a model would be a guess. Whether an action completed and
          whether continuity holds are <em>observed</em> by a model. Whether the
          performance is right is <em>left alone</em>.
        </p>
        <p>
          Every measurement is relative to the other takes of the same shot,
          never to an absolute standard. If all seven takes are handheld, that is
          the language of the scene. If six are locked off and one is not, that
          one is probably an accident.
        </p>
      </section>

      <section>
        <h2>Built on</h2>
        <p className="dim small">
          Gemini 3.6 Flash for video · Google ADK on Vertex AI Agent Engine ·
          ClickHouse Cloud through the official MCP server · Cloud Run · all
          infrastructure in Terraform, deployed by push.
        </p>
      </section>
    </main>
  );
}
