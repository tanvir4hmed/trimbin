/**
 * Uploading a shoot day.
 *
 * Three things the previous version got wrong on real footage.
 *
 * **One file at a time.** A shoot day is forty files on an office connection,
 * and doing them in series left most of the link idle while one request waited
 * on round trips.
 *
 * **No resume.** A connection that dropped at ninety per cent of a four-gigabyte
 * file started that file again from zero.
 *
 * A resumable session fixes interrupted requests within the active upload.
 * Cloud Storage hands back a session URI;
 * the browser can ask it how many bytes arrived and continue from there. The
 * browser cannot restore a File object after a refresh, so this does not claim
 * cross-refresh recovery: after a reload the person must choose the files again.
 */

export interface Ticket {
  clip_id: string;
  filename: string;
  upload_url: string;
  headers: Record<string, string>;
}

export interface Progress {
  clipId: string;
  filename: string;
  sent: number;
  total: number;
  state: "waiting" | "uploading" | "done" | "failed";
  error?: string;
}

/** How many files move at once.
 *
 * Three rather than one, and not thirty: a browser caps connections per host
 * anyway, and saturating the uplink makes every file slow rather than making
 * three fast. */
const PARALLEL = 3;

/** Chunk size for resumable puts. A multiple of 256 KiB, which Cloud Storage
 *  requires for every chunk but the last. */
const CHUNK = 8 * 1024 * 1024;

/** Session capabilities live only for this page. Persisting one without the
 * File object and batch ticket cannot resume anything after a refresh, and it
 * leaves a storage capability behind in localStorage for no benefit. */
const sessionUris = new Map<string, string>();

function remember(clipId: string, uri: string): void {
  sessionUris.set(clipId, uri);
}

function forget(clipId: string): void {
  sessionUris.delete(clipId);
}

/** Open a resumable session, or reuse the one this file already has. */
async function openSession(ticket: Ticket): Promise<string> {
  const existing = sessionUris.get(ticket.clip_id);
  if (existing) return existing;

  const response = await fetch(ticket.upload_url, {
    method: "POST",
    headers: ticket.headers,
  });
  if (!response.ok) {
    throw new Error(`could not start the upload (${response.status})`);
  }

  const uri = response.headers.get("Location");
  if (!uri) throw new Error("storage did not return a session");

  remember(ticket.clip_id, uri);
  return uri;
}

/**
 * How many bytes the server already has.
 *
 * Asked before continuing, because our idea of what was sent and the server's
 * can differ by exactly the request that died.
 */
async function bytesReceived(session: string, total: number): Promise<number> {
  const probe = await fetch(session, {
    method: "PUT",
    headers: { "Content-Range": `bytes */${total}` },
  });

  if (probe.status === 200 || probe.status === 201) return total;
  if (probe.status !== 308) return 0;

  const range = probe.headers.get("Range");
  if (!range) return 0;
  // `bytes=0-1048575` — the last byte received, so the next offset is +1.
  return Number(range.split("-")[1]) + 1;
}

async function uploadOne(
  ticket: Ticket,
  file: File,
  onProgress: (sent: number) => void,
): Promise<void> {
  const session = await openSession(ticket);
  let offset = await bytesReceived(session, file.size);
  onProgress(offset);

  while (offset < file.size) {
    const end = Math.min(offset + CHUNK, file.size);
    const response = await fetch(session, {
      method: "PUT",
      headers: {
        "Content-Range": `bytes ${offset}-${end - 1}/${file.size}`,
      },
      body: file.slice(offset, end),
    });

    if (response.status === 200 || response.status === 201) {
      offset = file.size;
      break;
    }
    if (response.status !== 308) {
      throw new Error(`upload failed at ${offset} (${response.status})`);
    }

    const range = response.headers.get("Range");
    offset = range ? Number(range.split("-")[1]) + 1 : end;
    onProgress(offset);
  }

  onProgress(file.size);
  forget(ticket.clip_id);
}

/**
 * Send everything, a few at a time, reporting as it goes.
 *
 * A file that fails does not stop the batch. It is reported and the rest
 * continue, because an editor who dropped forty files and got thirty-nine has
 * something to work with and a name to retry.
 */
export async function uploadAll(
  tickets: Ticket[],
  files: File[],
  onProgress: (rows: Progress[]) => void,
): Promise<{ arrived: string[]; names: Record<string, string> }> {
  const byName = new Map(files.map((f) => [f.name, f]));
  const rows: Progress[] = tickets.map((t) => ({
    clipId: t.clip_id,
    filename: t.filename,
    sent: 0,
    total: byName.get(t.filename)?.size ?? 0,
    state: "waiting",
  }));

  const report = () => onProgress([...rows]);
  report();

  const arrived: string[] = [];
  const names: Record<string, string> = {};
  let next = 0;

  async function worker(): Promise<void> {
    for (;;) {
      const index = next++;
      if (index >= tickets.length) return;

      const ticket = tickets[index];
      const file = byName.get(ticket.filename);
      if (!file) {
        rows[index] = { ...rows[index], state: "failed", error: "file not found" };
        report();
        continue;
      }

      rows[index] = { ...rows[index], state: "uploading" };
      report();

      try {
        await uploadOne(ticket, file, (sent) => {
          rows[index] = { ...rows[index], sent };
          report();
        });
        rows[index] = { ...rows[index], state: "done", sent: file.size };
        arrived.push(ticket.clip_id);
        names[ticket.clip_id] = ticket.filename;
      } catch (e) {
        rows[index] = {
          ...rows[index],
          state: "failed",
          error: e instanceof Error ? e.message : "upload failed",
        };
      }
      report();
    }
  }

  await Promise.all(Array.from({ length: Math.min(PARALLEL, tickets.length) }, worker));
  return { arrived, names };
}
