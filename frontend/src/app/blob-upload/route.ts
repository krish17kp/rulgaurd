import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";
import { NextResponse } from "next/server";

// Mirrors the backend's own MAX_UPLOAD_BYTES (src/bearing_pdm/api.py) -
// review found the frontend previously allowed up to 256MB while the
// backend caps at 64MB, so every file in between was accepted by Blob,
// then always rejected (413) by the backend without ever being cleaned up.
// Keep these two caps equal.
const MAX_UPLOAD_BYTES = 64 * 1024 * 1024;

// This project has no auth/session system (security.md: "no auth surface")
// and a dataset upload is meant to be usable by anyone who can reach the
// frontend - but with no gate at all, review correctly flagged that this
// route lets anyone on the internet mint tokens to store arbitrary public
// files on this project's Blob quota/bill. An Origin check is the same
// no-credentials-needed mitigation the backend's CORS policy already uses
// (ALLOWED_ORIGINS) - it stops casual/scripted abuse from other sites, not
// a determined attacker spoofing headers; a real rate limit/auth gate is a
// further step this capstone's "no auth surface" scope does not include.
const _ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ?? "http://localhost:3000")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

/**
 * Mints a short-lived client-upload token so the browser can PUT a raw
 * dataset file straight to Vercel Blob storage, never through this (or any)
 * serverless function's ~4.5MB request-body limit. This route itself never
 * sees the file bytes - only the upload metadata.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const origin = request.headers.get("origin");
  if (origin && !_ALLOWED_ORIGINS.includes(origin)) {
    return NextResponse.json({ error: "Origin not allowed." }, { status: 403 });
  }

  const body = (await request.json()) as HandleUploadBody;

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        // Only the raw dataset file types this app's upload page ever
        // sends (frontend/src/app/upload/page.tsx's `accept`), not an
        // arbitrary pathname/extension.
        if (!/\.(csv|txt|tsv|dat)$/i.test(pathname)) {
          throw new Error("Only .csv/.txt/.tsv/.dat dataset uploads are allowed.");
        }
        return {
          allowedContentTypes: ["text/csv", "text/plain", "application/octet-stream"],
          maximumSizeInBytes: MAX_UPLOAD_BYTES,
          addRandomSuffix: true,
          tokenPayload: JSON.stringify({ pathname }),
        };
      },
      // Runs server-side once the browser finishes the PUT to Blob storage.
      // No processing happens here - the frontend calls the FastAPI
      // */blob endpoints itself once it has the resulting URL, so cleanup
      // and feature extraction stay in one place (api.py), not duplicated.
      onUploadCompleted: async () => {},
    });
    return NextResponse.json(jsonResponse);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Upload token request failed" },
      { status: 400 }
    );
  }
}
