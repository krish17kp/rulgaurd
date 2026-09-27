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

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
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

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body && String(body.detail)) ||
      `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
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

export type Compatibility = "FULLY_SUPPORTED" | "ADAPTER_REQUIRED" | "UNSUPPORTED" | "INVALID_INPUT";

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

export async function inspectDataset(file: File): Promise<DatasetProfileResponse> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type here - the browser sets the multipart boundary itself.
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/dataset/inspect`, { method: "POST", body: form });
  } catch {
    throw new ApiError(0, `Could not reach the prediction service at ${API_BASE_URL}.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body && String(body.detail)) ||
      `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail);
  }
  return body as DatasetProfileResponse;
}
