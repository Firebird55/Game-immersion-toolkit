"""Run real hosted acquisition commands in an empty workspace, without HTTP."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import urllib.request

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('kind',['zstandard','crypto'])
def test_actual_hosted_software_callers_create_cold_cache_and_keep_pin_verification(tmp_path,monkeypatch,kind):
    lines=(ROOT/'.github/workflows/android-shared-core.yml').read_text().splitlines()
    commands=[re.fullmatch(r'\s+python -c "(.+)"',line)[1] for line in lines if 'm.acquire(' in line]
    assert len(commands)==2
    command=next(value for value in commands if ('android-zstandard' if kind=='zstandard' else 'android-crypto-source') in value)
    scripts=tmp_path/'scripts';scripts.mkdir()
    shutil.copyfile(ROOT/'scripts/build-android-python-dependencies.py',scripts/'build-android-python-dependencies.py')
    policy=tmp_path/'packaging/android';policy.mkdir(parents=True)
    raw=b'Authored software source fixture; not a real dependency acquisition.'
    pin={'source':'https://software.invalid/original','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    name='zstandard-native.json' if kind=='zstandard' else 'publisher-crypto-native.json'
    (policy/name).write_text(json.dumps(pin if kind=='zstandard' else {'source':pin}))
    cache=tmp_path/'output'/('android-zstandard' if kind=='zstandard' else 'android-crypto-source')
    archive=cache/('zstandard-0.25.0.tar.gz' if kind=='zstandard' else 'pycryptodome-3.24.1.tar.gz')
    calls=[]
    def fetch(url,*,timeout):
        assert url==pin['source'] and timeout==60
        assert cache.is_dir(),'The actual workflow must create its owned directory before any transfer.'
        calls.append(url);return io.BytesIO(raw)
    monkeypatch.setattr(urllib.request,'urlopen',fetch)
    monkeypatch.chdir(tmp_path)
    assert not cache.exists()
    exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert archive.read_bytes()==raw and len(calls)==1
    exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert len(calls)==1,'Verified warm inputs must not be acquired again.'
    archive.write_bytes(b'changed software')
    with pytest.raises(ValueError,match='checksum mismatch'):
        exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert len(calls)==1,'A changed cached input must be rejected, never silently replaced.'
