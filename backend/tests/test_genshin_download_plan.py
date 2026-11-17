"""Download quotes use original sizes, deduplicated chunks and explicit bounds."""
import json
from types import SimpleNamespace

import pytest

from backend import genshin_download_plan as quotes, genshin_publisher as publisher
from backend.hoyo_publisher_voice import descriptor
from backend.tests.test_genshin_official_text import generation


def fixtures():
    def unread(*args): pytest.fail('A size quote read a large game payload')
    chunk = lambda offset, digest, wire: (offset, 512, wire, 'a' * 16 + '_' + digest * 32, digest * 32)
    native = SimpleNamespace(size=1024, digest='a' * 32, chunks=(chunk(0, 'b', 5), chunk(512, 'c', 3)), read=unread)
    shared = SimpleNamespace(size=512, digest='b' * 32, chunks=(chunk(0, 'b', 6),), read=unread)
    http = SimpleNamespace(size=70, digest='d' * 32, read=unread)
    build = {'channel': 'genshin-global', 'version': '9.4.0', 'manifests': {'game': ['game'], 'ja-jp': ['voice']}}
    rows = {}
    for name, size, digest in [(quotes.INDEX_PACKAGE, 100, 'e'), ('blocks/03/99.blk', 200, 'f'), ('blocks/00/12.blk', 300, '9')]:
        rows[name] = {'remoteName': name, 'fileSize': size, 'md5': digest * 32}
    tables, _, _ = generation()
    return build, native, {'ja': {'one': shared, 'two': http}}, rows, tables.catalog


def test_full_cache_quote_deduplicates_real_cache_keys_and_keeps_an_upper_bound():
    build, native, voice, designs, _ = fixtures()
    result = quotes.plan(build, native, voice, designs, study_locales=('ja',), target_locales=('en',))
    assert result['text_selection'] == 'upper-bound' and result['selected_design_packages'] == 3
    assert result['transfer_bytes_upper_bound'] == 9 + 70 + 600
    shared, = [row for row in result['objects'] if row['cache_key'] == 'sophon-chunk:' + 'b' * 32]
    assert shared['wire_bytes'] == 6 and shared['cache_bytes'] == 512 and shared['parts'] == ['native', 'voice']
    assert not result['cache_reuse_subtracted'] and not result['complete_game_quote']
    assert 'derived-dialogue-index' in result['unquoted_components']


def test_authenticated_same_generation_catalog_narrows_text_packages_before_payload_reads():
    build, native, voice, designs, catalog = fixtures()
    # The fixture owns EN only, so select EN voice/text for this scoped quote.
    result = quotes.plan(build, native, {'en': voice['ja']}, designs, study_locales=('en',),
                         catalog=catalog, catalog_publisher=descriptor(build)[0])
    assert result['text_selection'] == 'exact' and result['selected_design_packages'] == 2
    assert result['transfer_bytes_upper_bound'] == 9 + 70 + 300
    assert result['decoded_containers_bytes_upper_bound'] == 2 * 512 * 1024**2
    assert result['resident_bytes_upper_bound'] == result['official_object_cache_bytes_upper_bound'] + 1024 + 2 * 512 * 1024**2
    with pytest.raises(ValueError):
        quotes.plan(build, native, {'en': voice['ja']}, designs, study_locales=('en',),
                    catalog=catalog, catalog_publisher='sophon-' + '0' * 64)


def test_shared_chinese_pack_is_counted_once_for_both_official_subtitle_editions():
    build, native, voice, designs, _ = fixtures()
    once = quotes.plan(build, native, {'zh-Hans': voice['ja']}, designs, study_locales=('zh-Hans',))
    twice = quotes.plan(build, native, {'zh-Hans': voice['ja'], 'zh-Hant': voice['ja']}, designs,
                        study_locales=('zh-Hans', 'zh-Hant'))
    assert twice['transfer_bytes_upper_bound'] == once['transfer_bytes_upper_bound']
    assert twice['text_codes'] == ['CHS', 'CHT']


def test_conflicting_chunk_ownership_cannot_underquote_a_download():
    build, native, voice, designs, _ = fixtures()
    voice['ja']['one'].chunks = ((0, 400, 6, 'a' * 16 + '_' + 'b' * 32, 'b' * 32),)
    voice['ja']['one'].size = 400
    with pytest.raises(ValueError): quotes.plan(build, native, voice, designs, study_locales=('ja',))


def test_publisher_preflight_only_reads_discovery_and_small_manifests(tmp_path, monkeypatch):
    build, native, voice, designs, _ = fixtures()
    from backend import sophon_assets
    build['manifests'][sophon_assets.VOICE_FIELDS['ja']] = ['voice']
    monkeypatch.setattr(publisher, '_release', lambda region: build)
    monkeypatch.setattr(publisher.sophon, 'manifest', lambda directory, channel, spec, suffix:
        {'GenshinImpact.exe': native} if suffix == ('.exe',) else
        {'GenshinImpact_Data/StreamingAssets/AudioAssets/Japanese/External0.pck': voice['ja']['one']})
    monkeypatch.setattr(publisher.hotfix, 'files', lambda directory, build, locale, regular: regular)
    monkeypatch.setattr(publisher.hotfix, 'index', lambda *args: b'\n'.join(json.dumps(row).encode() for row in designs.values()))
    result = publisher.preflight(tmp_path, study_locales=('ja',), target_locales=('en',))
    assert result['publisher'] == descriptor(build)[0] and result['transfer_bytes_upper_bound'] == 9 + 600
