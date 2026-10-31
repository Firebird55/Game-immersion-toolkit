"""Transient downloads must not poison the verified source cache."""
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import io
from pathlib import Path
import urllib.error

import pytest

spec = spec_from_file_location('audio_builder', Path(__file__).resolve().parents[2] / 'scripts/build-audio-runtime.py')
builder = module_from_spec(spec)
spec.loader.exec_module(builder)


def pin():
    return {'archive': 'authored-source.tar', 'url': 'https://example.invalid/source',
            'sha256': hashlib.sha256(b'authored source').hexdigest()}


def test_transient_partial_download_retries_without_publishing_partial_cache(tmp_path, monkeypatch):
    calls = []
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise urllib.error.URLError('authored transient interruption')
            return super().read(4)
    def download(*_args, **_kwargs):
        assert not (tmp_path / pin()['archive']).exists()
        calls.append(True)
        return Interrupted(b'authored source') if len(calls) == 1 else io.BytesIO(b'authored source')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)
    monkeypatch.setattr(builder.time, 'sleep', lambda _: None)
    result = builder.acquire(pin(), tmp_path)
    assert result.read_bytes() == b'authored source' and len(calls) == 2
    assert list(tmp_path.iterdir()) == [result]


@pytest.mark.parametrize('kind', ['checksum', '404', 'transient'])
def test_checksum_or_permanent_error_is_not_retried_and_transient_is_bounded(tmp_path, monkeypatch, kind):
    calls = []
    def download(*_args, **_kwargs):
        calls.append(True)
        if kind == 'checksum':
            return io.BytesIO(b'wrong source')
        if kind == '404':
            raise urllib.error.HTTPError('https://example.invalid/source', 404, 'Not found', {}, None)
        raise urllib.error.URLError('authored timeout')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)
    monkeypatch.setattr(builder.time, 'sleep', lambda _: None)
    with pytest.raises((ValueError, urllib.error.URLError)):
        builder.acquire(pin(), tmp_path)
    assert len(calls) == (3 if kind == 'transient' else 1)
    assert not list(tmp_path.iterdir())


def test_bad_existing_cache_is_never_silently_replaced(tmp_path, monkeypatch):
    existing = tmp_path / pin()['archive']
    existing.write_bytes(b'corrupt cached source')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', lambda *_args, **_kwargs: pytest.fail('Unexpected network'))
    with pytest.raises(ValueError, match='checksum'):
        builder.acquire(pin(), tmp_path)
    assert existing.read_bytes() == b'corrupt cached source'


def test_failed_build_emits_bounded_compiler_reason_without_workspace_prefix(tmp_path, monkeypatch, capsys):
    log = tmp_path / 'codec-build.log'
    def failed(_args, **options):
        options['stdout'].write((('old build output\n' * 4000) + str(tmp_path) + '/source/file.c:7: error: missing symbol\n').encode())
        raise builder.subprocess.CalledProcessError(2, ['compiler'])
    monkeypatch.setattr(builder.subprocess, 'run', failed)
    with pytest.raises(RuntimeError, match='sanitized compiler'):
        builder.run(['compiler'], tmp_path, {}, log)
    output = capsys.readouterr().err
    assert 'error: missing symbol' in output and str(tmp_path) not in output
    assert '<build>/source/file.c' in output and len(output) < 12500
