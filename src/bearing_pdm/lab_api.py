"""Research-lab features as API routes, so the public site can show them as its own pages.

Each route is a thin wrapper over what the Streamlit lab (dashboard.py, dashboard_cross.py)
already calls: the deployment snapshot, the FEMTO raw files, the routing results, the
CWRU/Paderborn readers, the synthetic generator and the RAG index. Nothing is fit, retrained
or written to shared state here; every route only reads.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from bearing_pdm import api as core

router = APIRouter(prefix="/lab", tags=["lab"])

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = ROOT / "deploy_data"
METRICS = ROOT / "reports" / "metrics"
FEMTO_LEARNING = ROOT / "data" / "interim" / "femto" / "Learning_set"
FIXTURES = ROOT / "data" / "fixtures"
MAX_POINTS = 4000  # waveform/FFT points sent to the browser per channel

CWRU_FIXTURES = {
    "97": "normal baseline",
    "105": "inner race fault 0.007in",
    "118": "ball fault 0.007in",
    "130": "outer race fault 0.007in @6:00",
}
PADERBORN_FIXTURES = {
    "N15_M07_F10_K001_1": "healthy (K001)",
    "N15_M07_F10_KA01_1": "artificial outer-race fault (KA01)",
}


def _thin(values: np.ndarray) -> list[float]:
    step = max(1, len(values) // MAX_POINTS)
    return [float(v) for v in values[::step]]


def _channel(signal: np.ndarray, sample_rate_hz: float, demean: bool = False) -> core.FemtoSignalChannel:
    signal = signal[~np.isnan(signal)]
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate_hz)
    magnitude = np.abs(np.fft.rfft(signal - signal.mean() if demean else signal))
    return core.FemtoSignalChannel(
        waveform=_thin(signal), fft_frequency_hz=_thin(freqs), fft_magnitude=_thin(magnitude),
    )


# ---------------------------------------------------------------- Signal & FFT

class SignalSource(BaseModel):
    source: str
    dataset_id: str
    bearing_run_id: str
    label: str
    sequence_indices: list[int] = Field(default_factory=list)
    acquisition_count: int = 0


@router.get("/signals", response_model=list[SignalSource])
def list_signals() -> list[SignalSource]:
    """Every waveform the site can show: all FEMTO learning acquisitions on the server,
    plus the measured windows bundled in the deployment snapshot (the only college ones)."""
    from bearing_pdm.femto import discover_femto_bearings, list_acquisition_indices

    out: list[SignalSource] = []
    if FEMTO_LEARNING.is_dir():
        for b in discover_femto_bearings(FEMTO_LEARNING, "learning"):
            out.append(SignalSource(
                source="femto_raw", dataset_id="femto", bearing_run_id=f"femto:{b.bearing_label}",
                label=f"FEMTO {b.bearing_label} (every acquisition)",
                acquisition_count=len(list_acquisition_indices(b.path)),
            ))
    snap_path = DEPLOY_DIR / "raw_signal_samples.parquet"
    if snap_path.is_file():
        snap = pd.read_parquet(snap_path, columns=["dataset_id", "bearing_run_id", "sequence_index"])
        for (dataset_id, bearing), g in snap.groupby(["dataset_id", "bearing_run_id"]):
            if dataset_id == "femto" and FEMTO_LEARNING.is_dir():
                continue  # the raw set above already has every acquisition of these bearings
            out.append(SignalSource(
                source="snapshot", dataset_id=dataset_id, bearing_run_id=bearing,
                label=f"{bearing} (bundled windows)",
                sequence_indices=sorted(int(s) for s in g["sequence_index"]),
            ))
    return out


@router.get("/signals/femto", response_model=core.FemtoSignalResponse)
def femto_signal(bearing: str, index: int) -> core.FemtoSignalResponse:
    """One FEMTO learning acquisition, through the same reader the upload endpoint uses."""
    if not re.fullmatch(r"Bearing\d_\d", bearing):
        raise HTTPException(status_code=400, detail="bearing must look like Bearing1_1")
    path = FEMTO_LEARNING / bearing / f"acc_{index:05d}.csv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{bearing} has no acquisition {index}")
    return core._femto_signal_view(str(path))


@router.get("/signals/snapshot", response_model=core.FemtoSignalResponse)
def snapshot_signal(bearing: str, sequence_index: int) -> core.FemtoSignalResponse:
    """A measured window bundled in deploy_data, with its cached feature row."""
    snap = pd.read_parquet(DEPLOY_DIR / "raw_signal_samples.parquet")
    hit = snap[(snap["bearing_run_id"] == bearing) & (snap["sequence_index"] == sequence_index)]
    if hit.empty:
        raise HTTPException(status_code=404, detail=f"no bundled window {bearing} #{sequence_index}")
    row = hit.iloc[0]
    fs = float(row["sample_rate_hz"])
    feats = pd.read_parquet(DEPLOY_DIR / "feature_snapshot.parquet")
    frow = feats[(feats["bearing_run_id"] == bearing) & (feats["sequence_index"] == sequence_index)]
    features = {}
    if not frow.empty:
        features = {
            c: float(v) for c, v in frow.iloc[0].items()
            if (c.startswith("vibration_") or c.startswith("bearing_temp")) and pd.notna(v)
        }
    x = np.asarray(row["vibration_x"], dtype=float)
    return core.FemtoSignalResponse(
        sample_rate_hz=fs, samples=int(x.size),
        vibration_x=_channel(x, fs), vibration_y=_channel(np.asarray(row["vibration_y"], dtype=float), fs),
        features=features,
        note=("A measured window bundled with the deployment (deploy_data/raw_signal_samples.parquet); "
              f"waveform and FFT are thinned to at most {MAX_POINTS} points for display. Features are "
              "the pipeline's cached values for this window, not recomputed."),
    )


# ---------------------------------------------------------------- Routing results

@router.get("/routing")
def list_routing() -> list[str]:
    return sorted(p.stem.removeprefix("routing_") for p in METRICS.glob("routing_*.json"))


@router.get("/routing/{dataset_id}", response_model=core.AnalysisBundleResponse)
def routing_result(dataset_id: str) -> core.AnalysisBundleResponse:
    """The offline routing_<dataset>.json, sanitized exactly as build_routing_bundle does,
    in the same response shape /analyze/bundle returns for an uploaded routing bundle."""
    from bearing_pdm.analysis_bundle import _SENSITIVE_PROFILE_KEYS

    if not re.fullmatch(r"[a-z0-9_]+", dataset_id):
        raise HTTPException(status_code=400, detail="invalid dataset id")
    path = METRICS / f"routing_{dataset_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no routing result for {dataset_id}")
    payload = json.loads(path.read_text())
    for key in _SENSITIVE_PROFILE_KEYS:
        payload.pop(key, None)
    return core.AnalysisBundleResponse(
        status="ok", dataset_id=f"{dataset_id}:routing", kind="routing", payload=payload,
    )


# ---------------------------------------------------------------- Experiment lab

class FaultSnapshotResponse(BaseModel):
    dataset_id: str
    file_id: str
    label: str
    sample_rate_hz: float
    signal: core.FemtoSignalChannel
    features: dict[str, float]
    applicability: dict | None
    note: str


@router.get("/experiment/fixtures")
def experiment_fixtures() -> dict[str, dict[str, str]]:
    return {"cwru": CWRU_FIXTURES, "paderborn": PADERBORN_FIXTURES}


@router.get("/experiment/{dataset_id}/{file_id}", response_model=FaultSnapshotResponse)
def experiment_snapshot(dataset_id: str, file_id: str) -> FaultSnapshotResponse:
    """One bundled CWRU/Paderborn recording: waveform (first 0.1 s), FFT, features and
    applicability against the FEMTO model. Never an RUL: these are fault snapshots."""
    if dataset_id == "cwru" and file_id in CWRU_FIXTURES:
        from bearing_pdm.cwru import extract_features, read_channel

        path, fs, label = FIXTURES / "cwru" / f"{file_id}.mat", 12_000.0, CWRU_FIXTURES[file_id]
        signal = read_channel(path, file_id, channel="DE")
        features = extract_features(path, file_id, sample_rate_hz=fs)
    elif dataset_id == "paderborn" and file_id in PADERBORN_FIXTURES:
        from bearing_pdm.paderborn import VIBRATION_SAMPLE_RATE_HZ, extract_features, read_channel

        path, fs, label = FIXTURES / "paderborn" / f"{file_id}.mat", VIBRATION_SAMPLE_RATE_HZ, PADERBORN_FIXTURES[file_id]
        signal = read_channel(path)
        features = extract_features(path)
    else:
        raise HTTPException(status_code=404, detail="unknown recording")
    full = _channel(np.asarray(signal, dtype=float), fs, demean=True)
    head = np.asarray(signal[: int(fs * 0.1)], dtype=float)
    return FaultSnapshotResponse(
        dataset_id=dataset_id, file_id=file_id, label=label, sample_rate_hz=fs,
        signal=core.FemtoSignalChannel(
            waveform=_thin(head), fft_frequency_hz=full.fft_frequency_hz, fft_magnitude=full.fft_magnitude,
        ),
        features={k: float(v) for k, v in features.items() if np.isfinite(v)},
        applicability=core._assess_applicability(features, dataset_id),
        note=("Fixed-condition fault-diagnosis snapshot: there is no degradation trajectory, so no "
              "RUL ground truth exists and none is estimated."),
    )


class SyntheticRequest(BaseModel):
    seed: int = 42
    n_acquisitions: int = Field(10, ge=2, le=200)
    samples_per_acquisition: int = Field(2560, ge=256, le=65536)
    sample_rate_hz: float = Field(25_600.0, gt=0, le=200_000)
    shaft_freq_hz: float = Field(50.0, gt=0, le=1000)
    baseline_noise_std: float = Field(0.05, ge=0, le=10)


class SyntheticResponse(BaseModel):
    first_acquisition: list[float]
    rms: list[float]
    kurtosis: list[float]
    applicability: dict | None
    rul_status: str | None
    note: str


def _synthetic_config(req: SyntheticRequest):
    from bearing_pdm.synthetic import SyntheticConfig

    return SyntheticConfig(**req.model_dump())


@router.post("/synthetic", response_model=SyntheticResponse)
def synthetic(req: SyntheticRequest) -> SyntheticResponse:
    """The Streamlit lab's synthetic simulator: demonstration data, never real-world evidence."""
    from bearing_pdm.applicability import assess as applicability_assess
    from bearing_pdm.features import frequency_domain_features, time_domain_features
    from bearing_pdm.routing import RUL_SUPPRESSED, decide
    from bearing_pdm.synthetic import generate_sequence

    cfg = _synthetic_config(req)
    sequence = generate_sequence(cfg)
    rms = [float(np.sqrt(np.mean(x**2))) for x, _ in sequence]
    kurt = [float(time_domain_features(x, "v")["v_kurtosis"]) for x, _ in sequence]

    applicability, rul_status = None, None
    candidate = core._applicability_candidate("femto")
    if candidate is not None:
        cols = list(candidate.applicability.feature_columns)
        rows = []
        for x, y in sequence:
            row = {}
            row.update(time_domain_features(x, "vibration_x"))
            row.update(frequency_domain_features(x, cfg.sample_rate_hz, "vibration_x"))
            row.update(time_domain_features(y, "vibration_y"))
            row.update(frequency_domain_features(y, cfg.sample_rate_hz, "vibration_y"))
            rows.append({c: row.get(c, np.nan) for c in cols})
        result = applicability_assess(pd.DataFrame(rows, dtype=float), candidate.applicability,
                                      single_recording=False)
        applicability = {"level": result["level"], "shift_ratio": result["shift_ratio"],
                         "reasons": result["reasons"]}
        decision = decide(True, [], [(candidate, result, True)])
        rul_status = "suppressed" if decision["status"] == RUL_SUPPRESSED else str(decision["status"])
    return SyntheticResponse(
        first_acquisition=_thin(sequence[0][0]), rms=rms, kurtosis=kurt,
        applicability=applicability, rul_status=rul_status,
        note="Synthetic, simulated data: a controlled demonstration signal, never a model of a real bearing.",
    )


