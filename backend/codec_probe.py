"""Actual codec probe on owned audio in the extracted Windows experiment only."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading

from .codec_fixture import authored_flac
from .media_tools import experimental_flac_decoder, ffmpeg_executable
from .prebuilt_readers import reader_environment
from .preparation_worker import PreparationCancelled
from .runtime_bundle import RuntimeBundleError


def probe(layout):
    decoder = experimental_flac_decoder(layout=layout)
    observations, buildconf, license_text = {}, '', ''
    # Diagnostics are fixed operations with no inputs, shell or inherited
    # loader/account variables. Raw copyright/build output is never uploaded.
    for option in ('-version', '-buildconf', '-L'):
        result = subprocess.run([str(decoder.executable), '-hide_banner', option],
            env=reader_environment(), cwd=layout.work_root, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=10)
        data = result.stdout + result.stderr
        if result.returncode or len(data) > 256 * 1024:
            raise RuntimeBundleError('Fixed codec diagnostic failed or exceeded its bound.')
        observations[option[1:]] = hashlib.sha256(data).hexdigest()
        text = data.decode('utf-8', errors='strict')
        if option == '-version' and 'ffmpeg version 7.1' not in text:
            raise RuntimeBundleError('Codec version differs from the exact observed artifact.')
        if option == '-buildconf': buildconf = text
        if option == '-L': license_text = text
    if '--enable-gpl' not in buildconf or '--enable-version3' not in buildconf or 'General Public License' not in license_text:
        raise RuntimeBundleError('Actual codec license/configuration differs from the retained GPLv3 evidence.')
    data, expected = authored_flac()
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
    return {'schema': 'proxy-r19-codec-probe-v1', 'status': 'passed',
        'scope': 'authored FLAC verbatim frame to exact PCM only', 'decode': decoded,
        'artifact_sha256': decoder.manifest['archive_sha256'],
        'executable_sha256': decoder.manifest['files']['ffmpeg.exe']['sha256'],
        'input_sha256': hashlib.sha256(data).hexdigest(), 'diagnostic_sha256': observations,
        'configuration': {'gpl': True, 'version3': True, 'nonfree': '--enable-nonfree' in buildconf},
        'pre_cancelled': 'previous-output-retained', 'deadline': 'owned-process-cleanup-before-publication',
        'truncated_input': 'previous-output-retained', 'owned_cleanup': 'passed',
        'production_execution_allowed': False, 'redistribution_review': 'pending-exact-output',
        'source_delivery_review': 'open', 'servicing_review': 'open',
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
