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
  state: "waiting" | "uploading" | "paused" | "done" | "failed" | "cancelled";
  error?: string;
}

export interface UploadSnapshot {
  id: string;
  rows: Progress[];
  state:
    "uploading" | "paused" | "interrupted" | "done" | "cancelled" | "failed";
  updatedAt: number;
}

type Listener = () => void;
const snapshots = new Map<string, UploadSnapshot>();
let snapshotList: UploadSnapshot[] = [];
const listeners = new Set<Listener>();
const controls = new Map<string, UploadControl>();

if (typeof window !== "undefined")
  window.addEventListener("trimbin:upload-clear", () => {
    controls.forEach((control) => control.cancel());
    controls.clear();
    snapshots.clear();
    snapshotList = [];
    restored = false;
    listeners.forEach((listener) => listener());
  });

function publish(
  id: string,
  rows: Progress[],
  state?: UploadSnapshot["state"],
) {
  const previous = snapshots.get(id);
  snapshots.set(id, {
    id,
    rows: [...rows],
    state: state ?? previous?.state ?? "uploading",
    updatedAt: Date.now(),
  });
  snapshotList = Array.from(snapshots.values()).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
  try {
    window.localStorage.setItem(
      `trimbin.upload.snapshot.${id}`,
      JSON.stringify(snapshots.get(id)),
    );
  } catch {
    /* progress still works when storage is unavailable */
  }
  listeners.forEach((listener) => listener());
}

let restored = false;
export function restoreUploadSnapshots(): void {
  if (restored || typeof window === "undefined") return;
  restored = true;
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key?.startsWith("trimbin.upload.snapshot.")) continue;
    try {
      const value = JSON.parse(
        window.localStorage.getItem(key) || "",
      ) as UploadSnapshot;
      if (!value?.id || !Array.isArray(value.rows)) continue;
      if (value.state === "uploading" || value.state === "paused")
        value.state = "interrupted";
      snapshots.set(value.id, value);
    } catch {
      window.localStorage.removeItem(key);
    }
  }
  snapshotList = Array.from(snapshots.values()).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
  listeners.forEach((listener) => listener());
}

