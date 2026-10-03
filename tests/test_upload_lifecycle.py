"""Request-owned raw files must be closed and deleted on every terminal path."""
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import pytest
import starlette.formparsers
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from bearing_pdm import api

ROUTES = ['/dataset/inspect', '/analyze/features', '/analyze/rul']
PARAMS = {
    '/dataset/inspect': {},
    '/analyze/features': {'channel': 'vibration_x', 'sampling_rate_hz': 25600},
    '/analyze/rul': {'dataset_id': 'femto', 'units': 'g', 'sampling_rate_hz': 25600,
                     'preprocessing_version': api.FEMTO_PREPROCESSING_VERSION},
}


@pytest.fixture
def raw():
    path = Path(__file__).resolve().parents[1] / 'data/fixtures/femto/Bearing1_1/acc_00001.csv'
    return pd.read_csv(path, header=None)[[4, 5]].rename(
        columns={4: 'vibration_x', 5: 'vibration_y'}).to_csv(index=False).encode()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    directory = tmp_path / 'uploads'
    directory.mkdir()
    monkeypatch.setattr(api.tempfile, 'tempdir', str(directory))
    # Keep references: garbage collection must not mask missing explicit closes.
    opened = []
    original = starlette.formparsers.SpooledTemporaryFile

    def spool(*args, **kwargs):
        kwargs['max_size'] = 1  # exercise real on-disk multipart spooling
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, 'SpooledTemporaryFile', spool)
    yield directory, opened
    assert list(directory.iterdir()) == []
    assert all(file.closed for file in opened)


def post(route, data, **kwargs):
    return TestClient(api.app, raise_server_exceptions=False).post(
        route, params=PARAMS[route], files={'file': ('../../model.joblib', data)}, **kwargs)


def invalid_rate(route):
    # /dataset/inspect takes its declaration as a form field, the others as a query.
    if route == '/dataset/inspect':
        return {'params': PARAMS[route], 'data': {'declared_sampling_rate_hz': -1}}
    return {'params': {**PARAMS[route], 'sampling_rate_hz': -1}}


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('case', ['success', 'empty', 'binary', 'encoding', 'file_limit',
                                  'parser', 'memory', 'storage', 'timeout', 'unexpected',
                                  'validation'])
def test_terminal_paths(route, case, raw, storage, monkeypatch, caplog):
    data = raw
    expected = 200
    if case == 'empty':
        data, expected = b'', 422
    elif case == 'binary':
        data, expected = b'\x00raw', 415
    elif case == 'encoding':
        data, expected = b'\xff\xfe', 422
    elif case == 'file_limit':
        monkeypatch.setattr(api, 'UPLOAD_CHUNK_BYTES', 1024)
        monkeypatch.setattr(api, 'MAX_UPLOAD_BYTES', 2048)
        expected = 413
    elif case == 'validation':
        data = b'vibration_x,vibration_y\n1,1\n1,1\n'
        expected = 200 if route == '/dataset/inspect' else 422
    elif case in ('parser', 'memory', 'storage', 'timeout', 'unexpected'):
        error = {'parser': ValueError, 'memory': MemoryError, 'storage': OSError,
                 'timeout': TimeoutError, 'unexpected': RuntimeError}[case]

        def fail(*args, **kwargs):
            raise error('private raw data must not be logged')

        target = '_check_text_head' if case == 'storage' else 'profile_file'
        monkeypatch.setattr(api, target, fail)
        expected = 503 if case in ('memory', 'storage') else 422
    with caplog.at_level(logging.INFO, logger='bearing_pdm.api'):
        response = post(route, data)
    assert response.status_code == expected, response.text
    records = [r for r in caplog.records if hasattr(r, 'cleanup_state')]
    assert records[-1].cleanup_state == 'deleted'
    assert len(records[-1].upload_id) == 32
    assert 'private raw data' not in caplog.text
    assert list(storage[0].iterdir()) == []


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('error', [ClientDisconnect, asyncio.CancelledError, TimeoutError])
def test_interruption_during_copy(route, error, storage):
    class InterruptedUpload:
        filename = 'recording.csv'
        calls = 0

        async def read(self, size):
            self.calls += 1
            if self.calls == 1:
                return b'vibration_x,vibration_y\n1,2\n'
            assert len(list(storage[0].iterdir())) == 1
            raise error()

    async def run():
        file = InterruptedUpload()
        if route == '/dataset/inspect':
            await api.inspect_dataset(file, declared_sampling_rate_hz=None, declared_units=None)
        elif route == '/analyze/features':
            await api.analyze_features(file, channel='vibration_x', sampling_rate_hz=25600,
                                       window_samples=2560, overlap_samples=0)
        else:
            await api.analyze_rul(file, **PARAMS[route], window_samples=2560, overlap_samples=0)

    # TimeoutError is an OSError and is translated to STORAGE_UNAVAILABLE.
    with pytest.raises(api.ApiError if error is TimeoutError else error):
        asyncio.run(run())


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('ending', ['disconnect', 'cancel', 'stream_limit', 'declared_limit'])
def test_transport_interruption(route, ending, storage, monkeypatch):
    monkeypatch.setattr(api, '_MAX_REQUEST_BYTES', 1024)
    header = (b'--boundary\r\nContent-Disposition: form-data; name="file"; '
              b'filename="x.csv"\r\n\r\n')
    messages = [
        {'type': 'http.request', 'body': header + b'vibration_x\n1\n2\n', 'more_body': True},
    ]
    if ending == 'stream_limit':
        messages.append({'type': 'http.request', 'body': b'3\n' * 1024, 'more_body': True})
    headers = [(b'content-type', b'multipart/form-data; boundary=boundary')]
    if ending == 'declared_limit':
        headers.append((b'content-length', b'2048'))
    sent = []

    async def receive():
        if messages:
            return messages.pop(0)
        if ending == 'cancel':
            raise asyncio.CancelledError()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)

    async def run():
        await api.app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                       'method': 'POST', 'scheme': 'http', 'path': route, 'root_path': '',
                       'query_string': urlencode(PARAMS[route]).encode(), 'headers': headers,
                       'client': ('test', 123), 'server': ('test', 80)}, receive, send)

    if ending == 'cancel':
        # BaseHTTPMiddleware may surface cancellation as no response returned.
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            asyncio.run(run())
    else:
        asyncio.run(run())
    if ending in ('stream_limit', 'declared_limit'):
        assert next(m['status'] for m in sent if m['type'] == 'http.response.start') == 413
    if ending != 'declared_limit':
        assert storage[1], 'must create a multipart spool before interruption'


