"""Real shared consent/budget/transport, with entirely authored ZIP/PE bytes."""
import copy
import hashlib
import io
import json
from email.message import Message
import zipfile

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Shared pure preparation dependency')
pytest.importorskip('backend.publisher_transport', reason='Shared context-owned transport dependency')
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataRequest, GameDataError
from backend.publisher_transport import PublisherTransport
from backend.endfield_native_import import Import
from backend import endfield_native_source as source
from backend.tests.test_endfield_client_parameters import identity
from backend.tests.endfield_parameter_fixture import toy_pe


class Fixture:
    def __init__(self, tmp_path, monkeypatch):
        self.raw = toy_pe()
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('Endfield_Data/Plugins/x86_64/OwnedSound.dll', self.raw,
                             compress_type=zipfile.ZIP_DEFLATED)
            # Keep the native payload out of the mandatory 65-KiB tail. No
            # large/native member is downloaded merely by planning this source.
            archive.writestr('unrelated-padding.bin', bytes(range(256)) * 400)
        data = output.getvalue()
        self.parts = [data[:len(data) // 2], data[len(data) // 2:]]
        self.identity = identity()
        base = self.identity['url'][:-6] + '/packs/authored.zip.'
        self.identity['artifacts'] = [{'url': base + str(n + 1).zfill(3), 'bytes': len(raw),
            'md5': hashlib.md5(raw).hexdigest()} for n, raw in enumerate(self.parts)]
        self.calls, self.body_reads, self.changed, self.no_tag = [], [], False, False
        self.root, self.service = tmp_path, GameDataService(tmp_path, {})
        self.request = GameDataRequest('global', 'en', (), 'text-audio')
        self.original_import = Import('OwnedSound', 'CurrentAuthoredEntry')
        monkeypatch.setattr(source.signature, 'source_runtime', lambda: None)
        # An authored signature-verifier fixture only. Native publisher-positive
        # evidence is separately the actual cached original WinTrust replay.
        monkeypatch.setattr(source.signature, 'verify', lambda path: {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': len(path.read_bytes()),
            'publisher': 'Authored signature fixture', 'online_revocation_freshness': False})

    def context(self, phase, budget=None):
        return _Context(self.service, self.root, 'local', 'endfield', self.request,
                        self.root / phase, phase, budget=budget)

    def server(self, request, **_):
        number = next(n for n, item in enumerate(self.identity['artifacts']) if item['url'] == request.full_url)
        low, high = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
        raw, fixture = self.parts[number], self
        data = raw[low:high + 1]
        self.calls.append((number, low, high + 1, request.get_header('If-match')))
        class Response:
            status = 206
            def __init__(self):
                self.body, self.headers = io.BytesIO(data), Message()
                self.headers['Content-Length'] = str(len(data))
                self.headers['Content-Range'] = f'bytes {low}-{high}/{len(raw)}'
                if not fixture.no_tag:
                    self.headers['ETag'] = f'"opaque-original-{number}-' + ('B' if fixture.changed else 'A') + '"'
            def geturl(self): return request.full_url
            def read(self, size):
                value = self.body.read(size)
                fixture.body_reads.append(len(value))
                return value
            def __enter__(self): return self
            def __exit__(self, *_): pass
        return Response()

    def source(self, ctx):
        return source.OriginalNativeSource(ctx, self.identity,
            PublisherTransport(ctx, hosts={'beyond.hg-cdn.com'}, opener=self.server))


@pytest.fixture
def original(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    try:
        yield fixture
    finally:
        fixture.service.close()


def test_exact_member_plan_consent_etag_and_complete_source_stage_use_real_shared_core(original):
    planning = original.context('plan')
    plan = original.source(planning).plan(original.original_import)
    payload = plan['payload']
    assert all(not (low <= payload['offset'] < high) for part, low, high, _ in original.calls if part == 0)
    assert plan['download_is_upper_bound'] and plan['download_bytes'] == payload['download_bytes'] + source.RECHECK_METADATA_UPPER
    downloading = original.context('download', budget=plan['download_bytes'])
    path, stage = original.source(downloading).acquire(plan, original.original_import, recheck=lambda: original.identity)
    assert path.read_bytes() == original.raw
    assert downloading.consumed == payload['download_bytes']
    assert stage['stage'] == 'original-audio-native-member-verified'
    assert stage['whole_part_md5_verified'] is stage['gamefiles_member_md5_verified'] is False
    assert 'multiplier' not in stage and 'snapshot_path' not in stage
    assert original.calls[-1][3] == '"opaque-original-0-A"'
    assert original.calls[-1][3] != '"' + original.identity['artifacts'][0]['md5'] + '"'
    # A verified member can be reused without network. The quote is explicitly
    # a conservative upper bound rather than pretending uncached work is zero.
    calls = len(original.calls)
    offline = original.context('download', budget=plan['download_bytes'])
    reused, retained = original.source(offline).acquire(plan, original.original_import, recheck=lambda: original.identity)
    assert reused == path and offline.consumed == 0 and len(original.calls) == calls
    assert retained['range_receipts_sha256'] == stage['range_receipts_sha256']
    assert retained['range_receipt_count'] == stage['range_receipt_count']


def test_text_mode_and_unavailable_signature_runtime_stop_before_any_request(original, monkeypatch):
    original.request = GameDataRequest('global', 'en', (), 'text')
    with pytest.raises(GameDataError) as error:
        original.source(original.context('plan')).plan(original.original_import)
    assert error.value.code == 'audio_not_requested' and not original.calls
    original.request = GameDataRequest('global', 'en', (), 'text-audio')
    from backend.preparation_errors import PreparationFailure
    def unavailable():
        raise PreparationFailure('missing_toolkit_runtime', 'Authored unsupported verifier.', previous_snapshot_retained=True)
    monkeypatch.setattr(source.signature, 'source_runtime', unavailable)
    with pytest.raises(GameDataError) as error:
        original.source(original.context('plan')).plan(original.original_import)
    assert error.value.code == 'missing_toolkit_runtime' and not original.calls


@pytest.mark.parametrize('failure', ['tag_changed', 'wrong_plan', 'signature', 'client_changed', 'no_consent', 'budget'])
def test_failure_preserves_previous_verified_source_pointer(original, monkeypatch, failure):
    planning = original.source(original.context('plan'))
    plan = planning.plan(original.original_import)
    previous = planning.root / 'module.json'
    previous.write_bytes(b'{"previous":"retained original source"}')
    original.body_reads.clear()
    if failure == 'tag_changed':
        original.changed = True
    if failure == 'wrong_plan':
        plan = copy.deepcopy(plan)
        plan['download_bytes'] += 1
    if failure == 'signature':
        monkeypatch.setattr(source.signature, 'verify', lambda _: (_ for _ in ()).throw(ValueError('Authored unsigned source')))
    context = original.context('plan' if failure == 'no_consent' else 'download',
                               budget=1 if failure == 'budget' else plan['download_bytes'])
    with pytest.raises((ValueError, GameDataError)):
        original.source(context).acquire(plan, original.original_import,
            recheck=lambda: {} if failure == 'client_changed' else original.identity)
    assert previous.read_bytes() == b'{"previous":"retained original source"}'
    if failure == 'tag_changed':
        assert not original.body_reads  # Shared If-Match check precedes body reads.


def test_absent_original_object_tag_is_not_synthesized_from_declared_md5(original):
    original.no_tag = True
    with pytest.raises(GameDataError) as error:
        original.source(original.context('plan')).plan(original.original_import)
    assert error.value.code == 'publisher_object_changed'
    assert not list((original.root / 'endfield' / 'cache').rglob('owner.json'))


def test_other_region_cannot_reuse_a_different_original_client_before_io(original):
    original.request = GameDataRequest('cn', 'en', (), 'text-audio')
    with pytest.raises(GameDataError) as error:
        original.source(original.context('plan')).plan(original.original_import)
    assert error.value.code == 'invalid_game_languages' and not original.calls
