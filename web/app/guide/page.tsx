import Link from "next/link";

/**
 * How to work the product, in the order somebody actually does it.
 *
 * Written as a sequence rather than a feature list. A feature list tells you
 * what exists; this has to tell somebody what to do on a Monday with a drive
 * full of footage and no idea where to start.
 *
 * It doubles as the acceptance script. Every step says what you should see
 * when it worked, because a walkthrough that only describes the happy path
 * cannot tell you whether the happy path happened — and the QA that found nine
 * release blockers found most of them by noticing a screen said something
 * slightly different from what it should have.
 */
export default function Guide() {
  return (
    <main className="shell prose">
      <section style={{ paddingTop: 56 }}>
        <span className="eyebrow">Guide</span>
        <h1>How to use it</h1>
        <p className="lede">
          Fifteen minutes end to end, from a drive of camera files to a scene
          you can watch and a decision you can defend. Each step says what you
          should see when it worked, so anything that does not match is worth
          reporting rather than working around.
        </p>
        <p>
          Everyone signed in can do all of this. A client reviewing with the
          editors has the same powers they do — compare, judge, choose, upload —
          with one boundary: you can remove footage you uploaded, never
          somebody else&rsquo;s.
        </p>
      </section>

      <section>
        <h2>1 · Declare the scenes and shots</h2>
        <p>
          Open <Link href="/projects">Projects</Link>, pick a production, then{" "}
          <strong>Upload takes</strong>. Scenes and shots are declared on that
          page, beside the footage that will go into them.
        </p>
        <p>
          Use the codes from the board — <code>3</code>, <code>12A</code>,{" "}
          <code>A012C</code>, <code>12A-PU</code>. They are names, not numbers,
          and they are matched against the slate exactly as written.
        </p>
        <p className="callout">
          <strong>Expect:</strong> the scene appears with its shots underneath,
          each showing <em>no footage</em> until something lands in it.
        </p>
      </section>

      <section>
        <h2>2 · Add a shoot day</h2>
        <p>
          Drop camera files on the same page. Four stages run in order — add
          files, read slates, verify matches, ingest — and nothing enters the
          production until you commit the batch.
        </p>
        <p>
          Choose <strong>AI reads the slate</strong> to let the board decide, or{" "}
          <strong>I know scene / shot / take</strong> to declare a destination.
          A declared destination always wins; a slate that disagrees with it is
          reported rather than obeyed, because moving footage on a misread board
          is the one mistake that scatters a shoot day silently.
        </p>
        <p className="callout">
          <strong>Expect:</strong> a row per clip with its slate frame,
          duration, camera and confidence, and a status of <em>Matched</em>,{" "}
          <em>Needs review</em>, <em>Unassigned</em> or <em>Duplicate</em>.
          Uploading continues if you navigate away — the tray at the bottom
          follows you. A refresh mid-upload keeps the batch but needs the same
          files chosen again; browsers do not hand a page back its file handles.
        </p>
      </section>

      <section>
        <h2>3 · Verify before committing</h2>
        <p>
          Every row needs a decision: keep the proposed match, move it, create
          the shot if it was never planned, or leave it unassigned. The
          inspector on the right shows the frame the board was read from and the
          text read off it, because deciding whether the slate or the reader was
          wrong means looking at the board.
        </p>
        <p>
          A file whose bytes are already here is flagged as a duplicate and
          never deleted. You can replace the take it duplicates — both clips
          survive; only which one stands for that take changes.
        </p>
        <p className="callout">
          <strong>Expect:</strong> commit is blocked until every row is
          resolved. Unassigned footage goes to its own bin — it must never
          appear as a scene or shot, or count toward a shot&rsquo;s takes.
        </p>
      </section>

      <section>
        <h2>4 · Let it analyse</h2>
        <p>
          Committing queues each take for full-duration analysis. This is not
          instant, and the take card says which state it is in:{" "}
          <em>queued for analysis</em>, <em>analysing…</em>, <em>analysed</em>,
          or <em>analysis failed</em>.
        </p>
        <p className="callout">
          <strong>Expect:</strong> a take that has been analysed and found
          nothing says <em>clean</em>. A take nobody has looked at yet says so.
          Those two must never look the same — if a lane is empty and the card
          claims clean before analysis finished, that is a defect.
        </p>
      </section>

      <section>
        <h2>5 · Open a shot</h2>
        <p>
          A project opens on its scenes; a scene opens on its shots; a shot
          opens the cockpit. The take you choose plays on the right with the
          take before it on the left, so you are always comparing against what
          came immediately before.
        </p>
        <p>
          <strong>Every take on one clock</strong> puts every take of the shot
          on one shared timeline — clean stretches, issues, slate and exit — so
          you can see at a glance which take holds together.
        </p>
        <p className="callout">
          <strong>Expect:</strong> the highlighted take card, the video badge
          and the take buttons always agree about which take you are on. A shot
          with a single take still plays and can still be cut from; there is
          simply nothing to compare it against.
        </p>
      </section>

      <section>
        <h2>6 · Work the issues</h2>
        <p>
          Issues are grouped in tabs, one per take. Clicking one seeks the
          player to the exact span and opens it, with the evidence frame, the
          model&rsquo;s note, and four actions: the issue is correct, dismiss
          it, correct the description, or adjust where it actually falls.
        </p>
        <p>
          Nothing is deleted. A dismissed finding leaves the working view and
          stays in the history with your name on it.
        </p>
        <p className="callout">
          <strong>Expect:</strong> a confirmed or dismissed finding stops
          appearing in <em>to verify</em>. Closing the panel works three ways —
          the close button, Escape, or clicking the same issue again.
        </p>
      </section>

      <section>
        <h2>7 · Choose what stands for the shot</h2>
        <p>
          This is the decision the system exists for. Set the in and out points
          and press <strong>Add range</strong>. Add as many as you need: several
          ranges from one take, ranges from different takes, in whatever order
          plays best. Reorder them with the arrows, preview with{" "}
          <strong>Play this shot</strong>, then save.
        </p>
        <p>
          Where you disagree with the suggestion, say why. The reason is what
          makes the archive worth searching a year later.
        </p>
        <p className="callout">
          <strong>Expect:</strong> after saving, the button reads{" "}
          <em>✓ n ranges saved</em> and stays that way until something changes.
          Refresh the page — the ranges must come back exactly as you left them,
          in the same order. The shot header says what stands for it:{" "}
          <em>Take 2 · 3 ranges</em> when they all come from one take,{" "}
          <em>Custom · 4 ranges from takes 1, 2</em> when they do not.
        </p>
      </section>

      <section>
        <h2>8 · Watch the scene</h2>
        <p>
          <strong>Play scene</strong> runs the coverage reel: your chosen ranges
          in order, shot after shot. A shot nobody has chosen ranges for is an
          explicit <em>GAP</em> rather than a silent omission.
        </p>
        <p>
          The V1 / A1 timeline underneath is a read-only picture of those
          decisions. It is not an edit and Trimbin does not pretend to make one.
        </p>
        <p className="callout">
          <strong>Expect:</strong> a shot with four ranges counts as one shot,
          not four. Clicking a block seeks to that exact source range.
        </p>
      </section>

      <section>
        <h2>9 · Ask the archive</h2>
        <p>
          Describe a moment in plain language — <em>where does she drop the
          shoes</em> — and the search returns the clip and a playable span.
          Every answer shows the rows behind it and the query that produced
          them, so it can be checked rather than trusted.
        </p>
        <p className="callout">
          <strong>Expect:</strong> the result seeks to the event, not to the
          start of a long processing window. A clip nobody has decided about is
          reported as <em>analysed</em> — never as <em>selected</em>. If the
          archive claims a decision that was never made, that is the most
          serious thing you can find here.
        </p>
      </section>

      <section>
        <h2>10 · Take it to your NLE</h2>
        <p>
          <strong>EDL</strong> and <strong>Markers</strong> export the scene as
          source ranges with timecode. One event per chosen range, carrying the
          source clip and its in and out points.
        </p>
        <p className="callout">
          <strong>Expect:</strong> the event order and timecodes match what you
          watched. Mixed frame rates are reported rather than silently
          reconciled.
        </p>
      </section>

      <section>
        <h2>What the dots mean</h2>
        <ul className="plain">
          <li>
            <strong>needs you</strong> — the call was close enough that a person
            should look.
          </li>
          <li>
            <strong>not compared</strong> — nothing has judged this shot yet.
          </li>
          <li>
            <strong>differs from the circle</strong> — the director circled one
            take and the measurements chose another. This outranks everything,
            because the circle knows about performance and this system
            deliberately does not judge it.
          </li>
          <li>
            <strong>choose a range</strong> — nobody has decided what stands for
            this shot.
          </li>
          <li>
            <strong>settled</strong> — a person has chosen, and their choice
            holds until the evidence changes.
          </li>
        </ul>
        <p>
          Add a take to a settled shot and it reopens. The old decision is not
          deleted — it is marked as made against footage that has since changed.
        </p>
      </section>

      <section>
        <h2>If something looks wrong</h2>
        <p>
          The states above are the contract. Anything that contradicts them is
          worth reporting even if the screen still works: a count that
          disagrees with another screen, a take that says clean before it was
          analysed, a decision attributed to somebody who did not make it,
          footage appearing in a scene nobody put it in.
        </p>
        <p>
          Trimbin publishes{" "}
          <Link href="/accuracy">how often it is right</Link>, measured rather
          than asserted, and{" "}
          <Link href="/demo">what is built and what is not</Link>. Both are
          worth reading before deciding how much to trust any single answer.
        </p>
      </section>
    </main>
  );
}
