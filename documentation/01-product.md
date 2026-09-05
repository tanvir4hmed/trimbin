# Product

## The problem

A feature shoot produces thirty to a hundred hours of footage. Around two hours
reach the screen.

The other ninety-eight are not waste. They are alternate performances, safety
takes, coverage from angles that were not used this time, and material that a
re-cut two years later would want. What makes them unusable is not the footage —
it is that the reasoning behind every choice lived in one editor's head. Which
take was circled and why. Which one had the better performance but a boom in
frame. Which was rejected for continuity nobody would notice now.

When that editor moves to the next production, the footage stays and the reasoning
leaves. What remains is a folder of files and a timeline, with no way to ask why.

## What Trimbin does

It does the assistant editor's daily job — logging, grouping, triage — and keeps
the notes as a by-product rather than as extra work.

Drop a folder of camera files and it:

1. **Measures** each clip with ffmpeg: exposure, focus, stability, audio level,
   noise floor, freezes, dropped frames. Every finding carries a timecode, so it
   is something you can seek to rather than a sentence about a problem somewhere.
2. **Reads the slate** if there is one, groups the takes of a setup, and flags a
   clip that appears to belong somewhere else. When there is no slate it says so,
   rather than guessing.
3. **Compares** the takes of one camera setup — three specialists and a chief,
   each reporting only on what it can actually know.
4. **Recommends one**, with the reason for every take including the rejected ones,
   and the part of each take that is safe to use.
5. **Remembers** all of it. Every decision, every reason, every human override,
   queryable in plain language years later.

### What it will not do

It never decides where a cut goes and never judges acting. Those are story
questions. Nothing is auto-rejected — a technically worse take is often the right
take, and that call belongs to a person.

## Who it is for

**The assistant editor**, whose day is logging and grouping and who currently
writes notes that nobody reads again.

**The editor**, who wants the four takes of a setup side by side with the reason
each was flagged, and wants to overrule the machine without arguing with it.

**The production that comes back to the material** — for a re-cut, a trailer, a
different edit two years on — and needs the reasoning, not just the files.

Any signed-in client can use the same workflow in a production opened to them:
upload, verify placement, run review, correct findings, choose ranges and leave
comments. This is not a reduced judge sandbox. Destructive actions remain tied
to ownership, so somebody can remove footage they uploaded without being able to
delete another editor's records.

---

## A worked example

A short film. Scene 12 is a two-hander in a kitchen: an argument, shot over four
setups across one afternoon. The camera rolled 41 times. Setup 3 — the reverse on
the second actor — has seven takes.

### Ingest

The assistant drops the card's folder into the browser. The bytes go straight from
the browser to storage by resumable signed URL; they never pass through the
application. Forty-one clips are queued, one message each, and the page returns
immediately.

For each clip the worker reports what it is doing as it does it: downloading,
measuring, reading the slate, encoding a proxy, ready for verification. The middle
of that pipeline used to be silent for several minutes, which is indistinguishable
from a system that has stopped.

The slate agent reads the clapperboard on 38 of the 41. Three were rolled without
a board — the agent says so rather than guessing, and they arrive as unassigned
footage for a person to place.

### Placement

Every reading is a **proposal**. The assistant confirms them in a single pass; the
three unslated clips get placed by hand. One clip the agent read as *Scene 12 /
Setup 4 / Take 1* is actually the tail of setup 3 — the assistant corrects it.

That correction **appends a new row**. The agent's mistaken reading stays on the
record beside the fix, with who corrected it and when. This is why the published
accuracy figure is a query rather than a claim: it is counted from the log by
something other than the thing being measured.

### The panel

With setup 3's seven takes placed, the panel runs.

**Technical** reads the measurements only. All seven are within a few percent of
the setup's own median on exposure, focus and stability — because a competent crew
shot them. It reports no outliers. This is the correct answer and a dull one, and
it is the answer an absolute threshold would have got wrong: the scene is lit dim
on purpose, and a fixed exposure floor would have flagged all seven.

**Continuity** watches what breaks between takes. In take 4 a mug moves from the
left of the counter to the right between the wide and this reverse. It reports the
mismatch with the timecode where it is visible.

**Performance** reports only what is observably true: take 2 stops eleven seconds
in — the actor drops the line. Take 6 runs to the end but the last exchange is
clipped by an early cut of the camera.

**The chief** weighs the three, holding all seven takes at once. It recommends
take 5, with a stated margin over take 7, and gives a reason for each of the
seven — including why take 4 was not chosen despite being the strongest
performance.

The **segment agent** then marks what is usable inside each take. Take 4 is not
discarded: its first 34 seconds are clean, and the mug is only visible after that.
A take with one bad moment is a take with a shorter usable range, not a bad take.

### The decision

The editor opens setup 3 in the cockpit. Take 5 and take 7 play side by side. Each
finding is a control that seeks the player to its timecode — the mug in take 4 is
one click away, not a description to go hunting for.

The editor disagrees. Take 4's performance is worth more than the continuity break,
because the mug is out of frame in the wide that precedes it. They select take 4,
and record why.

**That override is an event.** It does not overwrite the recommendation; it sits
beside it. The accuracy page counts it as a disagreement, which is what makes the
figure worth reading.

Coverage for the shot ends up as ranges from two takes: take 4 up to 00:34, then
take 5 from its equivalent point. The archive records that as editorial usage,
separate from where each clip was placed.

Each range keeps its own reason, origin and author. Saving the final ordered list
does not flatten an AI-proposed range and a manually added range into one generic
reason.

### Two years later

A trailer cut needs the argument. Nobody involved is still on the production.

> *"What was rejected in scene 12, and why?"*

Seven rows come back with the reason recorded at the time, who or what decided
each, and a player that starts a beat before the moment in question. Take 4 shows
as a human selection, over the recommendation, with the editor's reason attached.

The query that produced it is shown beside the answer. A result you can check is
worth more than one you have to trust — that is the entire argument for building
this the way it is built.

---

## What is honest about the numbers

Where there is no data, the interface shows zero or nothing at all. It never
displays a plausible figure it cannot source. Synthetic rows used for testing are
separated at the schema level, in views the application reads, so test data cannot
reach a figure anybody is shown — public or private.

The accuracy figure is where a person overruled the recommendation, counted from
the event log. It is not self-reported, and it is not calculated by the component
being measured.
