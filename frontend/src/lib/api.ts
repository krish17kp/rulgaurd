/**
 * Typed client for the read-only inference service (src/bearing_pdm/api.py).
 * NEXT_PUBLIC_API_BASE_URL must point at a running instance of that service -
 * see backend README. No prediction value is ever computed in the browser;
 * this file only shapes and forwards requests/responses.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  // The backend's own retryable bool (src/bearing_pdm/api.py's ApiError/
  // _error_content): true only when the same request could succeed later
  // unchanged (a transient 503, a network error). Defaults to true so a
  // caller that doesn't pass it (or a body without the field, e.g. a non-API
  // 500) keeps today's "always offer Retry" behaviour rather than silently
  // hiding it.
  retryable: boolean;
  // Stable UPPER_SNAKE code from the same error body (api.py's _error_content).
  // Used to distinguish a real failure from an intentional policy outcome
  // like APPLICABILITY_LOW, rather than pattern-matching the human-readable detail text.
  code?: string;

  constructor(status: number, detail: string, retryable = true, code?: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.retryable = retryable;
    this.code = code;
  }
}

export interface HealthResponse {
  status: string;
  models_loaded: Record<string, boolean>;
}

export interface ModelsInfoResponse {
  selected_model: { selected: string; reason: string } | null;
  extra_trees_feature_columns: string[] | null;
  hi_feature_columns: string[] | null;
  supported_datasets: string[];
  note: string;
}

export interface HiRequest {
  dataset_id: string;
  rows: Array<{ sequence_index: number } & Record<string, number>>;
}

export interface HiRow {
  sequence_index: number;
  health_indicator: number;
  stage: "HEALTHY" | "DEGRADING" | "CRITICAL";
}

export interface HiResponse {
  rows: HiRow[];
  hi_warn_threshold: number;
  hi_critical_threshold: number;
  note: string;
}

export function predictHi(payload: HiRequest): Promise<HiResponse> {
  return request<HiResponse>("/predict/hi", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ModelMetrics {
  mae_seconds: number;
  rmse_seconds: number;
  median_abs_error_seconds: number;
  n: number;
}

export interface EvaluationResponse {
  femto_lobo_mean_mae_by_model: Record<string, number>;
  femto_lobo_overall_by_model: Record<string, ModelMetrics>;
  femto_lobo: Array<ModelMetrics & { model: string; held_out_bearing: string }>;
  college_mean_mae_by_model?: Record<string, number>;
  college_naive_caveat: string;
}

export function getModelEvaluation(): Promise<EvaluationResponse> {
  return request<EvaluationResponse>("/models/evaluation");
}

export interface PredictRulRequest {
  dataset_id: string;
  features: Record<string, number>;
}

export interface PredictRulResponse {
  model_name: string;
  rul_seconds: number;
  rul_hours: number;
  features_used: string[];
  features_missing: string[];
  /** Real model-domain compatibility (applicability.py), not just a
   * sampling-rate/structural check - see docs/dataset-compatibility.md. */
  compatibility: Compatibility;
  applicability_level: "HIGH" | "MEDIUM" | "LOW" | null;
  applicability_shift_ratio: number | null;
  applicability_reasons: string[];
}

/** FastAPI/Pydantic 422s put `detail` as a list of error objects, not a
 * string - `String(detail)` on that renders "[object Object]". Render
 * something readable either way. */
function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : JSON.stringify(d)))
      .join("; ");
  }
  return JSON.stringify(detail);
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const detail =
    body && typeof body === "object" && "detail" in body
      ? formatDetail((body as { detail: unknown }).detail)
      : `Request failed with status ${response.status}`;
  const retryable =
    body && typeof body === "object" && "retryable" in body
      ? Boolean((body as { retryable: unknown }).retryable)
      : true;
  const code =
    body && typeof body === "object" && "code" in body
      ? String((body as { code: unknown }).code)
      : undefined;
  return new ApiError(response.status, detail, retryable, code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, `Could not reach the prediction service at ${API_BASE_URL}.`);
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as T;
}

export interface ExplainCitation {
  chunk_id: string;
  document_title: string;
  source: string;
  relevance_score: number;
}

export interface ExplainResponse {
  explanation: string;
  citations: ExplainCitation[];
  /** "complete" | "insufficient_evidence" - the deterministic fallback's own
   * reported status (src/bearing_pdm/rag/explain.py), not an HTTP status. */
  status: string;
  provider: string;
  fallback_used: boolean;
}

/** M7 explanation layer (docs/rag.md) - never computes or alters RUL/HI/
 * stage/applicability; only explains a result already produced above. */
export async function explainPrediction(
  context: Partial<PredictRulResponse> & { health_indicator?: number | null; degradation_stage?: string | null },
  question: string
): Promise<ExplainResponse> {
  return request<ExplainResponse>("/explain", {
    method: "POST",
    body: JSON.stringify({ context, question }),
  });
}

