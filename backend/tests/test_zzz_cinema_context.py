import json
from types import SimpleNamespace

import pytest

from backend.multilingual_index import MultilingualTextIndex
from backend.zzz_cinema_occurrences import FIELD, build, digest, recording_rows
from backend.zzz_cinema_context import CinemaContext, CinemaFrame, ProxyEvidence, proxy_source_scope
from backend.zzz_pc_audio import LocalOriginals, _binding_keys
from backend.desktop_original_audio import DesktopOriginalVoices, occurrence


def source(tmp_path, *, player_branches=False):
    generation = 'sophon-' + 'c' * 64
    request = {'region': 'global', 'source_locale': 'ja', 'target_locales': ['en', 'zh-Hans'], 'content_mode': 'text-audio'}
    values = {
        'anchor-one': ('独立した合図アルファです', 'This is one unique signal.', '相同的起点'),
        'anchor-two': ('独立した合図ベータです', 'This is another unique signal.', '相同的起点'),
        'shared-one': ('同じ返事を確認します', 'The first shared response.', '第一个相同回答'),
        'shared-two': ('そのまま次へ進みます', 'The second shared response.', '第二个相同回答'),
    }
    records = []
    for number, (identity, texts) in enumerate(values.items(), 1):
        audio = ({'publisher': generation, 'locale': 'ja', 'source': '', 'file_id': f'{number:016x}',
            'package': 'original.pck', 'event': 'Play_vo_' + identity.replace('-', '_'),
            'audio_scope': 'context', 'matched_by': 'publisher_cinematic_event'} if number <= 2 else None)
        records.append({'text_id': identity, 'source_locale': 'ja', 'source_text': texts[0],
            'texts': dict(zip(('ja', 'en', 'zh-Hans'), texts)), 'english': texts[1], 'chinese': texts[2],
            'audio': audio, 'audio_locale': 'ja', 'audio_scope': 'context' if audio else 'line',
            'voice_status': 'voiced' if audio else 'unavailable', 'dialogue_kind': 'cutscene',
            'channels': ['cinematic'], 'text_capture_verified': True})
    if player_branches:
        records[0]['player_voice'] = 'male'
        records[1]['player_voice'] = 'female'
    payload = {'format': 2, 'game': 'zzz', 'fingerprint': generation, 'publisher_region': 'global',
        'source_locale': 'ja', 'content_mode': 'text-audio', 'records': records}
    raw = []
    for variant, anchor in enumerate(('anchor-one', 'anchor-two'), 1):
        for language, locale in enumerate(('ja', 'en', 'zh-Hans'), 1):
            sequence = ('shared-one', anchor, 'shared-two') if player_branches else (anchor, 'shared-one', 'shared-two')
            for ordinal, identity in enumerate(sequence):
                raw.append({'resource': str(variant) * 64, 'timeline': str(variant * 100),
                    'event': records[variant - 1]['audio']['event'], 'text_id': identity, 'locale': locale,
                    'start': 1. + ordinal * 3, 'duration': 1., 'track': str(variant * 100 + language),
                    'clip': str(variant * 1000 + language * 10 + ordinal), 'subtitle_position': 0})
    payload[FIELD] = build(payload, raw, request)
    (tmp_path / 'textmap.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    index = MultilingualTextIndex('zzz', tmp_path)
    assert index.ready
    index.publisher_generation = generation
    index.publisher_request_sha256 = digest(request)
    return payload, index


def observe(context, index, text, sequence, when, *, scope='session-one', fresh=True, player=None):
    frame = CinemaFrame(sequence, when, when + .01, fresh)
    return context.observe(index, [text] if text else [], scope=scope, frame=frame,
        now=when + .05, stable_frames=2, player=player)


def arm(context, index, variant=0, *, locale='ja'):
    row = index._records[variant]
    assert not observe(context, index, row['texts'][locale], 1, 101.1)
    assert not observe(context, index, row['texts'][locale], 2, 101.35)


def advance_blank(context, index, *, start=3, end=11):
    for sequence in range(start, end + 1):
        assert not observe(context, index, '', sequence, 101.35 + (sequence - 2) * .25)


@pytest.mark.parametrize('variant', [0, 1])
def test_forward_context_keeps_base_ambiguous_and_selects_actual_event(tmp_path, variant):
    payload, index = source(tmp_path)
    context = CinemaContext()
    assert index.match_lines([index._records[2]['source_text']], exact_only=True, channel='cinematic') is None
    arm(context, index, variant)
    advance_blank(context, index)
    hits = observe(context, index, index._records[2]['source_text'], 12, 104.1)
    assert len(hits) == 1
    hit = hits[0]
    row = index._zzz_cinema_occurrences['rows'][hit.text_id]
    assert row['audio']['event'] == payload['records'][variant]['audio']['event']
    assert row['member_text_ids'] == ['shared-one'] and hit.audio_scope == 'context'
    assert hit.publisher_occurrence_sha256 == occurrence(row)
    assert payload['records'][2]['voice_status'] == 'unavailable' and payload['records'][2]['audio'] is None
    assert (row['text_id'], digest(row['audio'])) in _binding_keys(payload)


@pytest.mark.parametrize('role, branch', [('male', 0), ('female', 1)])
@pytest.mark.parametrize('locale', ['ja', 'en', 'zh-Hans'])
def test_shared_opening_needs_two_fresh_frames_and_an_established_role(tmp_path, role, branch, locale):
    payload, index = source(tmp_path, player_branches=True)
    context = CinemaContext()
    caption = payload['records'][2]['texts'][locale]
    for ordinal in (1, 2):
        assert not observe(context, index, caption, ordinal, 101 + ordinal * .2)
    assert not observe(context, index, caption, 3, 101.6, player=role)
    hit, = observe(context, index, caption, 4, 101.8, player=role)
    row = index._zzz_cinema_occurrences['rows'][hit.text_id]
    assert row['audio']['event'] == payload['records'][branch]['audio']['event']
    assert row['member_text_ids'] == ['shared-one']
    assert not observe(context, index, caption, 5, 102, player=None)


def test_proxy_remembers_confirmed_previous_session_and_replaces_it_after_two_frames(tmp_path):
    from backend.config import SettingsStore

    payload, index = source(tmp_path, player_branches=True)
    settings = SettingsStore(tmp_path / 'settings.json')
    scope = proxy_source_scope(index, 'account-one', 'unconfigured')
    context = ProxyEvidence()
    context.prepare('first-session', None)
    female_line = payload['records'][1]['texts']['en']
    male_line = payload['records'][0]['texts']['en']

    def role(text, seq, at, fresh=True):
        return context.observe(index, [text], frame=CinemaFrame(seq, at, at, fresh),
            now=at, stable_frames=2)

    assert not role(male_line, 1, 1)
    assert not role(male_line, 2, 1.2, fresh=False)
    assert not role(male_line, 3, 1.4)
    assert role(male_line, 4, 1.6) == 'male'
    settings.remember_zzz_cinema_proxy(scope, 'male')
    reopened = SettingsStore(settings.path).get()
    context.prepare('second-session', reopened.previous_zzz_cinema_proxy(scope))
    assert context.voice('unconfigured') == 'male'
    assert not role(female_line, 5, 1.8)
    assert context.voice('unconfigured') is None
    assert role(female_line, 6, 2) == 'female'
    assert context.voice('unconfigured') == 'female'
    other_account = proxy_source_scope(index, 'account-two', 'unconfigured')
    assert reopened.previous_zzz_cinema_proxy(other_account) is None


def test_native_capture_reuses_scoped_previous_player_and_registers_original(tmp_path):
    from backend.native_frame_admission import NativeFrameAdmissions
    from backend.prepared_session import PreparedCaptureSession

    payload, index = source(tmp_path, player_branches=True)
    session = PreparedCaptureSession(tmp_path / 'host')
    descriptor = {'game': 'zzz', 'request': payload[FIELD]['request'],
        'revision': payload['fingerprint'], 'ready': True}
    session.activate_source(tmp_path, index, descriptor, SimpleNamespace(has=lambda row: True), lambda *_: None)
    session._queue_original = lambda _: None
    generation = session.start()
    clock = [101.]
    admissions = NativeFrameAdmissions(clock=lambda: clock[0])
    app_owner = ('a' * 32, 0, ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 1))

    def frame(sequence, now, *, dialogue=(), cinema=(), scope=app_owner):
        clock[0] = now
        admissions.admit(session, generation, sequence, scope)
        with admissions.result(session, generation, sequence, scope) as receipt:
            return session.observe(generation, sequence, list(cinema), channel='cinematic',
                now=now, admission=receipt, zzz_dialogue=dialogue, zzz_captions=cinema)

    player_line = payload['records'][0]['texts']['en']
    assert not frame(1, 101., dialogue=[player_line])
    assert not frame(2, 101.2, dialogue=[player_line])
    generation = session.start()
    assert session.zzz_proxy.confirmed is None
    caption = payload['records'][2]['texts']['en']
    assert not frame(1, 201.1, cinema=[caption])
    assert not frame(2, 201.3, cinema=[caption])
    line, = frame(3, 201.5, cinema=[caption])
    _, saved = session.recordings.reference(line['id'])
    assert saved['source']['revision'] == descriptor['revision']
    assert saved['row']['audio']['event'] == payload['records'][0]['audio']['event']


