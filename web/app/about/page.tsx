import Link from "next/link";

/**
 * What this is, for somebody who wants to know.
 *
 * Everything that used to be the front page. It is worth reading and it is not
 * the front door — a person arriving at an application is looking for the way
 * in, and nine screens of method is what they scroll past to find it.
 *
 * Every claim here is checkable from another page on this site, which is the
 * only kind of claim worth making about a system that judges things.
 */
export default function About() {
  return (
    <main className="shell prose">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Agentic Cinema · ClickHouse track</span>
        <h1>An assistant editor that never forgets</h1>
        <p className="lede">
          In film editing, the trim bin held every frame you cut away, and
          editors went back to it constantly. Digital editing quietly threw that
          away. Trimbin organises a shoot day on its own, surfaces only the shots
          that need a human eye, and remembers every take it passed over and why.
        </p>
      </section>

      <section>
        <h2>The job it does</h2>
        <ol className="numbered">
          <li>A shoot day arrives — a folder of takes.</li>
          <li>
            Everything is measured, grouped by shot, and compared{" "}
            <em>within</em> its shot.
          </li>
          <li>
            The editor is handed the short list: these six shots need your eye;
            the other sixty-two were clear.
          </li>
          <li>They confirm or overrule, and say why.</li>
          <li>The scene plays back from the chosen takes.</li>
          <li>
            Two years later somebody asks why take 4 and not take 5, and gets an
            answer.
          </li>
        </ol>
      </section>

      <section>
        <h2>The vocabulary</h2>
        <p>
          A <strong>scene</strong> is what the script calls a scene. A{" "}
          <strong>shot</strong> is one camera position within it — 12A the wide,
          12B her close-up — which is what a script supervisor marks by drawing a
          vertical line down the page for each setup. A <strong>take</strong> is
          one attempt at a shot. The slate says <span className="mono">12A</span>{" "}
          / <span className="mono">TAKE 3</span>, and that is exactly the
          hierarchy here.
        </p>
        <p>
          Takes are only ever compared within their own shot. A wide and a
          close-up of the same moment are not alternatives to each other —
          choosing between them is a story question, and this system has no
          standing to answer it.
        </p>
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
        <h2>The take the room circled</h2>
        <p>
          On set the director or DoP marks the takes they liked, and the script
          supervisor writes it down. That is the strongest prior about a shot
          that exists anywhere, and it is recorded here — but it is never shown
          to the panel.
        </p>
        <p>
          Telling a model which take a human preferred ends the measurement: it
          agrees, and the agreement is then reported as an independent
          confirmation of a judgement it was handed. So the circle is kept out of
          the comparison and used on the way out instead. A shot where the panel
          picks take 1 and the director circled take 3 goes to the top of the
          queue, because that is where a person adds the most.
        </p>
      </section>

      <section>
        <h2>Who can do what</h2>
        <p>
          Three editors work here, and everybody else who arrives is a guest. A
          guest is not a spectator: they can read our productions, comment on any
          shot, and overrule any call the panel made, with a reason. Watching
          somebody disagree with the system is the product.
        </p>
        <p>
          A signed-in guest works like an editor in productions opened to them:
          they can upload footage, run review, correct findings, choose ranges and
          comment. Destructive authority remains attached to ownership, so they
          cannot delete footage another editor uploaded.
        </p>
      </section>

      <section>
        <h2>Built on</h2>
        <p className="dim small">
          Gemini 3.6 Flash for video · ClickHouse Cloud through the official MCP
          server · Cloud Run for the API, the worker and the interface · Firestore
          for the things people retype · all infrastructure in Terraform,
          deployed by push.
        </p>
      </section>

      <section>
        <p>
          <Link href="/guide">How to actually use it</Link>
          {" · "}
          <Link href="/accuracy">How often it is right</Link>
          {" · "}
          <Link href="/">Back to the front</Link>
        </p>
      </section>
    </main>
  );
}
