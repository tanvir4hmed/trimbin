import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

/**
 * Frontend logic runs in tests, rather than being read as text.
 *
 * The regressions these cover were pinned from Python by grepping the .tsx
 * files for a phrase. That passes whenever the phrase is present and fails
 * whenever somebody renames a variable — it proves the source contains a
 * string, not that the rule holds. These functions are pure, so they can
 * simply be called.
 */
export default defineConfig({
  resolve: { alias: { "@": resolve(__dirname, ".") } },
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