export function uploadSnapshots(): UploadSnapshot[] {
  return snapshotList;
}
export function subscribeUploads(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function pauseUpload(id: string) {
  controls.get(id)?.pause();
}
export function resumeUpload(id: string) {
  controls.get(id)?.resume();
}
export function cancelUpload(id: string) {
  controls.get(id)?.cancel();
}
export function dismissUpload(id: string) {
  snapshots.delete(id);
  try {
    window.localStorage.removeItem(`trimbin.upload.snapshot.${id}`);
  } catch {}
  snapshotList = Array.from(snapshots.values()).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
  listeners.forEach((listener) => listener());
}

class UploadControl {
  paused = false;
  cancelled = false;
  controller = new AbortController();
  private wake: (() => void)[] = [];
  constructor(readonly id: string) {}
  pause() {
    if (this.cancelled) return;
    this.paused = true;
    this.controller.abort();
    const snap = snapshots.get(this.id);
    if (snap)
      publish(
        this.id,
        snap.rows.map((r) =>
          r.state === "uploading" ? { ...r, state: "paused" } : r,
        ),
        "paused",
      );
  }
  resume() {
    if (!this.paused || this.cancelled) return;
    this.paused = false;
    this.controller = new AbortController();
    this.wake.splice(0).forEach((fn) => fn());
    const snap = snapshots.get(this.id);
    if (snap) publish(this.id, snap.rows, "uploading");
  }
  cancel() {
    this.cancelled = true;
    this.paused = false;
    this.controller.abort();
    this.wake.splice(0).forEach((fn) => fn());
    const snap = snapshots.get(this.id);
    if (snap)
      publish(
        this.id,
        snap.rows.map((r) =>
          r.state === "done" ? r : { ...r, state: "cancelled" },
        ),
        "cancelled",
      );
  }
  async ready() {
    if (this.cancelled)
      throw new DOMException("Upload cancelled", "AbortError");
    if (this.paused)
      await new Promise<void>((resolve) => this.wake.push(resolve));
    if (this.cancelled)
      throw new DOMException("Upload cancelled", "AbortError");
  }
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

const sessionUris = new Map<string, string>();

function sessionKey(clipId: string) {
  return `trimbin.upload.session.${clipId}`;
}

function remember(clipId: string, uri: string): void {
  sessionUris.set(clipId, uri);
  window.localStorage.setItem(sessionKey(clipId), uri);
}

function forget(clipId: string): void {
  sessionUris.delete(clipId);
  window.localStorage.removeItem(sessionKey(clipId));
}

/** Open a resumable session, or reuse the one this file already has. */
const RETRIES = 4;

async function retry<T>(
  operation: () => Promise<T>,
  control: UploadControl,
): Promise<T> {
  let last: unknown;
  for (let attempt = 0; attempt < RETRIES; attempt += 1) {
    await control.ready();
    try {
      return await operation();
    } catch (error) {
      if (
        control.cancelled ||
        (error instanceof DOMException && error.name === "AbortError")
      )
        throw error;
      last = error;
      await new Promise((resolve) =>
        window.setTimeout(resolve, 400 * 2 ** attempt),
      );
    }
  }
  throw last instanceof Error ? last : new Error("upload failed after retries");
}

async function openSession(
  ticket: Ticket,
  control: UploadControl,
): Promise<string> {
  const existing =
    sessionUris.get(ticket.clip_id) ??
    window.localStorage.getItem(sessionKey(ticket.clip_id));
  if (existing) return existing;

  const response = await retry(
    () =>
      fetch(ticket.upload_url, {
        method: "POST",
        headers: ticket.headers,
        signal: control.controller.signal,
      }),
    control,
  );
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
async function bytesReceived(
  session: string,
  total: number,
  control: UploadControl,
): Promise<number> {
  const probe = await retry(
    () =>
      fetch(session, {
        method: "PUT",
        headers: { "Content-Range": `bytes */${total}` },
        signal: control.controller.signal,
      }),
    control,
  );

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
  control: UploadControl,
): Promise<void> {
  const session = await openSession(ticket, control);
  let offset = await bytesReceived(session, file.size, control);
  onProgress(offset);

  while (offset < file.size) {
    await control.ready();
    const end = Math.min(offset + CHUNK, file.size);
    let response: Response;
    try {
      response = await retry(async () => {
        const sent = await fetch(session, {
          method: "PUT",
          headers: {
            "Content-Range": `bytes ${offset}-${end - 1}/${file.size}`,
          },
          body: file.slice(offset, end),
          signal: control.controller.signal,
        });
        if (sent.status === 408 || sent.status === 429 || sent.status >= 500)
          throw new Error(`storage temporarily unavailable (${sent.status})`);
        return sent;
      }, control);
    } catch (error) {
      if (control.paused && !control.cancelled) {
        await control.ready();
        offset = await bytesReceived(session, file.size, control);
        onProgress(offset);
        continue;
      }
      try {
        offset = await bytesReceived(session, file.size, control);
        onProgress(offset);
        continue;
      } catch {
        /* report the original failure */
      }
      throw error;
    }

    if (response.status === 200 || response.status === 201) {
      offset = file.size;
      break;
    }
    if (response.status !== 308) {
      const reconciled = await bytesReceived(session, file.size, control);
      if (reconciled > offset) {
        offset = reconciled;
        onProgress(offset);
        continue;
      }
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
  batchId = crypto.randomUUID(),
): Promise<{
  arrived: string[];
  names: Record<string, string>;
  cancelled: boolean;
}> {
  // Camera cards can contain the same basename in different folders. Keep
  // every occurrence and pair them with same-named tickets in selection order;
  // a Map<string, File> silently uploaded the first file twice.
  const byName = new Map<string, File[]>();
  for (const file of files)
    byName.set(file.name, [...(byName.get(file.name) ?? []), file]);
  const fileForTicket = new Map<string, File>();
  for (const ticket of tickets) {
    const candidates = byName.get(ticket.filename) ?? [];
    const file = candidates.shift();
    if (file) fileForTicket.set(ticket.clip_id, file);
  }
  const rows: Progress[] = tickets.map((t) => ({
    clipId: t.clip_id,
    filename: t.filename,
    sent: 0,
    total: fileForTicket.get(t.clip_id)?.size ?? 0,
    state: "waiting",
  }));

  const control = new UploadControl(batchId);
  controls.set(batchId, control);
  const report = () => {
    onProgress([...rows]);
    publish(batchId, rows);
  };
  report();

  const arrived: string[] = [];
  const names: Record<string, string> = {};
  let next = 0;

  async function worker(): Promise<void> {
    for (;;) {
      const index = next++;
      if (index >= tickets.length) return;

      const ticket = tickets[index];
      const file = fileForTicket.get(ticket.clip_id);
      if (!file) {
        rows[index] = {
          ...rows[index],
          state: "failed",
          error: "file not found",
        };
        report();
        continue;
      }

      rows[index] = { ...rows[index], state: "uploading" };
      report();

      try {
        await uploadOne(
          ticket,
          file,
          (sent) => {
            rows[index] = { ...rows[index], sent };
            report();
          },
          control,
        );
        rows[index] = { ...rows[index], state: "done", sent: file.size };
        arrived.push(ticket.clip_id);
        names[ticket.clip_id] = ticket.filename;
      } catch (e) {
        rows[index] = {
          ...rows[index],
          state: control.cancelled ? "cancelled" : "failed",
          error: e instanceof Error ? e.message : "upload failed",
        };
      }
      report();
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(PARALLEL, tickets.length) }, worker),
  );
  publish(
    batchId,
    rows,
    control.cancelled
      ? "cancelled"
      : rows.some((row) => row.state === "failed")
        ? "failed"
        : "done",
  );
  controls.delete(batchId);
  return { arrived, names, cancelled: control.cancelled };
}
