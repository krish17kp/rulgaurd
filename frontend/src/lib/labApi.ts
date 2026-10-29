/**
 * Client for the research-lab routes (src/bearing_pdm/lab_api.py): the features that used to
 * live only in the Streamlit dashboard. Read-only; nothing is computed in the browser.
 */
import { AnalysisBundleResponse, ApiError, FemtoSignalResponse } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/lab${path}`, init);
  } catch {
    throw new ApiError(0, `Could not reach the analysis service at ${API_BASE_URL}.`);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `Request failed with status ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface SignalSource {
  source: "femto_raw" | "snapshot";
  dataset_id: string;
  bearing_run_id: string;
  label: string;
  sequence_indices: number[];
  acquisition_count: number;
}

export const listSignals = () => call<SignalSource[]>("/signals");
export const getFemtoSignal = (bearing: string, index: number) =>
  call<FemtoSignalResponse>(`/signals/femto?bearing=${encodeURIComponent(bearing)}&index=${index}`);
export const getSnapshotSignal = (bearing: string, sequenceIndex: number) =>
  call<FemtoSignalResponse>(
    `/signals/snapshot?bearing=${encodeURIComponent(bearing)}&sequence_index=${sequenceIndex}`,
  );

export const listRoutingResults = () => call<string[]>("/routing");
export const getRoutingResult = (datasetId: string) =>
  call<AnalysisBundleResponse>(`/routing/${encodeURIComponent(datasetId)}`);

export interface Applicability {
  level: "HIGH" | "MEDIUM" | "LOW";
  shift_ratio: number;
  reasons: string[];
}

export interface FaultSnapshot {
  dataset_id: string;
  file_id: string;
  label: string;
  sample_rate_hz: number;
  signal: { waveform: number[]; fft_frequency_hz: number[]; fft_magnitude: number[] };
  features: Record<string, number>;
  applicability: Applicability | null;
  note: string;
}

export const getExperimentFixtures = () =>
  call<{ cwru: Record<string, string>; paderborn: Record<string, string> }>("/experiment/fixtures");
export const getExperimentSnapshot = (datasetId: string, fileId: string) =>
  call<FaultSnapshot>(`/experiment/${datasetId}/${encodeURIComponent(fileId)}`);

export interface SyntheticConfig {
  seed: number;
  n_acquisitions: number;
  samples_per_acquisition: number;
  sample_rate_hz: number;
  shaft_freq_hz: number;
  baseline_noise_std: number;
}

export interface SyntheticResult {
  first_acquisition: number[];
  rms: number[];
  kurtosis: number[];
  applicability: Applicability | null;
  rul_status: string | null;
  note: string;
}

export const runSynthetic = (cfg: SyntheticConfig) => call<SyntheticResult>("/synthetic", json(cfg));

export async function downloadSyntheticZip(cfg: SyntheticConfig): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/lab/synthetic/zip`, json(cfg));
  if (!response.ok) throw new ApiError(response.status, "Could not build the synthetic ZIP.");
  return response.blob();
}

export interface KnowledgeSearchResult {
  index: "built-in" | "uploaded";
  documents: number;
  chunks: number;
  files: Array<{ file: string; status: string; chunks: number; reason: string }>;
  hits: Array<{ source: string; page: number | null; chunk_id: string; score: number; text: string }>;
}

export function searchKnowledge(query: string, files: File[]): Promise<KnowledgeSearchResult> {
  const form = new FormData();
  form.append("query", query);
  files.forEach((f) => form.append("files", f));
  return call<KnowledgeSearchResult>("/knowledge/search", { method: "POST", body: form });
}
