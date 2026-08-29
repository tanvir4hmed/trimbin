import Link from "next/link";

/**
 * How to work a queue, in the order somebody actually does it.
 *
 * Written as a sequence rather than a feature list. A feature list tells you
 * what exists; this has to tell an editor what to do on a Monday with a drive
 * full of footage and no idea where to start.
 */
export default function Guide() {
  return (
    <main className="shell prose">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Guide</span>
        <h1>How to use it</h1>
        <p className="lede">
          Five minutes end to end. Everything below is doable by anyone signed
          in, including on our productions — the only thing reserved to the
          editors here is putting footage into them.
        </p>
      </section>

      <section>
        <h2>1 · Start at the dashboard</h2>
        <p>
          <strong>Needs you</strong> is the whole point. It is every shot across
          every project you can open where a person actually adds something —
          the calls that were close, the shots nothing has compared yet, and the
          ones where the take the director circled is not the take the
          measurements chose.
        </p>
        <p>
          Your own shots sort first, then unassigned ones, then everybody
          else&rsquo;s. Nothing is hidden: a queue that hid other people&rsquo;s
          work would let three editors each believe the scene is nearly done.
        </p>
      </section>

      <section>
        <h2>2 · Open a shot</h2>
        <p>
          Every take is listed, including the rejected ones. &ldquo;Why not that
          one?&rdquo; is the question the archive exists to answer, and a screen
          that shows only the winner cannot answer it.
        </p>
        <p>
          The table across the top is the useful reading: which{" "}
          <em>criterion</em> separates these takes. Each axis says whether it was
          measured by ffmpeg or observed by a model, because an editor deciding
          whether to trust a number should know which.
        </p>
      </section>

      <section>
        <h2>3 · Click a finding</h2>
        <p>
          Findings carry timecodes and the timecodes are links. Told
          &ldquo;unstable&rdquo;, you have to go and find it; told{" "}
          <span className="mono">unstable · 4.2s</span> and given a click that
          seeks there, you have been saved the search. That is most of the value
          of measuring anything.
        </p>
        <p>
          The bar under the player is the shape of the take: solid where it is
          usable, hollow where time was removed, marked where something happens.
          A take with a jolt in the middle is not a discarded take — it is twenty
          usable seconds on the far side of it.
        </p>
      </section>

      <section>
        <h2>4 · Overrule it, and say why</h2>
        <p>
          The reason is required. An override without one is the exact moment
          this archive exists to capture, arriving empty — it is the only record
          anywhere of a human editorial judgement, and the reason no model can be
          trained to make these calls today.
        </p>
        <p>
          Confirming the recommendation is recorded too. &ldquo;The editor
          agreed&rdquo; is evidence; silence is not, and a system that only
          writes down disagreements cannot tell a good decision from an
          unexamined one.
        </p>
        <p>
          Changed your mind? <strong>Undo</strong> puts back what stood before —
          by writing a third decision, never by deleting the second. An archive
          whose whole claim is that it remembers every decision cannot be the
          kind that erases one.
        </p>
      </section>

      <section>
        <h2>5 · Leave a note where it happened</h2>
        <p>
          Comments anchor to a second of a take, the way they do in every review
          tool an editor already uses. Pause, type, and the note sticks to that
          frame. Anyone signed in can comment; anyone can reply; anyone can mark
          one dealt with.
        </p>
      </section>

      <section>
        <h2>6 · Watch the scene</h2>
        <p>
          <strong>Play the scene</strong> assembles a stringout: every shot in
          order, one take each, from the takes that currently stand. That is what
          an assistant editor hands the editor, and it is the point of all the
          rest of it.
        </p>
        <p>
          It is not an edit. Nothing here decides where a cut goes, how long a
          shot holds, or which angle a moment belongs to — those are story
          questions. A stringout is the raw material you cut <em>from</em>.
        </p>
      </section>

      <section>
        <h2>7 · Take it to your NLE</h2>
        <p>
          <strong>EDL</strong> gives you the stringout as a CMX3600 file with the
          reasoning in the comment lines. <strong>Markers</strong> gives you every
          finding and every note as timeline markers, positioned where they land
          in the assembly rather than where they sat in the source.
        </p>
        <p className="dim small">
          One honest limitation: the frame rate is declared, not measured.
          Nothing in the archive records what the original was shot at, so an EDL
          generated at 24 for 25fps footage drifts a frame a second. The header
          says which rate was used.
        </p>
      </section>

      <section>
        <h2>What the dots mean</h2>
        <dl className="legend">
          <div>
            <dt>
              <span className="dot needs_review" /> needs you
            </dt>
            <dd>The gap to the runner-up was small enough that a person should look.</dd>
          </div>
          <div>
            <dt>
              <span className="dot differs_from_circle" /> differs from the circle
            </dt>
            <dd>
              The director circled a different take. The circle knows about
              performance, which this system deliberately never judges.
            </dd>
          </div>
          <div>
            <dt>
              <span className="dot not_judged" /> not compared
            </dt>
            <dd>The takes are here and nothing has run yet.</dd>
          </div>
          <div>
            <dt>
              <span className="dot decided" /> decided
            </dt>
            <dd>A clear call. Nobody has looked, and nobody needs to.</dd>
          </div>
          <div>
            <dt>
              <span className="dot confirmed" /> confirmed
            </dt>
            <dd>A person agreed with it, or chose otherwise and said why.</dd>
          </div>
          <div>
            <dt>
              <span className="dot too_few_takes" /> one take
            </dt>
            <dd>Nothing to compare it against. A fact, not work.</dd>
          </div>
        </dl>
      </section>

      <section>
        <h2>If you are here as a guest</h2>
        <p>
          You get the same application. Read every production here, comment on
          any shot, overrule any call — your decisions are recorded with your
          name and they change what everyone sees, which is the whole
          demonstration.
        </p>
        <p>
          For your own footage, make a project. Inside it you are an editor,
          upload included. The limits are on the New Project screen before you
          start rather than sprung afterwards.
        </p>
      </section>

      <section>
        <p>
          <Link href="/about">What this is</Link>
          {" · "}
          <Link href="/dashboard">Go to the dashboard</Link>
        </p>
      </section>
    </main>
  );
}
