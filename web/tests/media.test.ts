import { describe, expect, it } from "vitest";
import { verifyUploadPrefix, type MediaUpload } from "../lib/media";

async function hash(text: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

describe("resumable original upload", () => {
  it("verifies previously received bytes before appending a reselected file", async () => {
    const session: MediaUpload = { id: "session", filename: "take.mov", expected_bytes: 6,
      received_bytes: 3, chunk_bytes: 3, chunk_hashes: [await hash("abc")] };
    await expect(verifyUploadPrefix(new File(["abcdef"], "take.mov"), session)).resolves.toBeUndefined();
    await expect(verifyUploadPrefix(new File(["xyzdef"], "take.mov"), session)).rejects.toThrow("differs");
    await expect(verifyUploadPrefix(new File(["abcdefg"], "take.mov"), session)).rejects.toThrow("same original");
  });
});
