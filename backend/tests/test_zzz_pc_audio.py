"""Canonical audio stages use real ownership parsers and the shared service."""
import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import wave

from flatbuffers import flexbuffers
import pytest
import zstandard

from backend import zzz_pc_audio as audio, zzz_pc_stages as stages, sophon_assets as sophon
from backend import hoyo_publisher_voice as voice
from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError, GameDataPlan, PreparationStage, GameDataRequest
from backend.publisher_transport import PublisherTransport
from backend.source_recordings import OriginalRecordings
from backend.tests.test_game_data import Provider as Baseline, finish, REQUEST
from backend.tests.test_zzz_game_data import Response
from backend.tests.test_zzz_publisher_cinematics import package, link
from backend.zzz_audio_sources import AudioSources
from backend.zzz_pc_sources import OriginalFile
from backend.xxhash64 import xxhash64


class AuthoredCodec:
    identity = 'authored-codec-fixture'
    def resolve(self, raw, sound, destination, *, cancelled):
        assert not cancelled() and raw[:4] == b'RIFF'
        path = Path(destination).with_suffix('.wav')
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(48000)
            stream.writeframes(hashlib.sha256(raw).digest() * 20)
        return path


class FixtureProvider:
    def __init__(self, tmp_path, monkeypatch):
        self.version = 'one';self.move_pointer = False;self.interrupt = False;self.calls = []
        self.reader = SimpleNamespace(identity='authored-reviewed-reader-output')
        self.codecs = AuthoredCodec();self.baseline = Baseline();self.assets = {};self.bodies = {}
        self.last_plan = None
        self.verification = {}
        for generation, suffix in (('one', b'A'), ('two', b'B')):
            original, _ = package(tmp_path / generation, 'en', suffix=suffix)
            raw = original.data;chunks = []
            prefix = 'https://autopatchos.zenlesszonezero.com/authored/' + generation
            for offset in range(0, len(raw), 64):
                part = raw[offset:offset + 64];digest = hashlib.md5(part).hexdigest();identity = '0' * 16 + '_' + digest
                encoded = zstandard.ZstdCompressor().compress(part);self.bodies[prefix + '/' + identity] = encoded
                chunks.append((offset, len(part), len(encoded), identity, digest))
            name = 'ZenlessZoneZero_Data/StreamingAssets/Audio/Windows/Full/En/Owned.pck'
            source = sophon.File(name, len(raw), hashlib.md5(raw).hexdigest(), tuple(chunks), prefix)
            self.assets[generation] = OriginalFile(name, len(raw), xxhash64(raw), '', source)
        self.content = {'links': [link()], 'tables': {'en': {'SyntheticCaption': 'An authored complete caption.'},
            'zh-Hans': {'SyntheticCaption': '合成测试台词。'}}, 'voice_directory': {}, 'coverage': {'presentation_owners': {}},
            'registry': ''}
        # Use the same strict original vector, not an event-id-only surrogate.
        from backend.nte_assets import wwise_hash
        self.content['registry'] = base64.b64encode(flexbuffers.Dumps({'eventReferenceBanks': [wwise_hash('Play_vo_Synthetic_01'), 77, 88, 0]})).decode()
        provider = self
        class BoundSources(AudioSources):
            def assets(self):
                asset = provider.assets[self.build['build']]
                return {asset.name: asset}
        monkeypatch.setattr(audio, 'AudioSources', BoundSources)

    def build(self):return {'channel': 'zzz-global', 'version': '3.3.0', 'build': self.version,
                            'hotfix': {'revisions': {'design': 'authored-design'}}}

    def transport(self, ctx, *, hosts):
        def open(request, **kwargs):
            self.calls.append((ctx.phase, request.full_url))
            raw = self.bodies[request.full_url]
            return Response(request.full_url, raw[:-5] if self.interrupt else raw)
        return PublisherTransport(ctx, hosts=hosts, opener=open)

    def plan(self, request, ctx):
        build = self.build();revision = voice.descriptor(build)[0]
        handle = {'schema': stages.SCHEMA, 'game': 'zzz', 'request': request.json(), 'revision': revision,
                  'build': build, 'reader': self.reader.identity, 'mode': 'fixture-catalogue'}
        planned = audio.plan_candidate(ctx, build, handle, self.reader, transport_factory=self.transport, final_metadata_bytes=0)
        self.last_plan = planned or GameDataPlan(revision, 0, 1024**2, handle=handle, runtime_available=True, stage='fixture-catalogue')
        return self.last_plan

    def download(self, plan, ctx):
        if plan.handle['mode'] == 'fixture-catalogue':return audio.save_candidate(ctx, plan.handle, self.content, self.reader)
        def verify(*args, **kwargs):
            if self.move_pointer:raise GameDataError('zzz_publisher_changed', 'The publisher changed; previous data is kept.', 409)
        return audio.download(ctx, plan, self.reader, self.codecs, transport_factory=self.transport,
                              verify_current=verify, verification=self.verification)

    def restore(self, handle, ctx):
        if handle.get('schema') != audio.SCHEMA:return self.baseline.restore(handle, ctx)
        return audio.restore(ctx, handle, self.codecs, transport_factory=self.transport, verification=self.verification)


