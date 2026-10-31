"""Actual source-built Windows probe; no frozen runtime or Windows 11 claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.codec_fixture import authored_flac
from backend.prebuilt_readers import reader_environment
from backend.preparation_worker import PreparationJob, PreparationCancelled

spec = importlib.util.spec_from_file_location('reference_codec', ROOT / 'scripts/reference-codec.py')
reference = importlib.util.module_from_spec(spec); spec.loader.exec_module(reference)


def probe(root):
    root = Path(root).resolve()
    value = json.loads((root / 'CODEC-CANDIDATE.json').read_text())
    candidate = root / 'candidate'
    before = reference.inventory(candidate)
    if before != value['files']:
        raise ValueError('Candidate bytes differ from the build receipt.')
    environment = reader_environment()
    exe = candidate / 'flac.exe'
    version = subprocess.run([str(exe), '--version'], env=environment,
        cwd=root, stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=True)
    if version.stdout.decode().strip() != 'flac 1.5.0':
        raise ValueError('Unexpected actual codec version.')
    data, expected = authored_flac()
    with tempfile.TemporaryDirectory(prefix='Codec source probe 漢字 ', dir=root) as tmp:
        work = Path(tmp); source = work / 'owned.flac'; output = work / 'complete.pcm'
        source.write_bytes(data); output.write_bytes(b'previous')
        def decode(timeout=10, cancelled=None):
            event = threading.Event() if cancelled is None else cancelled
            job = PreparationJob(SimpleNamespace(stop_event=event, _publication_lock=threading.RLock()), event)
            job.checkpoint()
            with tempfile.TemporaryDirectory(prefix='attempt-', dir=work) as attempt:
                pending = Path(attempt) / 'pending.pcm'
                status = job.run([str(exe), '--decode', '--silent', '--force-raw-format',
                    '--endian=little', '--sign=signed', '--until=512', '--output-name='+str(pending), str(source)],
                    cwd=Path(attempt), env=environment, timeout=timeout)
                if status or not pending.is_file() or pending.read_bytes() != expected:
                    raise ValueError('Decode failed; previous complete output retained.')
                with job.publication(): pending.replace(output)
        cancelled = threading.Event(); cancelled.set()
        try: decode(cancelled=cancelled)
        except PreparationCancelled: pass
        else: raise ValueError('Pre-cancellation did not stop the decode.')
        if output.read_bytes() != b'previous': raise ValueError('Cancellation changed previous output.')
        decode()
        try: decode(timeout=0.001)
        except subprocess.TimeoutExpired: pass
        else: raise ValueError('Owned deadline did not stop the attempt.')
        source.write_bytes(data[:-10])
        try: decode()
        except ValueError: pass
        else: raise ValueError('Truncated frame unexpectedly decoded.')
        if output.read_bytes() != expected or sorted(p.name for p in work.iterdir()) != ['complete.pcm', 'owned.flac']:
            raise ValueError('Failure lost previous output or retained attempt work.')
    if reference.inventory(candidate) != before:
        raise ValueError('Codec probe wrote into the read-only candidate tree.')
    report = {'schema': 'proxy-r19-reference-codec-probe-v1', 'source_commit': value['source_commit'],
        'status': 'passed', 'actual_version': version.stdout.decode().strip(),
        'pcm_sha256': hashlib.sha256(expected).hexdigest(), 'pcm_bytes': len(expected),
        'pre_cancelled': 'previous-output-retained', 'deadline': 'owned-cleanup-passed',
        'truncated_input': 'previous-output-retained', 'owned_cleanup': 'passed',
        'developer_environment': 'OS essentials only; absolute binary; source Python owns Job Object',
        'source_archive_sha256': value['source_archive_sha256'], 'files': before,
        'frozen_runtime_integration': 'not-run', 'native_windows_11_acceptance': 'unavailable',
        'production_execution_allowed': False, 'installer': 'not-built', 'r19_complete': False}
    (root / 'CODEC-PROBE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    probe(p.parse_args().root)
