import Link from "next/link";

export const metadata = {
  title: "About · Trimbin",
  description: "An editorial preparation and decision workspace.",
};

export default function AboutPage() {
  return (
    <main className="shell prose">
      <section>
        <p className="eyebrow">ABOUT TRIMBIN</p>
        <h1>Your footage, evidence and editorial decisions—connected.</h1>
        <p className="lede">
          Trimbin helps a team turn a shoot day's recordings into organized,
          searchable material and a preview of the portions they choose.
        </p>
      </section>
      <section>
        <h2>The editor stays in charge</h2>
        <p>
          AI reads slates, records observable events, describes footage and
          suggests useful ranges. Editors verify findings, choose alternatives
          and record creative reasons. A technical issue does not make an entire
          take unusable, and a clean take is not automatically the right
          performance.
        </p>
      </section>
      <section>
        <h2>Three distinct views of your work</h2>
        <ul>
          <li>
            <strong>Footage:</strong> the source recordings and where they
            belong.
          </li>
          <li>
            <strong>Shot Review:</strong> evidence, alternatives and the team's
            confirmed portions.
          </li>
          <li>
            <strong>Film Preview:</strong> those portions played across scenes,
            or arranged into an independent saved sequence.
          </li>
        </ul>
      </section>
      <section>
        <h2>Built for traceable decisions</h2>
        <p>
          Google Cloud and Gemini support media processing and observation.
          ClickHouse stores analytical evidence and powers scoped retrieval
          through its official MCP server. Firestore owns operational state and
          revisions; Cloud Storage holds media. Playback uses prepared sources
          rather than asking a model on every seek.
        </p>
      </section>
      <section>
        <h2>Honest boundaries</h2>
        <p>
          This is not a finishing NLE or an objective judge of acting. Browser
          preview does not replace frame-accurate conform, grading, sound
          editing or delivery. Review agreement describes what people explicitly
          checked; it is not a claim of universal accuracy.
        </p>
        <p>
          <Link href="/demo">Explore the example production</Link> ·{" "}
          <Link href="/guide">Workflow guide</Link> ·{" "}
          <Link href="/accuracy">Live review measurements</Link>
        </p>
      </section>
    </main>
  );
}
