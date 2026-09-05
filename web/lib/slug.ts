/**
 * Readable project URLs that survive a rename.
 *
 * `/project/6?scene=1&shot=1` tells you nothing about which production you are
 * looking at, and a URL built from the name alone — `/shortfilm/kill-bill` —
 * breaks the moment somebody renames it. Project names are not unique either;
 * nothing stops two productions being called Kill Bill.
 *
 * So the name is decoration and the id is identity: `kill-bill-6`. The trailing
 * number is what resolves, the words in front are for the person reading the
 * address bar, and a renamed project still opens from every link ever shared.
 *
 * The id cannot be replaced by the slug. It is the ClickHouse partition and
 * sort key — see `services/projects.py` — so it stays an integer whatever the
 * URL says.
 */

/** `Kill Bill` + 6 → `kill-bill-6`. */
export function projectSlug(name: string, projectId: number): string {
  const words = name
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    // Long enough to recognise, short enough to read in a browser tab.
    .slice(0, 48)
    .replace(/-+$/, "");
  return words ? `${words}-${projectId}` : String(projectId);
}

/**
 * The id out of a slug, or 0.
 *
 * Reads the trailing number and ignores the words entirely, so a stale slug
 * from before a rename still resolves. A bare `6` works too, which is what
 * keeps every link written before this scheme existed alive.
 */
export function projectIdFromSlug(slug: string): number {
  const match = /(?:^|-)(\d+)$/.exec(slug ?? "");
  return match ? Number(match[1]) : 0;
}

/**
 * The canonical paths.
 *
 * The name is optional throughout. Several screens hold an id and no name —
 * an activity row, a queue entry — and a bare `/projects/6` resolves perfectly
 * well because only the trailing number is read. Passing the name when it is
 * to hand simply makes the address readable.
 */
const base = (id: number, name?: string) =>
  `/projects/${name ? projectSlug(name, id) : id}`;

export const paths = {
  project: (id: number, name?: string) => base(id, name),
  scene: (id: number, scene: number, name?: string) => `${base(id, name)}/scenes/${scene}`,
  shot: (id: number, scene: number, shot: number, name?: string) =>
    `${base(id, name)}/scenes/${scene}/shots/${shot}`,
  coverage: (id: number, scene: number, name?: string) =>
    `${base(id, name)}/scenes/${scene}/coverage`,
  ingest: (id: number, name?: string) => `${base(id, name)}/ingest`,
};
