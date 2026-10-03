"""Deployment/offline parity on committed samples; tolerances documented below.

Samples and framing: exact (CSV text preserved, no transforms permitted).
Features/model inputs/HI: rtol=1e-12, atol=1e-12 for float64 roundoff only.
RUL: rtol=1e-12, atol=1e-9 seconds for parallel tree reduction order.
These are numerical plumbing checks, not held-out accuracy measurements.
"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, chunked
from bearing_pdm import artifacts as artifacts_module
from bearing_pdm.adapters import FemtoAdapter
from bearing_pdm.health import apply_reference_hi
from bearing_pdm.modeling import predict_tree_baseline
from bearing_pdm.pipeline import canonical_feature_row
from bearing_pdm.stages import assign_stages

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def recordings():
    adapter = FemtoAdapter()
    run = adapter.discover(ROOT / 'data/fixtures/femto')[0]
    return list(adapter.recordings(run))


def upload(recordings):
    # Reheader only: preserve original acceleration decimal text and ordering.
    rows = [','.join(line.split(',')[4:6]) for rec in recordings
            for line in rec.source_path.read_text().splitlines()]
    return ('vibration_x,vibration_y\n' + '\n'.join(rows) + '\n').encode()


def vibration_features(rec):
    return {k: v for k, v in canonical_feature_row(rec).items()
            if k.startswith(('vibration_x_', 'vibration_y_'))}


@pytest.fixture
def artifacts(monkeypatch):
    directory = ROOT / 'artifacts/models'
    required = ('rul_extra_trees.joblib', 'reference_hi_model.joblib',
                'stage_thresholds.joblib', 'rul_selected_model.json')
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        pytest.skip('Parity requires mounted artifacts/models: missing ' + ', '.join(missing))
    monkeypatch.setattr(artifacts_module, 'MODELS_DIR', directory)
    monkeypatch.setattr(api, '_MODEL_CACHE', {})
    monkeypatch.setattr(api, '_MODEL_VERSIONS', {})
    return {name: joblib.load(directory / name) for name in required if name.endswith('.joblib')}


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('chunk_rows', [997, 4096])
def test_raw_preprocessing_and_features(recordings, index, chunk_rows, monkeypatch):
    rec = recordings[index]
    expected = vibration_features(rec)
    captured = []
    original = chunked.time_domain_features

    def observe(samples, prefix):
        captured.append((prefix, samples.copy()))
        return original(samples, prefix)

    monkeypatch.setattr(chunked, 'time_domain_features', observe)
    monkeypatch.setattr(api, 'ANALYZE_CHUNK_ROWS', chunk_rows)
    with TestClient(api.vercel_app) as client:
        for axis in ('vibration_x', 'vibration_y'):
            response = client.post('/api/analyze/features', params={
                'channel': axis, 'sampling_rate_hz': rec.run.sampling_rate_hz,
                'window_samples': 2560, 'overlap_samples': 0,
            }, files={'file': ('fixture.csv', upload([rec]), 'text/csv')})
            assert response.status_code == 200, response.json()
            body = response.json()
            assert body['windows_total'] == body['windows_returned'] == 1
            assert body['truncated'] is False
            assert body['sampling']['rate_hz'] == rec.run.sampling_rate_hz
            window = body['windows'][0]
            assert (window['index'], window['row_start'], window['row_stop']) == (0, 0, 2560)
            reference = {k: v for k, v in expected.items() if k.startswith(axis + '_')}
            assert window['features'].keys() == reference.keys()
            assert window['features'] == pytest.approx(reference, rel=1e-12, abs=1e-12)
    assert len(captured) == 2
    for axis, samples in captured:
        np.testing.assert_array_equal(samples, rec.signals[axis])


@pytest.mark.parametrize('indices', [(0,), (1,), (0, 1) * 30])
def test_raw_to_hi_model_inputs_and_rul(recordings, artifacts, indices, monkeypatch):
    # Alternation supplies a nondegenerate reference window solely to exercise
    # HI plumbing. It is not a real trajectory or evidence of healthy operation.
    history = [recordings[i] for i in indices]
    rows = [vibration_features(rec) for rec in history]
    offline = pd.DataFrame(rows)
    tree = artifacts['rul_extra_trees.joblib']
    reference_rul = float(predict_tree_baseline(offline.iloc[[-1]], tree).iloc[0])
    expected_x = offline.iloc[[-1]][list(tree.feature_columns)].fillna(tree.median_fill)
    served = api._load_joblib('rul_extra_trees.joblib')
    captured = []
    original = served.model.predict

    def observe(frame, *args, **kwargs):
        captured.append(frame.copy())
        return original(frame, *args, **kwargs)

    monkeypatch.setattr(served.model, 'predict', observe)
    with TestClient(api.vercel_app) as client:
        response = client.post('/api/analyze/rul', params={
            'dataset_id': 'femto', 'units': 'g', 'sampling_rate_hz': history[0].run.sampling_rate_hz,
            'preprocessing_version': api.FEMTO_PREPROCESSING_VERSION,
        }, files={'file': ('fixture.csv', upload(history), 'text/csv')})
        assert response.status_code == 200, response.json()
        body = response.json()
        direct = client.post('/api/predict/rul', json={'dataset_id': 'femto', 'features': rows[-1]})
        assert direct.status_code == 200, direct.json()
    assert len(captured) == 2
    for frame in captured:
        assert list(frame.columns) == list(tree.feature_columns)
        np.testing.assert_allclose(frame, expected_x, rtol=1e-12, atol=1e-12)
    for result in (body, direct.json()):
        assert result['rul_seconds'] == pytest.approx(reference_rul, rel=1e-12, abs=1e-9)
        assert result['rul_hours'] == pytest.approx(reference_rul / 3600, rel=1e-12, abs=1e-12)
    assert body['supporting']['latest_features'] == pytest.approx(rows[-1], rel=1e-12, abs=1e-12)
    assert body['supporting']['recordings'] == len(history)
    assert body['model']['name'] == direct.json()['model_name'] == 'extra_trees'
    artifact_bytes = (ROOT / 'artifacts/models/rul_extra_trees.joblib').read_bytes()
    assert body['model']['version'] == 'sha256:' + hashlib.sha256(artifact_bytes).hexdigest()
    schema = json.dumps(list(tree.feature_columns), separators=(',', ':')).encode()
    assert body['model']['feature_schema_version'] == 'sha256:' + hashlib.sha256(schema).hexdigest()
    assert body['model']['trained_dataset_id'] == 'femto'
    assert body['compatibility'] == 'FULLY_SUPPORTED'
    if len(history) == 1:
        assert body['health'] is None
        assert body['health_indicator_produced'] is False
    else:
        offline['sequence_index'] = range(len(offline))
        offline['bearing_run_id'] = history[0].run.run_id
        hi = apply_reference_hi(offline, artifacts['reference_hi_model.joblib'])
        stages = assign_stages(offline, hi, artifacts['stage_thresholds.joblib'])
        assert body['health_indicator_produced'] is True
        actual = body['health']['rows']
        assert [r['sequence_index'] for r in actual] == list(range(len(history)))
        np.testing.assert_allclose([r['health_indicator'] for r in actual], hi,
                                   rtol=1e-12, atol=1e-12)
        assert [r['stage'] for r in actual] == stages.tolist()
