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
    throw new BlobUploadError(err instanceof Error ? err.message : "Upload to storage failed");
  }
}
