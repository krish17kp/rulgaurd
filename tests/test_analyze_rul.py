"""Raw FEMTO fixture equivalence and fail-closed analysis routing."""
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api
from bearing_pdm.features import frequency_domain_features, time_domain_features

client = TestClient(api.app)
FIXTURE = Path(__file__).resolve().parents[1] / 'data/fixtures/femto/Bearing1_1/acc_00001.csv'


@pytest.fixture
def raw():
    return pd.read_csv(FIXTURE, header=None)[[4, 5]].rename(
        columns={4: 'vibration_x', 5: 'vibration_y'})


def post(raw, **params):
    return client.post('/analyze/rul', params={
        'dataset_id': 'femto', 'units': 'g', 'sampling_rate_hz': 25600,
        'preprocessing_version': api.FEMTO_PREPROCESSING_VERSION, **params},
        files={'file': ('acquisitions.csv', raw.to_csv(index=False).encode(), 'text/csv')})


def test_real_raw_fixture_matches_predict_rul(raw):
    features = {}
    for channel in raw:
        features.update(time_domain_features(raw[channel].to_numpy(), channel))
        features.update(frequency_domain_features(raw[channel].to_numpy(), 25600, channel))
    reference = client.post('/predict/rul', json={'dataset_id': 'femto', 'features': features})
    response = post(raw)
    assert reference.status_code == response.status_code == 200, response.json()
    body = response.json()
    assert body['rul_seconds'] == pytest.approx(reference.json()['rul_seconds'], rel=1e-10)
    assert body['rul_hours'] == pytest.approx(body['rul_seconds'] / 3600)
    assert body['supporting']['latest_features'] == pytest.approx(features)
    assert body['model']['name'] == 'extra_trees'
    assert body['model']['version'].startswith('sha256:')
    assert body['model']['feature_schema_version'].startswith('sha256:')
    assert body['compatibility'] == 'FULLY_SUPPORTED'
    assert body['prediction_produced'] is True
    assert body['reliability'] == reference.json()['reliability']
    assert body['health'] is None and body['health_indicator_produced'] is False
    assert any('Health indicator unavailable' in w for w in body['warnings'])
    assert body['stages'][-1]['status'] == 'ok'


@pytest.mark.parametrize(('params', 'code'), [
    ({'dataset_id': 'college'}, 'RETRAIN_REQUIRED'),
    ({'dataset_id': 'unknown'}, 'UNSUPPORTED_DATASET'),
    ({'sampling_rate_hz': 1000}, 'RETRAIN_REQUIRED'),
    ({'units': 'm/s2'}, 'UNITS_MISMATCH'),
    ({'preprocessing_version': 'unknown'}, 'PREPROCESSING_MISMATCH'),
    ({'window_samples': 1280}, 'PREPROCESSING_MISMATCH'),
    ({'overlap_samples': 1}, 'PREPROCESSING_MISMATCH'),
])
def test_metadata_gates_never_infer(raw, params, code, monkeypatch):
    monkeypatch.setattr(api, 'predict_rul', lambda *_: pytest.fail('RUL must not run'))
    monkeypatch.setattr(api, 'predict_hi', lambda *_: pytest.fail('HI must not run'))
    response = post(raw, **params)
    assert response.status_code == 422
    body = response.json()
    assert body['code'] == code
    assert body['rul_seconds'] is None and body['prediction_produced'] is False
    assert body['stages'][-1]['status'] == 'skipped'


@pytest.mark.parametrize('mutation', ['missing_axis', 'constant', 'infinite', 'partial', 'cap'])
def test_data_gates(raw, mutation, monkeypatch):
    if mutation == 'missing_axis':
        raw = raw.drop(columns='vibration_y')
    elif mutation == 'constant':
        raw['vibration_y'] = 1.0
    elif mutation == 'infinite':
        raw.loc[0, 'vibration_y'] = float('inf')
    elif mutation == 'partial':
        raw = pd.concat([raw, raw.iloc[:1]])
    else:
        monkeypatch.setattr(api, 'MAX_RETURNED_WINDOWS', 1)
        raw = pd.concat([raw, raw])
    monkeypatch.setattr(api, 'predict_rul', lambda *_: pytest.fail('RUL must not run'))
    response = post(raw)
    assert response.status_code == 422, response.json()
    assert response.json()['prediction_produced'] is False


