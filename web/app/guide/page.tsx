import Link from "next/link";

const steps = [
  [
    "Bring in the footage",
    "Open a project → Footage → Add files. Choose slate-based organization or enter the scene, shot and take yourself. Transfer progress and processing are separate stages.",
  ],
  [
    "Resolve only the exceptions",
    "With automatic organization enabled, an unambiguous slate can create and fill a scene/shot. Missing slates, conflicting identities and duplicates need your review. Inspect the evidence, choose the destination, or leave the clip unassigned. Nothing is automatically deleted.",
  ],
  [
    "Review one shot",
    "Open Scenes & shots, choose a scene, then a shot. Compare its takes and inspect their timecoded issue lanes. An empty or pending analysis is not a clean bill of health.",
  ],
  [
    "Check the evidence",
    "Click a finding to seek to its source moment. Confirm, dismiss or correct the finding. Keep your creative preference in a human note; preferring another performance is not proof that a technical observation was wrong.",
  ],
  [
    "Confirm the useful portions",
    "Choose ranges from one or several takes. A take with an issue can still contain useful material. Save your shot selections explicitly; clicking Play or switching the active source does not confirm a decision.",
  ],
  [
    "Watch Film Preview",
    "Open Film Preview to watch current confirmed portions across all scenes in scene/shot/range order. Missing selections are listed. This is coverage, not an automatically edited story.",
  ],
  [
    "Arrange a Sequence",
    "Change source In/Out seconds, add alternative takes, reorder or repeat portions, and save the sequence. This order is independent of shot selections. Load a saved revision as a draft to revise it without erasing history.",
  ],
  [
    "Find and hand off",
    "Search your project by action, dialogue, description or issue. Results link back to source moments. Scene exports and the sequence list support hand-off; final conform, grading and sound finishing belong in your NLE.",
  ],
] as const;

export default function Guide() {
  return (
    <main className="shell prose guide-page">
      <section>
        <p className="eyebrow">WORKFLOW GUIDE</p>
        <h1>From shoot day to Film Preview</h1>
        <p className="lede">
          Organize the material. Check the evidence. Keep the choices that tell
          your story.
        </p>
        <Link className="primary" href="/projects">
          Open a project
        </Link>
      </section>
      {steps.map(([title, body], index) => (
        <section key={title}>
          <h2>
            {index + 1} · {title}
          </h2>
          <p>{body}</p>
        </section>
      ))}
      <section>
        <h2>When you leave the page</h2>
        <p>
          In-app navigation can keep an active transfer running. Closing or
          reloading the browser may require reselecting the same files to
          resume. Processing continues on the server after the files arrive. A
          failed item stays visible with its reason.
        </p>
        <p>
          A Film sequence draft can be recovered in the same browser. Save
          shared changes before leaving. If another editor saves first, your
          stale revision cannot overwrite their work.
        </p>
      </section>
      <section>
        <h2>What the measurements mean</h2>
        <p>
          Analysis coverage tells you how much footage was processed.
          First-review agreement counts only explicitly reviewed findings. It
          does not measure acting, narrative quality or all missed problems.
        </p>
        <Link href="/accuracy">Open Accuracy &amp; review →</Link>
      </section>
    </main>
  );
}