/** Shared by the two multipart-upload endpoints below - same
 * network-failure/non-2xx handling as `request`, but with a `FormData` body
 * and no JSON Content-Type header (the browser sets the multipart boundary
 * itself). */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: form });
  } catch {
    throw new ApiError(0, `Could not reach the prediction service at ${API_BASE_URL}.`);
  }
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getModelsInfo(): Promise<ModelsInfoResponse> {
  return request<ModelsInfoResponse>("/models/info");
}

export function predictRul(payload: PredictRulRequest): Promise<PredictRulResponse> {
  return request<PredictRulResponse>("/predict/rul", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Raw FEMTO acc_*.csv -> features.py -> RUL, in one call. The caller is
 * explicitly asserting "this is a FEMTO acquisition" by using this function
 * at all (see src/bearing_pdm/api.py's /predict/rul/femto-acquisition) -
 * this is never inferred from an arbitrary upload's contents.
 */
export async function predictRulFromFemtoAcquisition(file: File): Promise<PredictRulResponse> {
  const form = new FormData();
  form.append("file", file);
  return requestForm<PredictRulResponse>("/predict/rul/femto-acquisition", form);
}

/**
 * Direct-to-storage counterpart of predictRulFromFemtoAcquisition: `blobUrl`
 * is an object this app's own client upload (lib/blobUpload.ts) just wrote
 * to Vercel Blob - the backend downloads it itself, in bounded chunks, and
 * deletes it once processed (src/bearing_pdm/api.py's
 * predict_rul_from_femto_acquisition_blob).
 */
export function predictRulFromFemtoAcquisitionBlob(blobUrl: string): Promise<PredictRulResponse> {
  return request<PredictRulResponse>("/predict/rul/femto-acquisition/blob", {
    method: "POST",
    body: JSON.stringify({ blob_url: blobUrl }),
  });
}

export interface FemtoSignalChannel {
  waveform: number[];
  fft_frequency_hz: number[];
  fft_magnitude: number[];
}

export interface FemtoSignalResponse {
  sample_rate_hz: number;
  samples: number;
  vibration_x: FemtoSignalChannel;
  vibration_y: FemtoSignalChannel;
  features: Record<string, number>;
}

/** Raw waveform/FFT/feature values for the Signal & FFT / Features UI tabs -
 * same FEMTO acc_*.csv upload as predictRulFromFemtoAcquisition, visualization
 * only (src/bearing_pdm/api.py's /analyze/femto-signal). */
export async function analyzeFemtoSignal(file: File): Promise<FemtoSignalResponse> {
  const form = new FormData();
  form.append("file", file);
  return requestForm<FemtoSignalResponse>("/analyze/femto-signal", form);
}

export type Compatibility =
  | "FULLY_SUPPORTED"
  | "ADAPTER_REQUIRED"
  | "RETRAIN_REQUIRED"
  | "UNSUPPORTED"
  | "INVALID_INPUT";

export interface DatasetColumnProfile {
  name: string;
  canonical: string | null;
  confidence: "high" | "low" | "unmapped";
  numeric: boolean;
  nan_fraction: number;
  constant: boolean;
}

export interface DatasetProfileResponse {
  compatibility: Compatibility;
  reasons: string[];
  profile: {
    file: string;
    readable: boolean;
    has_header?: boolean;
    n_columns?: number;
    rows?: number;
    rows_exact?: boolean;
    warnings: string[];
    columns?: DatasetColumnProfile[];
  };
}

export interface InspectDatasetOptions {
  /** The caller's own assertion - used only when the file has no regular
   * timestamps in seconds to derive a rate from. Never guessed by the backend. */
  declaredSamplingRateHz?: number;
  declaredUnits?: string;
}

export async function inspectDataset(
  file: File,
  options?: InspectDatasetOptions
): Promise<DatasetProfileResponse> {
  const form = new FormData();
  form.append("file", file);
  if (options?.declaredSamplingRateHz !== undefined) {
    form.append("declared_sampling_rate_hz", String(options.declaredSamplingRateHz));
  }
  if (options?.declaredUnits) {
    form.append("declared_units", options.declaredUnits);
  }
  return requestForm<DatasetProfileResponse>("/dataset/inspect", form);
}

/** Direct-to-storage counterpart of inspectDataset - see
 * predictRulFromFemtoAcquisitionBlob's note above. */
export function inspectDatasetBlob(
  blobUrl: string,
  options?: InspectDatasetOptions
): Promise<DatasetProfileResponse> {
  return request<DatasetProfileResponse>("/dataset/inspect/blob", {
    method: "POST",
    body: JSON.stringify({
      blob_url: blobUrl,
      declared_sampling_rate_hz: options?.declaredSamplingRateHz,
      declared_units: options?.declaredUnits,
    }),
  });
}