def test_identical_chinese_anchors_never_choose_from_japanese_dub(tmp_path):
    _, index = source(tmp_path)
    context = CinemaContext()
    arm(context, index, locale='zh-Hans')
    advance_blank(context, index)
    assert not observe(context, index, index._records[2]['texts']['zh-Hans'], 12, 104.1)
    assert not context.active


@pytest.mark.parametrize('change', ['background', 'missing_frame', 'clock_gap', 'scope', 'source', 'request', 'rewind'])
def test_context_resets_before_any_conditional_recording(tmp_path, change):
    _, index = source(tmp_path)
    context = CinemaContext()
    arm(context, index)
    advance_blank(context, index)
    sequence, when, scope, fresh = 12, 104.1, 'session-one', True
    if change == 'background': fresh = False
    if change == 'missing_frame': sequence = 13
    if change == 'clock_gap': when = 111.
    if change == 'scope': scope = 'another-window-or-session'
    if change == 'source': index.publisher_generation = 'sophon-' + 'd' * 64
    if change == 'request': index.publisher_request_sha256 = 'f' * 64
    if change == 'rewind': when = 101.4
    assert not observe(context, index, index._records[2]['source_text'], sequence, when, scope=scope, fresh=fresh)


def test_conditional_row_roundtrips_to_real_original_adapter_without_provenance_bypass(tmp_path):
    payload, index = source(tmp_path)
    context = CinemaContext()
    arm(context, index, 1)
    advance_blank(context, index)
    hit, = observe(context, index, index._records[2]['source_text'], 12, 104.1)
    descriptor = {'game': 'zzz', 'revision': payload['fingerprint'], 'request': payload[FIELD]['request']}
    host = SimpleNamespace(audio_pool=None, service=SimpleNamespace(closed=False), owner=lambda: 'owner', blocked=set())
    voices = DesktopOriginalVoices(host, 'owner', descriptor, index)
    row = voices._row(hit)
    assert row and row['audio']['event'] == payload['records'][1]['audio']['event']
    assert voices._row(hit.model_copy(update={'publisher_occurrence_sha256': '0' * 64})) is None
    assert voices._row(hit.model_copy(update={'publisher_request_sha256': '0' * 64})) is None
    source_object = SimpleNamespace(ctx=SimpleNamespace(check=lambda: None))
    local = LocalOriginals.__new__(LocalOriginals)
    local.sources, local.codecs, local.keys = source_object, object(), _binding_keys(payload)
    assert local.has(row)
    assert not local.has({**row, 'audio': payload['records'][0]['audio']})
    # Immutable snapshot metadata is sufficient after restart; no mutable
    # capture hint or reconstructed arbitrary audio descriptor is serialized.
    assert row in recording_rows(payload)


