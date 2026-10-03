"""Sampling evidence must establish units and regular intervals."""
import pytest
from fastapi.testclient import TestClient

from bearing_pdm.api import app
from bearing_pdm.profiler import profile_folder

client = TestClient(app)


def inspect(csv, rate=None):
    return client.post('/dataset/inspect',
                       data={} if rate is None else {'declared_sampling_rate_hz': rate},
                       files={'file': ('signal.csv', csv, 'text/csv')})


@pytest.mark.parametrize('times,regular,rate', [
    ('0\n0.01\n0.02', True, 100),
    ('0\n0.01\n0.02005', True, 1 / 0.010025),
    ('0\n0.01\n0.03', False, None),
    ('0\n0\n0.01', False, None),
    ('0.02\n0.01\n0', False, None),
    ('0\nNaN\n0.02', False, None),
    ('0\n0.01', None, None),
])
def test_timestamp_intervals(times, regular, rate):
    response = inspect('time_s\n' + times + '\n')
    assert response.status_code == 200
    info = response.json()['sampling']
    assert info['regular'] is regular
    assert info['rate_hz'] == (pytest.approx(rate) if rate else None)
    assert info['source'] == ('timestamps' if rate else 'unknown')
    assert info['required'] is (rate is None)


@pytest.mark.parametrize('csv', ['vibration_x\n1\n2\n3\n', 'time\n0\n1\n2\n'])
def test_missing_sampling_or_units(csv):
    info = inspect(csv).json()['sampling']
    assert info['rate_hz'] is None
    assert info['regular'] is None
    assert info['required'] is True


def test_iso_timestamps():
    info = inspect('timestamp\n2026-01-01T00:00:00.000Z\n'
                   '2026-01-01T00:00:00.010Z\n2026-01-01T00:00:00.020Z\n').json()['sampling']
    assert info['rate_hz'] == pytest.approx(100)


def test_user_rate_overrides_without_claiming_regularity():
    info = inspect('time_s\n0\n1\n3\n', 25600).json()['sampling']
    assert info['rate_hz'] == 25600
    assert info['source'] == 'user'
    assert info['regular'] is False
    assert info['required'] is False


@pytest.mark.parametrize('rate', ['0', '-1', 'nan', 'inf', '-inf', '1000001', 'bad'])
def test_invalid_user_rate(rate):
    assert inspect('vibration_x\n1\n2\n3\n', rate).status_code == 422


def test_folder_reuses_regular_interval_check(tmp_path):
    (tmp_path / 'signal.csv').write_text('time_s,vibration_x\n0,1\n0.01,2\n0.03,3\n')
    assert profile_folder(tmp_path)['sampling_rate_hz'] is None


def test_irregular_tail_after_profile_sample():
    times = list(range(6000)) + [6001]
    info = inspect('time_s\n' + '\n'.join(map(str, times))).json()['sampling']
    assert info['rate_hz'] is None
    assert info['regular'] is False
