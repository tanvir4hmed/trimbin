/** Human-facing scene and shot names, without leaking internal row numbers. */

function clean(value: string | undefined): string {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

/** A heading such as "Scene 1" adds no information below the scene title. */
export function supplementarySceneHeading(
  scene: number,
  sceneCode: string,
  heading: string | undefined,
): string {
  const value = clean(heading);
  const title = `Scene ${clean(sceneCode) || scene}`;
  return value.toLowerCase() === title.toLowerCase() ? "" : value;
}

/**
 * Keep a slate code readable inside its scene: `3B` becomes `Shot B`, while
 * a production-specific code such as `12A-PU` remains intact.
 */
export function shotDisplayName(
  scene: number,
  sceneCode: string,
  slug: string | undefined,
  shot: number,
): string {
  const raw = clean(slug);
  if (!raw) return `Shot ${shot}`;

  const withoutPrefix = raw.replace(/^shot\s+/i, "");
  const code = clean(sceneCode) || String(scene);
  const suffix = withoutPrefix.match(
    new RegExp(`^${code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([A-Za-z]+)$`, "i"),
  )?.[1];
  return `Shot ${suffix || withoutPrefix}`;
}

/** Queue rows carry the numeric scene but not its production-facing code. */
export function queueShotDisplayName(
  scene: number,
  slug: string | undefined,
  shot: number,
): string {
  return shotDisplayName(scene, String(scene), slug, shot);
}
