import { describe, expect, it } from "vitest";
import {
  queueShotDisplayName,
  shotDisplayName,
  supplementarySceneHeading,
} from "@/lib/labels";

describe("workspace labels", () => {
  it("uses the slate name once instead of exposing the internal shot number", () => {
    expect(shotDisplayName(3, "3", "3B", 2)).toBe("Shot B");
    expect(shotDisplayName(1, "1", "A", 2)).toBe("Shot A");
    expect(queueShotDisplayName(3, "3B", 2)).toBe("Shot B");
  });

  it("keeps a production-specific code intact", () => {
    expect(shotDisplayName(12, "12", "12A-PU", 4)).toBe("Shot 12A-PU");
  });

  it("does not render a scene heading that only repeats the scene title", () => {
    expect(supplementarySceneHeading(1, "1", "Scene 1")).toBe("");
    expect(supplementarySceneHeading(1, "1", "Kitchen at night")).toBe(
      "Kitchen at night",
    );
  });
});
