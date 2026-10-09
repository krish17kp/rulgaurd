import { upload } from "@vercel/blob/client";

/**
 * Files at or above this size would exceed Vercel's ~4.5MB serverless
 * request-body limit as ordinary multipart form data - everything at or
 * above it goes straight to Blob storage from the browser instead (see
 * docs on functions/limitations#request-body-size). Kept well under the
 * real limit as a margin for multipart overhead.
 */
export const DIRECT_UPLOAD_THRESHOLD_BYTES = 4 * 1024 * 1024;

export class BlobUploadError extends Error {}

/**
 * Uploads `file` straight to Vercel Blob storage from the browser and
 * returns the resulting object URL. Never buffers the file through this
 * app's own API routes or the FastAPI backend.
 */
export async function uploadFileToBlob(
  file: File,
  onProgress?: (fraction: number) => void
): Promise<string> {
  try {
    const result = await upload(file.name, file, {
      access: "public",
      // Deliberately NOT under /api/ - vercel.json rewrites /api/(.*) to the
      // Python function, which has no such route; this would 404 in
      // production despite working in local dev (review flagged this).
      handleUploadUrl: "/blob-upload",
      onUploadProgress: (event) => onProgress?.(event.percentage / 100),
    });
    return result.url;
  } catch (err) {
    // The @vercel/blob SDK's own error text ("Vercel Blob: Failed to
    // retrieve the client token") is an infrastructure detail, not
    // something a visitor can act on - log it for debugging and show a
    // plain, retryable message instead (found live: this exact string was
    // shown directly to a user).
    if (err instanceof Error) console.error("Blob upload failed:", err.message);
    throw new BlobUploadError("Upload could not start. Please try again.");
  }
}