@router.post("/synthetic/zip")
def synthetic_zip(req: SyntheticRequest) -> StreamingResponse:
    from bearing_pdm.synthetic import write_synthetic_zip

    with tempfile.TemporaryDirectory() as tmp:
        path = write_synthetic_zip(_synthetic_config(req), Path(tmp) / "synthetic_bearing.zip")
        data = Path(path).read_bytes()
    return StreamingResponse(
        io.BytesIO(data), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="synthetic_bearing.zip"'},
    )


# ---------------------------------------------------------------- Knowledge / RAG

class KnowledgeHit(BaseModel):
    source: str
    page: int | None = None
    chunk_id: str
    score: float
    text: str


class KnowledgeFile(BaseModel):
    file: str
    status: str
    chunks: int
    reason: str = ""


class KnowledgeSearchResponse(BaseModel):
    index: str
    documents: int
    chunks: int
    files: list[KnowledgeFile] = Field(default_factory=list)
    hits: list[KnowledgeHit]


MAX_KNOWLEDGE_FILES = 10
MAX_KNOWLEDGE_BYTES = 20 * 1024 * 1024


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(
    query: str = Form(""), files: list[UploadFile] | None = File(None),
) -> KnowledgeSearchResponse:
    """Search the project's built-in knowledge index, or a temporary index built from the
    uploaded documents for this request only. Never replaces the shared /explain index."""
    from bearing_pdm.rag.ingest import ingest_paths
    from bearing_pdm.rag.retrieval import VectorIndex

    status: list[KnowledgeFile] = []
    if files:
        if len(files) > MAX_KNOWLEDGE_FILES:
            raise HTTPException(status_code=400, detail=f"at most {MAX_KNOWLEDGE_FILES} documents")
        total = 0
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for f in files:
                name = Path(f.filename or "document").name
                if Path(name).suffix.lower() not in (".pdf", ".md", ".txt", ".docx"):
                    raise HTTPException(status_code=400, detail=f"{name}: only PDF, Markdown, TXT or DOCX")
                data = await f.read()
                total += len(data)
                if total > MAX_KNOWLEDGE_BYTES:
                    raise HTTPException(status_code=413, detail="documents are over 20 MB in total")
                p = Path(tmp) / name
                p.write_bytes(data)
                paths.append(p)
            result = ingest_paths(paths)
        status = [KnowledgeFile(file=Path(r.path).name, status=r.status, chunks=r.chunk_count,
                                reason=r.reason or "") for r in result.files]
        if not result.chunks:
            return KnowledgeSearchResponse(index="uploaded", documents=0, chunks=0, files=status, hits=[])
        index, label = VectorIndex.build_from_chunks(result.chunks), "uploaded"
    else:
        index, label = core._rag_index(), "built-in"
    hits = index.search(query, top_k=5) if query.strip() else []
    return KnowledgeSearchResponse(
        index=label, documents=len({c.doc_id for c in index.chunks}), chunks=len(index.chunks),
        files=status,
        hits=[KnowledgeHit(source=Path(h.source).name, page=h.page, chunk_id=str(h.chunk_id),
                           score=round(float(h.score), 4), text=h.text[:600]) for h in hits],
    )
