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