def step(service):
    row = service.plan('zzz', REQUEST)['game']
    assert row['can_download'], row
    service.download('zzz', {'plan_id': row['plan_id'], 'revision': row['revision']})
    return finish(service)


def prepare(service):
    stages_seen = []
    for _ in range(12):
        row = step(service);stages_seen.append(row['job']['phase'])
        assert row['job']['status'] != 'failed', row
        if row['job']['status'] == 'complete':return row
    raise AssertionError('Synthetic original source never reached complete audio preparation')


def test_real_service_owned_banks_complete_download_and_offline_restore_retain_old_text(tmp_path, monkeypatch):
    provider = FixtureProvider(tmp_path, monkeypatch)
    root = tmp_path / 'host';service = GameDataService(root, {'zzz': provider.baseline})
    try:
        before = service.plan('zzz', {**REQUEST, 'content_mode': 'text'})['game']
        service.download('zzz', {'plan_id': before['plan_id'], 'revision': before['revision']})
        assert finish(service)['state'] == 'ready'
        pointer = root / 'zzz/current.json';old = pointer.read_bytes()
        service.providers['zzz'] = provider
        first = step(service)
        assert first['job']['status'] == 'needs_plan' and pointer.read_bytes() == old
        assert service.restore('zzz') is not None
        complete = prepare(service)
        assert complete['state'] == 'ready' and complete['content_mode'] == 'text-audio'
        source = service.restore('zzz');payload = json.loads(source.snapshot_path.read_bytes())
        record, = payload['records'];assert record['audio_scope'] == 'context' and source.voice_source.has(record)
        assert not source.voice_source.has({**record, 'audio': {**record['audio'], 'event': 'Play_vo_Other'}})
        assert not source.voice_source.has({**record, 'text_id': 'OtherCaption'})
        calls = list(provider.calls);service.close()
        service = GameDataService(root, {'zzz': provider})
        restored = service.restore('zzz');assert restored.voice_source.has(record) and provider.calls == calls
        resolved = restored.voice_source.resolve(record, tmp_path / 'decoded', cancelled=lambda: False)
        assert resolved.is_file() and provider.calls == calls
        binding_index = restored.snapshot_path.parent / 'original-bindings.json'
        raw = binding_index.read_bytes();binding_index.write_bytes(b' ' + raw[1:])
        with pytest.raises(GameDataError):service.restore('zzz')
        assert provider.calls == calls
    finally:service.close()


