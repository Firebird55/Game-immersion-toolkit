"""Actual codec probe on owned audio in the extracted Windows experiment only."""
import hashlib
from dataclasses import replace
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import threading

from .codec_fixture import authored_flac
from .media_tools import experimental_flac_decoder, ffmpeg_executable
from .preparation_worker import PreparationCancelled
from .runtime_bundle import RuntimeBundleError
from .prebuilt_codecs import PREFIX, SOURCE_REVIEW, SERVICING_REVIEW
from .codec_module_probe import observe


def probe(layout):
    decoder = experimental_flac_decoder(layout=layout)
    if any(p.is_file() and p.suffix.casefold() == '.exe' and p.name.casefold().startswith('ffmpeg')
           for p in layout.application_root.rglob('*')):
        raise RuntimeBundleError('Rejected legacy FFmpeg executable was collected in the Xiph runtime.')
    data, expected = authored_flac()
    modules = observe(layout, decoder, data, expected)
    # Negative artifact cases use owned copies outside every runtime root.
    # The original read-only application is never modified for fault injection.
    for fault in ('missing-dll', 'corrupt-dll'):
        with tempfile.TemporaryDirectory(prefix='Codec fault ', dir=layout.settings_root.parent) as temporary:
            resource = Path(temporary); target = resource / PREFIX
            shutil.copytree(decoder.executable.parent, target)
            for p in target.rglob('*'):
                if p.is_file(): p.chmod(stat.S_IREAD | stat.S_IWRITE)
            dll = target / 'FLAC.dll'
            if fault == 'missing-dll': dll.unlink()
            else: dll.write_bytes(b'authored corrupt DLL; not executable')
            try: experimental_flac_decoder(layout=replace(layout, resource_root=resource))
            except ValueError: pass
            else: raise RuntimeBundleError('Faulty codec DLL unexpectedly resolved.')
    with tempfile.TemporaryDirectory(prefix='Owned codec space 漢字 ', dir=layout.work_root) as temporary:
        root = Path(temporary)
        source, output = root / 'authored.flac', root / 'decoded.pcm'
        source.write_bytes(data); output.write_bytes(b'previous complete output')
        cancelled = threading.Event(); cancelled.set()
        try: decoder.decode(source, output, cancelled=cancelled)
        except PreparationCancelled: pass
        else: raise RuntimeBundleError('Pre-cancelled codec operation executed.')
        if output.read_bytes() != b'previous complete output':
            raise RuntimeBundleError('Cancelled codec operation replaced previous output.')
        decoded = decoder.decode(source, output)
        if output.read_bytes() != expected:
            raise RuntimeBundleError('Real FLAC decode changed expected PCM samples.')
        try: decoder.decode(source, output, timeout=0.001)
        except subprocess.TimeoutExpired: pass
        else: raise RuntimeBundleError('Owned codec deadline did not stop the probe attempt.')
        source.write_bytes(data[:-10])
        try: decoder.decode(source, output)
        except ValueError: pass
        else: raise RuntimeBundleError('Codec accepted a truncated authored FLAC frame.')
        if output.read_bytes() != expected or sorted(path.name for path in root.iterdir()) != ['authored.flac', 'decoded.pcm']:
            raise RuntimeBundleError('Failed codec attempt lost prior output or retained temporary work.')
    # The ordinary game adapter must not infer full FFmpeg acceptance from this
    # single format/fixture or from a mutable receipt's approval-like fields.
    if ffmpeg_executable() is not None:
        raise RuntimeBundleError('Codec experiment unexpectedly enabled general FFmpeg game dispatch.')
    return {'schema': 'proxy-r19-codec-probe-v2', 'status': 'passed', 'codec': 'Xiph FLAC 1.5.0',
        'scope': 'authored FLAC verbatim frame to exact PCM only', 'decode': decoded,
        'artifact_sha256': decoder.manifest['archive_sha256'],
        'executable_sha256': decoder.manifest['files']['flac.exe']['sha256'],
        'library_sha256': decoder.manifest['files']['FLAC.dll']['sha256'],
        'source_kit_sha256': decoder.manifest['files']['codec-sources.zip']['sha256'],
        'input_sha256': hashlib.sha256(data).hexdigest(), 'dll_origins': modules,
        'legacy_ffmpeg_binary_collected': False,
        'missing_dll': 'rejected-before-execution', 'corrupt_dll': 'rejected-before-execution',
        'pre_cancelled': 'previous-output-retained', 'deadline': 'owned-process-cleanup-before-publication',
        'truncated_input': 'previous-output-retained', 'owned_cleanup': 'passed',
        'production_execution_allowed': False, 'redistribution_review': 'pending-exact-output',
        'source_delivery_review': SOURCE_REVIEW, 'servicing_review': SERVICING_REVIEW,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
