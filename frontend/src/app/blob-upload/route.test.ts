import { afterEach, describe, expect, it, vi } from "vitest";

// handleUpload talks to Vercel's real token-signing API, so stub it - this
// test exists to prove the Origin gate (the bug fixed here), not the Blob
// SDK plumbing beneath it.
vi.mock("@vercel/blob/client", () => ({
  handleUpload: vi.fn(async () => ({ type: "blob.generate-client-token", clientToken: "stub" })),
}));

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
  vi.resetModules();
});

function postRequest(origin: string): Request {
  return new Request("https://example.test/blob-upload", {
    method: "POST",
    headers: { origin, "content-type": "application/json" },
    body: JSON.stringify({ type: "blob.generate-client-token", payload: {} }),
  });
}

describe("POST /blob-upload origin gate", () => {
  it("rejects an origin absent from ALLOWED_ORIGINS and not the deployment's own", async () => {
    process.env.ALLOWED_ORIGINS = "https://rulguard.vercel.app";
    delete process.env.VERCEL_URL;
    delete process.env.VERCEL_BRANCH_URL;
    const { POST } = await import("./route");

    const res = await POST(postRequest("https://evil.example.com"));

    expect(res.status).toBe(403);
  });

  it("accepts a Preview deployment's own unique origin via VERCEL_URL", async () => {
    process.env.ALLOWED_ORIGINS = "https://rulguard.vercel.app";
    process.env.VERCEL_URL = "rulguard-2t9nv9ypc-krishparekh261-9292s-projects.vercel.app";
    const { POST } = await import("./route");

    const res = await POST(
      postRequest("https://rulguard-2t9nv9ypc-krishparekh261-9292s-projects.vercel.app")
    );

    expect(res.status).toBe(200);
  });
});