def test_source_scope_or_media_tampering_cannot_create_conditional_keys(tmp_path):
    payload, _ = source(tmp_path)
    payload[FIELD]['region'] = 'cn'
    with pytest.raises(ValueError, match='identity'):
        recording_rows(payload)


def test_second_forward_caption_and_locale_switch_are_authored_not_numeric(tmp_path):
    _, index = source(tmp_path)
    context = CinemaContext()
    arm(context, index)
    advance_blank(context, index)
    first, = observe(context, index, index._records[2]['source_text'], 12, 104.1)
    for sequence in range(13, 24):
        assert not observe(context, index, '', sequence, 104.1 + (sequence - 12) * .25)
    second, = observe(context, index, index._records[3]['source_text'], 24, 107.1)
    assert first.text_id != second.text_id
    assert second.publisher_occurrence_sha256 == occurrence(index._zzz_cinema_occurrences['rows'][second.text_id])
    assert not observe(context, index, index._records[3]['texts']['en'], 25, 107.35)
    assert not context.active


def test_full_inventory_duplicate_disables_english_anchor_despite_distinct_pair(tmp_path):
    payload, _ = source(tmp_path)
    duplicate = {**payload['records'][2], 'text_id': 'unrelated-catalogue-owner',
        'texts': {**payload['records'][2]['texts'], 'en': payload['records'][0]['texts']['en']}}
    payload['records'].append(duplicate)
    (tmp_path / 'textmap.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    index = MultilingualTextIndex('zzz', tmp_path)
    index.publisher_generation = payload['fingerprint']
    index.publisher_request_sha256 = digest(payload[FIELD]['request'])
    context = CinemaContext()
    arm(context, index, locale='en')
    assert not context.active
    # The unrelated English duplicate does not invalidate the separate original
    # Japanese whole-text anchor; no audio-locale heuristic is involved.
    arm(context, index, locale='ja')
    assert context.active


def test_fresh_restart_does_not_restore_a_playing_instance(tmp_path):
    _, index = source(tmp_path)
    context = CinemaContext()
    arm(context, index)
    advance_blank(context, index)
    context = CinemaContext()
    assert not observe(context, index, index._records[2]['source_text'], 12, 104.1)


@pytest.mark.parametrize('variant', [0, 1])
@pytest.mark.parametrize('fault', [None, 'background', 'source', 'session', 'chinese', 'foreground_lost', 'region'])
def test_actual_capture_to_original_recording_chain(tmp_path, monkeypatch, variant, fault):
    """Real scan/capture/context/index/voice/retention calls, synthetic pixels/OCR.

    This proves the integration boundary, not native OCR/gameplay acceptance.
    The pre-existing RGB1 image has deliberately no acquisition timestamp.
    """
    import threading
    from PIL import Image
    from backend import capture as module
    from backend.config import SettingsStore
    from backend.storage import TranscriptStore
    from backend.windows import WindowInfo
    from backend.games import GAME_PROFILES
    from backend.models import CaptureRegion
    from backend.source_recordings import OriginalRecordings
    from backend.tests.test_desktop_original_audio import tone

    payload, index = source(tmp_path)
    settings = SettingsStore(tmp_path / 'settings.json')
    settings.save(settings.get().model_copy(update={'cinematic_region': CaptureRegion(left=0, top=0, width=1, height=1)}))
    transcript = TranscriptStore(tmp_path / 'transcript.sqlite')
    async def publish(*_): pass
    service = module.CaptureService(settings, index, None, transcript, publish, publish, publish, tmp_path / 'audio')
    service._executor.shutdown(wait=True)
    clock, caption = [101.1], ['']
    window = WindowInfo(123, 'Synthetic current game', 'owned-test.exe', (0, 0, 1000, 1000))
    monkeypatch.setattr(module, 'find_active_game_window', lambda _: (GAME_PROFILES['zzz'], window))
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(service, '_foreground_capture_handle', lambda: window.handle)
    # Real MSS adapter seam; deliberately no BackgroundCapture timestamp guess.
    image = Image.new('RGB', (1000, 1000), (120, 120, 120))
    class Grabber:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def grab(self, bounds):
            result = image.crop((0, 0, bounds['width'], bounds['height']))
            return SimpleNamespace(size=result.size, rgb=result.tobytes())
    monkeypatch.setattr(module.mss, 'mss', Grabber)
    service._background_capture = SimpleNamespace(frame=lambda _: image if fault == 'background' else None)
    class Engine:
        def recognize_pil(self, value):
            if value.width != value.height or not caption[0]: return {'lines': []}
            return {'lines': [{'text': caption[0], 'bounding_rect': {
                'x1': value.width * .25, 'x2': value.width * .75, 'x3': value.width * .75, 'x4': value.width * .25,
                'y1': value.height * .80, 'y2': value.height * .80, 'y3': value.height * .83, 'y4': value.height * .83}}]}
    service._engine = Engine()
    service._event_loop = object()
    service._queue_publication = lambda coroutine: coroutine.close()
    records = OriginalRecordings(tmp_path / 'recordings')
    local = LocalOriginals.__new__(LocalOriginals)
    local.keys, local.sources = _binding_keys(payload), SimpleNamespace(ctx=SimpleNamespace(check=lambda: None))
    extracted = []
    local.catalogue = SimpleNamespace(extract=lambda audio: extracted.append(audio['event']) or b'owned synthetic member')
    def decode(raw, audio, destination, *, cancelled):
        assert raw == b'owned synthetic member' and not cancelled()
        path = destination.with_suffix('.wav'); path.write_bytes(tone(100 + variant)); return path
    local.codecs = SimpleNamespace(resolve=decode)
    class Inline:
        def submit(self, call): call()
    host = SimpleNamespace(audio_pool=Inline(), service=SimpleNamespace(closed=False), owner=lambda: 'owner',
        blocked=set(), runtime=SimpleNamespace(transcript=transcript, accounts=SimpleNamespace(lock=threading.RLock())),
        profile_root=lambda: tmp_path / 'profile', recordings=lambda: records, source_for=lambda *_: local)
    descriptor = {'game': 'zzz', 'revision': payload['fingerprint'], 'request': payload[FIELD]['request'], 'ready': True}
    service.voice_assets = DesktopOriginalVoices(host, 'owner', descriptor, index)
    emitted = []
    def scan(when, value):
        clock[0], caption[0] = when, value
        emitted.extend(service._scan_once().emitted_lines)
    locale = 'zh-Hans' if fault == 'chinese' else 'ja'
    scan(101.1, index._records[variant]['texts'][locale])
    scan(101.35, index._records[variant]['texts'][locale])
    if fault == 'source': index.publisher_generation = 'sophon-' + 'd' * 64
    if fault == 'session': service.session_id = 'different-capture-session'
    if fault == 'foreground_lost': monkeypatch.setattr(service, '_foreground_capture_handle', lambda: None)
    if fault == 'region': settings.save(settings.get().model_copy(update={
        'cinematic_region': CaptureRegion(left=0, top=0, width=.99, height=.99)}))
    for n in range(3, 12): scan(101.35 + (n - 2) * .25, '')
    scan(104.1, index._records[2]['texts'][locale])
    for n in range(13, 24): scan(104.1 + (n - 12) * .25, '')
    scan(107.1, index._records[3]['texts'][locale])
    conditional = [line for line in emitted if line.text_id.startswith('zzz-cinema:')]
    assert len(conditional) == (2 if fault is None else 0)
    for line in conditional:
        saved = records.reference(line.id)[1]
        assert saved['row']['audio']['event'] == payload['records'][variant]['audio']['event']
        assert occurrence(saved['row']) == line.publisher_occurrence_sha256
        assert records.path(line.id).read_bytes() == tone(100 + variant)
        # Fresh retained-recording replay never needs a playing context or any
        # provider access, even once the publisher source is removed.
        fresh = OriginalRecordings(tmp_path / 'recordings')
        def unavailable(_): raise AssertionError('Retained audio must replay offline')
        assert fresh.materialize(line.id, unavailable).read_bytes() == tone(100 + variant)