@pytest.mark.parametrize('artifact', ['rul_extra_trees.joblib', 'reference_hi_model.joblib',
                                      'stage_thresholds.joblib'])
def test_missing_model_503(raw, artifact, monkeypatch):
    load = api._load_joblib
    monkeypatch.setattr(api, '_load_joblib', lambda name: None if name == artifact else load(name))
    response = post(raw)
    assert response.status_code == 503, response.json()
    assert response.json()['code'] == 'MODEL_UNAVAILABLE'
    assert response.json()['rul_seconds'] is None


def test_schema_gate(raw, monkeypatch):
    name, artifact, model = api._selected_rul_model()
    changed = replace(model, feature_columns=(*model.feature_columns, 'not_extracted'))
    monkeypatch.setattr(api, '_selected_rul_model', lambda: (name, artifact, changed))
    response = post(raw)
    assert response.status_code == 422
    assert response.json()['compatibility'] == 'ADAPTER_REQUIRED'


def test_degenerate_hi_history_does_not_predict(raw, monkeypatch):
    monkeypatch.setattr(api, 'predict_rul', lambda *_: pytest.fail('RUL must not run'))
    response = post(pd.concat([raw] * 60, ignore_index=True))
    assert response.status_code == 422, response.json()
    assert response.json()['code'] == 'DEGENERATE_REFERENCE_WINDOW'
    assert response.json()['failed_stage'] == 'health_indicator'


def test_second_axis_failure_keeps_later_stages_skipped(raw):
    raw['vibration_y'] = 0.0
    body = post(raw).json()
    names = {s['name']: s['status'] for s in body['stages']}
    assert names['validation'] == 'failed'
    assert names['preprocessing'] == names['feature_extraction'] == 'skipped'


def test_hi_orchestration_matches_existing_path(raw):
    # Artificial history made from the two real fixtures: numerical plumbing
    # evidence only, never a real run or a held-out performance measurement.
    second = pd.read_csv(FIXTURE.with_name('acc_00002.csv'), header=None)[[4, 5]]
    second.columns = raw.columns
    history = pd.concat([raw, second] * 30, ignore_index=True)
    response = post(history)
    assert response.status_code == 200, response.json()
    features = []
    for frame in (raw, second):
        row = {}
        for channel in frame:
            row.update(time_domain_features(frame[channel].to_numpy(), channel))
            row.update(frequency_domain_features(frame[channel].to_numpy(), 25600, channel))
        features.append(row)
    reference = client.post('/predict/hi', json={'dataset_id': 'femto', 'rows': [
        {**features[i % 2], 'sequence_index': i} for i in range(60)]})
    assert reference.status_code == 200, reference.json()
    body = response.json()
    assert body['health_indicator_produced'] is True
    for actual, expected in zip(body['health']['rows'], reference.json()['rows'], strict=True):
        assert actual['health_indicator'] == pytest.approx(expected['health_indicator'], abs=1e-12)
        assert actual['stage'] == expected['stage']
    assert body['supporting']['hi_model_version'].startswith('sha256:')


def test_nonfinite_window_features_suppress_prediction(raw, monkeypatch):
    constant = raw.copy()
    constant[:] = 1.0
    monkeypatch.setattr(api, 'predict_rul', lambda *_: pytest.fail('RUL must not run'))
    response = post(pd.concat([constant, raw], ignore_index=True))
    assert response.status_code == 422
    assert response.json()['code'] == 'NON_FINITE_FEATURES'


def test_header_aliases_preserve_prediction(raw):
    reference = post(raw).json()
    raw = raw.rename(columns={'vibration_x': 'horizontal_acceleration',
                              'vibration_y': 'vertical_acceleration'})
    response = post(raw)
    assert response.status_code == 200, response.json()
    assert response.json()['rul_seconds'] == pytest.approx(reference['rul_seconds'])


def test_selected_metadata_missing(raw, monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'MODELS_DIR', tmp_path)
    response = post(raw)
    assert response.status_code == 503
    assert response.json()['code'] == 'MODEL_UNAVAILABLE'
    assert response.json()['prediction_produced'] is False