@pytest.mark.parametrize('stage', ['predict_hi', 'predict_rul'])
def test_prediction_failure_and_retry(stage, raw, storage, monkeypatch):
    original = getattr(api, stage)

    def fail(*args):
        assert list(storage[0].iterdir()) == []  # raw data already released before inference
        raise api.ApiError(503, 'MODEL_UNAVAILABLE', 'Model unavailable.', True)

    monkeypatch.setattr(api, stage, fail)
    assert post('/analyze/rul', raw).status_code == 503
    monkeypatch.setattr(api, stage, original)
    assert post('/analyze/rul', raw).status_code == 200


def test_cleanup_isolation(storage, tmp_path):
    unrelated = tmp_path / 'shared-model-sentinel'
    unrelated.write_bytes(b'unchanged')
    with api._temporary_upload() as first:
        first.write(b'first')
        with api._temporary_upload() as second:
            second.write(b'second')
            assert first.name != second.name
        assert Path(first.name).exists()
        assert not Path(second.name).exists()
    assert unrelated.read_bytes() == b'unchanged'


@pytest.mark.parametrize('route', ROUTES)
def test_query_validation_closes_multipart(route, raw, storage):
    response = TestClient(api.app).post(
        route, files={'file': ('input.csv', raw)}, **invalid_rate(route))
    assert response.status_code == 422
    assert storage[1]


@pytest.mark.parametrize('route', ROUTES)
def test_malformed_multipart_closes_prior_file(route, storage):
    body = (b'--boundary\r\nContent-Disposition: form-data; name="file"; '
            b'filename="x.csv"\r\n\r\nvibration_x\n1\n2\n\r\n'
            b'--boundary\r\nContent-Disposition: form-data\r\n\r\nbad\r\n'
            b'--boundary--\r\n')
    response = TestClient(api.app).post(
        route, params=PARAMS[route], content=body,
        headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
    assert response.status_code == 400
    assert storage[1]


@pytest.mark.parametrize('route', ['/analyze/features', '/analyze/rul'])
def test_unhandled_analysis_failure(route, raw, storage, monkeypatch):
    def fail(*args, **kwargs):
        assert len(list(storage[0].iterdir())) == 1
        raise RuntimeError('analysis failed')

    monkeypatch.setattr(api, '_analyze_spooled', fail)
    assert post(route, raw).status_code == 500


def test_creation_and_cleanup_failure_states(storage, monkeypatch):
    fields = {}
    token = api._REQUEST_OBS.set(fields)
    original = api.tempfile.NamedTemporaryFile

    def unavailable(**kwargs):
        raise OSError('storage unavailable')

    try:
        monkeypatch.setattr(api.tempfile, 'NamedTemporaryFile', unavailable)
        with pytest.raises(OSError), api._temporary_upload():
            pytest.fail('must not analyze without storage')
        assert fields['cleanup_state'] == 'not_created'
        monkeypatch.setattr(api.tempfile, 'NamedTemporaryFile', original)
        with pytest.raises(OSError), api._temporary_upload() as file:
            close = file.close

            def failed_close():
                close()  # leave no real test residue, but simulate an OS close error
                raise OSError('close failed')

            monkeypatch.setattr(file, 'close', failed_close)
        assert fields['cleanup_state'] == 'failed'
    finally:
        api._REQUEST_OBS.reset(token)
