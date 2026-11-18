"""Scoped Android host I/O for the pinned ZZZ publisher catalogue worker."""
import base64
import json
import re
import shutil
import stat
import tempfile
from pathlib import Path

from .game_data_protocol import GameDataError
from .private_data_paths import _no_links

IDENTITY = 'e2c8551d8841c7447689b356d09d77e6c72651d94b9bc9bf245634b3362bc24b'
MAX_FILE = 128 * 1024**2
MAX_OUTPUT = 256 * 1024**2
CHUNK = 24 * 1024
MODES = {
    'scene-plan': ('design', 'catalogs'),
    'presentation-config-plan': ('catalogs', 'roots'),
    'presentation-owners': ('catalogs', 'blocks'),
    'comic-plan': ('catalogs', 'roots'),
    'catalogue': ('design', 'blocks', 'comics', 'cinemaTimelines', 'voiceDirectory'),
}
SOURCE = re.compile(
    r'(?:(?:design-|catalog-|Blocks-(?:Data-)?)[0-9]+\.blk|[0-9]+\.blk\.'
    r'(?:scenes|comics|comic-roots|voice-directory|presentation-roots|presentation-configs|cinema-timelines))'
)
DIGEST = re.compile(r'[0-9a-f]{64}')
LOCALES = frozenset(('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'de', 'es-ES', 'fr', 'id', 'pt-BR', 'ru', 'th', 'vi'))


def _require(condition):
    if not condition:
        raise GameDataError('invalid_zzz_catalogue_stage', 'The ZZZ catalogue stage was incomplete or invalid.', 409)


def _unavailable():
    return GameDataError('zzz_catalogue_worker_unavailable', 'The verified Android ZZZ catalogue worker is unavailable.', 503)


def create_android_catalogue(native):
    """Obtain the application-owned Java capability. The provider owns no WebView."""
    try:
        from java import jclass
        worker = native.zzzCatalogueWorker()
        _require(isinstance(worker, jclass('io.github.firebird55.gameimmersiontoolkit.ZzzCatalogueWorker')))
        _require(str(worker.proof()) == IDENTITY)
    except Exception as error:
        raise _unavailable() from error
    return worker


def _roles(mode, spec, audio):
    _require(mode in MODES and isinstance(spec, dict))
    names = set()
    for role in MODES[mode]:
        files = spec.get(role, [])
        _require(isinstance(files, list) and len(files) <= 512)
        for name in files:
            _require(isinstance(name, str) and len(name) <= 80 and SOURCE.fullmatch(name))
            names.add(name)
    _require(len(names) <= 512)
    outputs = {mode + '-output.json'}
    if mode == 'catalogue':
        _require(spec.get('includeAudio') is audio and (audio or not spec.get('voiceDirectory')))
        locales = spec.get('locales')
        _require(isinstance(locales, list) and 1 <= len(locales) <= 13)
        for locale in locales:
            _require(isinstance(locale, str) and locale in LOCALES)
            outputs.add('texts-' + locale + '.json')
        outputs.update(('links.json', 'voice-directory.json'))
        if audio:
            outputs.add('audio-resource.flex')
    return names, outputs


def _regular(path):
    _no_links(path)
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_FILE)
    return info.st_size


def _send(ticket, **event):
    ticket.send(json.dumps(event, separators=(',', ':')))


def _message(ticket, check):
    while True:
        check()
        event = ticket.poll(250)
        check()
        if event is not None:
            event = str(event)
            _require(0 < len(event) <= 33_000)
            message = json.loads(event)
            _require(isinstance(message, dict))
            return message


def _push(ticket, event, check, path, digest):
    length = _regular(path)
    with path.open('rb') as source:
        request = event['id']
        _send(ticket, type='input', id=request, size=length, sha256=digest)
        while length:
            _require(_message(ticket, check) == {'type': 'pull', 'id': request})
            count = min(CHUNK, length)
            part = source.read(count)
            _require(len(part) == count)
            _send(ticket, type='chunk', id=request, data=base64.b64encode(part).decode('ascii'))
            length -= count
        check()
        _require(source.read(1) == b'')


def _pull(ticket, event, check, path, size):
    request = event['id']
    with path.open('xb') as destination:
        while size:
            _send(ticket, type='pull', id=request)
            part = _message(ticket, check)
            _require(part.get('type') == 'chunk' and part.get('id') == request and
                     isinstance(part.get('data'), str) and len(part['data']) <= CHUNK * 4 // 3)
            decoded = base64.b64decode(part['data'], validate=True)
            _require(len(decoded) == min(CHUNK, size))
            destination.write(decoded)
            size -= len(decoded)
    _send(ticket, type='pull', id=request)


def run_stage(worker, mode, spec, staged_directory, receipts, ctx):
    """Return a complete private output directory. The caller validates and publishes its contents."""
    ctx.check()
    audio = ctx.request.content_mode == 'text-audio'
    _require(ctx.game == 'zzz' and ctx.request.content_mode in {'text', 'text-audio'})
    names, outputs = _roles(mode, spec, audio)
    _require(isinstance(receipts, dict) and set(receipts) == names and
             all(isinstance(digest, str) and DIGEST.fullmatch(digest) for digest in receipts.values()))
    root, staged = Path(ctx.directory), Path(staged_directory)
    for directory in (root, staged):
        _no_links(directory)
        _require(directory.is_absolute() and '..' not in directory.parts and directory.is_dir())
    _require(staged == root or root in staged.parents)
    for name in names:
        _regular(staged / name)
    control = json.dumps(spec, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    _require(len(control) <= 192 * 1024)
    pending = Path(tempfile.mkdtemp(prefix='zzz-catalogue-', dir=root))
    ticket = None
    complete = False
    try:
        ctx.check()
        _require(str(worker.proof()) == IDENTITY)
        ticket = worker.begin(mode, control)
        _require(_message(ticket, ctx.check) == {'type': 'started', 'identity': IDENTITY})
        written, request, used = set(), 0, 0
        while True:
            event = _message(ticket, ctx.check)
            kind = event.get('type')
            if kind == 'complete':
                _require(written == outputs)
                ctx.check()
                complete = True
                return pending
            if kind == 'failed':
                raise _unavailable()
            name, identifier = event.get('name'), event.get('id')
            _require(type(identifier) is int and identifier == request + 1 and isinstance(name, str))
            request = identifier
            if kind == 'read':
                _require(name in receipts)
                _push(ticket, event, ctx.check, staged / name, receipts[name])
            elif kind == 'write':
                size = event.get('size')
                _require(name in outputs and name not in written and type(size) is int and
                         0 < size <= MAX_FILE and used + size <= MAX_OUTPUT)
                _pull(ticket, event, ctx.check, pending / name, size)
                written.add(name)
                used += size
            else:
                _require(False)
    except GameDataError:
        # Owner/epoch changes and cancellation retain their existing public state.
        raise
    except Exception as error:
        raise _unavailable() from error
    finally:
        try:
            if ticket is not None:
                ticket.cancel()
        finally:
            if not complete:
                shutil.rmtree(pending)