def test_normal_worker_publishes_conditional_occurrences_and_restores_original_keys(tmp_path, monkeypatch):
    from backend.multilingual_index import MultilingualTextIndex
    from backend.zzz_cinema_context import CinemaContext, CinemaFrame
    from backend.zzz_cinema_occurrences import FIELD, digest
    from backend.desktop_original_audio import DesktopOriginalVoices
    provider = FixtureProvider(tmp_path, monkeypatch)
    provider.content['links'] = [link(dialogue_kind='cutscene', channels=['cinematic']),
        link(None, text_id='SharedCaption', dialogue_kind='cutscene', channels=['cinematic'])]
    provider.content['tables']['en']['SharedCaption'] = 'The authored shared response.'
    provider.content['tables']['zh-Hans']['SharedCaption'] = '合成共同回复。'
    provider.content['cinema_occurrences'] = [{'text_id': identity, 'locale': 'en', 'start': start,
        'duration': 1., 'resource': 'a' * 64, 'timeline': '10', 'track': '20', 'clip': clip,
        'subtitle_position': 0, 'event': 'Play_vo_Synthetic_01'}
        for identity, start, clip in [('SyntheticCaption', 1., '30'), ('SharedCaption', 4., '40')]]
    root = tmp_path / 'host';service = GameDataService(root, {'zzz': provider})
    try:
        prepare(service)
        source = service.restore('zzz');payload = json.loads(source.snapshot_path.read_bytes())
        assert payload[FIELD]['generation'] == service._metadata(root, 'zzz')['revision']
        shared = next(row for row in payload['records'] if row['text_id'] == 'SharedCaption')
        assert shared['voice_status'] == 'unavailable' and not shared.get('audio')
        index = MultilingualTextIndex('zzz', source.snapshot_path.parent)
        index.publisher_generation = payload['fingerprint']
        index.publisher_request_sha256 = digest(payload[FIELD]['request'])
        context = CinemaContext()
        def observe(text, sequence, when):
            return context.observe(index, [text] if text else [], scope='actual-normal-worker',
                frame=CinemaFrame(sequence, when, when + .01, True), now=when + .02, stable_frames=2)
        assert not observe(provider.content['tables']['en']['SyntheticCaption'], 1, 101.1)
        assert not observe(provider.content['tables']['en']['SyntheticCaption'], 2, 101.35)
        for sequence in range(3, 12):assert not observe('', sequence, 101.35 + (sequence - 2) * .25)
        hit, = observe(provider.content['tables']['en']['SharedCaption'], 12, 104.1)
        host = SimpleNamespace(audio_pool=None)
        voice = DesktopOriginalVoices(host, 'local', service._metadata(root, 'zzz'), index)
        row = voice._row(hit);assert row and source.voice_source.has(row)
        calls = list(provider.calls);service.close()
        service = GameDataService(root, {'zzz': provider})
        restored = service.restore('zzz');assert restored.voice_source.has(row)
        assert restored.voice_source.resolve(row, tmp_path / 'conditional', cancelled=lambda: False).is_file()
        assert provider.calls == calls
        fresh = MultilingualTextIndex('zzz', restored.snapshot_path.parent)
        fresh.publisher_generation, fresh.publisher_request_sha256 = index.publisher_generation, index.publisher_request_sha256
        assert DesktopOriginalVoices(host, 'local', service._metadata(root, 'zzz'), fresh)._row(hit) == row
        assert index.match_lines([shared['source_text']], exact_only=True, channel='cinematic') is None
    finally:service.close()


def test_interrupted_original_transfer_and_final_pointer_failure_preserve_ready_and_saved_recording(tmp_path, monkeypatch):
    provider = FixtureProvider(tmp_path, monkeypatch)
    root = tmp_path / 'host';service = GameDataService(root, {'zzz': provider})
    try:
        prepare(service)
        source = service.restore('zzz');record, = json.loads(source.snapshot_path.read_bytes())['records']
        metadata = service._metadata(root, 'zzz')
        recordings = OriginalRecordings(tmp_path / 'retained-recordings')
        recordings.register(1, metadata, record)
        clip = recordings.materialize(1, lambda descriptor: service.original_voice_source(descriptor, expected_owner='local'))
        old_sha = hashlib.sha256(clip.read_bytes()).hexdigest();old_pointer = (root / 'zzz/current.json').read_bytes()
        provider.version = 'two';step(service)  # New authored dialogue output, not Ready.
        provider.interrupt = True
        failed = step(service)
        assert failed['job']['status'] == 'failed' and (root / 'zzz/current.json').read_bytes() == old_pointer
        assert service.restore('zzz') is not None
        provider.interrupt = False;provider.move_pointer = True
        for _ in range(12):
            failed = step(service)
            if failed['job']['status'] == 'failed':break
        assert failed['job']['status'] == 'failed' and (root / 'zzz/current.json').read_bytes() == old_pointer
        provider.move_pointer = False;prepare(service)
        source = service.restore('zzz');new_record, = json.loads(source.snapshot_path.read_bytes())['records']
        assert new_record['audio']['publisher'] != record['audio']['publisher']
        assert hashlib.sha256(recordings.path(1).read_bytes()).hexdigest() == old_sha
        assert service.original_voice_source(metadata, expected_owner='local').has(record)
    finally:service.close()


def test_bank_ownership_plan_skips_data_payload_and_checks_original_language(tmp_path):
    from backend.honkai_assets import package_tables_from_reader
    original, wem = package(tmp_path, 'en')
    name = 'owned-bank'
    languages, banks, _ = package_tables_from_reader(original.size, lambda start, size: original.read(None, start, size))
    entry = next(value for (identifier, _), value in banks.items() if identifier == 88)
    class Local:
        def ranges_available(self, *args):return True
        def read(self, source, start, size):return source.read(None, start, size)
    ranges = audio._bank_metadata_ranges(Local(), {name: original}, name, entry, 88, 'english(en)')
    data_start = original.size - len(wem)
    assert all(row['offset'] + row['size'] <= data_start or row['offset'] >= original.size for row in ranges)
    with pytest.raises(GameDataError):audio._bank_metadata_ranges(Local(), {name: original}, name, entry, 88, 'japanese(jp)')
