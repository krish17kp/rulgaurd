/**
 * Cheap client-side check of whether a selected file could plausibly be a
 * FEMTO acc_*.csv acquisition, before any byte of it is uploaded anywhere.
 *
 * Mirrors the backend's own authoritative shape check (femto.py's
 * ACC_COLUMNS: hour, minute, second, microsecond, accel_horizontal,
 * accel_vertical - a fixed, headerless, 6-column numeric layout). This is
 * not a full validator - the backend still does that - it only avoids
 * uploading an obviously-wrong file (e.g. a hundred-MB college LogFile,
 * which uses a different 4-column layout) just to get the same rejection
 * back after the round trip.
 */
const FEMTO_COLUMN_COUNT = 6;

// Comfortably covers one CSV line at FEMTO's widest realistic field widths;
// reading this prefix never touches the rest of the file, however large.
const SNIFF_PREFIX_BYTES = 4096;

export async function looksLikeFemtoAcquisition(file: File): Promise<boolean> {
  const prefix = await file.slice(0, SNIFF_PREFIX_BYTES).text();
  const firstLine = prefix.split(/\r?\n/).find((line) => line.trim().length > 0);
  if (!firstLine) return false;

  const fields = firstLine.split(",").map((f) => f.trim());
  if (fields.length !== FEMTO_COLUMN_COUNT) return false;
  return fields.every((f) => f !== "" && Number.isFinite(Number(f)));
}

/**
 * Filename-only archive detection, checked BEFORE any FEMTO/MAT routing so a
 * RAR/7z/TAR upload never reaches `looksLikeFemtoAcquisition` or the FEMTO
 * predictor and gets misreported as "Dataset not recognized for RUL
 * prediction" (that message is about CONTENT shape, not about an unsupported
 * container format - a materially different, and misleading, failure mode).
 *
 * `.rulguard.zip` is RULGuard's own portable Analysis Bundle format (see
 * bearing_pdm.analysis_bundle) and is NOT a plain archive the cloud can't
 * read - it routes to /analyze-bundle, not to offline-mode guidance. It is
 * checked first since it also ends in ".zip".
 *
 * This cloud upload page intentionally never attempts server-side RAR/7z/TAR
 * extraction (that belongs in Offline Research Mode,
 * src/bearing_pdm/rar_archive.py) - this is filename routing only, never a
 * parser.
 */
export type ArchiveKind = "rulguard_bundle" | "multipart_rar" | "rar" | "7z" | "tar";

const MULTIPART_RAR_RE = /\.part\d+\.rar$/i;

export function detectArchiveKind(filename: string): ArchiveKind | null {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".rulguard.zip")) return "rulguard_bundle";
  if (MULTIPART_RAR_RE.test(lower)) return "multipart_rar";
  if (lower.endsWith(".rar")) return "rar";
  if (lower.endsWith(".7z")) return "7z";
  if (lower.endsWith(".tar") || lower.endsWith(".tar.gz") || lower.endsWith(".tgz")) return "tar";
  return null;
}

/**
 * Files the whole-dataset job workflow (src/bearing_pdm/dataset_jobs.py)
 * takes: a ZIP / 7Z / RAR archive or one part of a multi-part `.partNN.rar`
 * or `.7z.NNN` set. Never `.rulguard.zip` (an Analysis Bundle, routed to
 * /analyze-bundle). Filename routing only; the server checks the contents.
 */
export function isDatasetArchive(filename: string): boolean {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".rulguard.zip")) return false;
  return /\.(zip|7z|rar)$/.test(lower) || /\.7z\.\d{3}$/.test(lower);
}
