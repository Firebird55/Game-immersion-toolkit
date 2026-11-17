"""Authored synthetic mixed events; no game banks, media, keys or IDs."""
import struct

import pytest

from backend.wuthering_bank import SceneSource, scene_sources, song_sources
from backend.tests.test_wuthering_bank import base, bank, children, gendered, play, sound, u32


def compressor(plugin=0x006c0003, *, value=-15., extra=bytes(7)):
    return u32(plugin) + u32(31) + struct.pack('<7f', value, 4., .01, .1, 1., 0., 0.) + b'\1\0\1' + extra


def effected_base(parent=0):
    return bytes([0, 1, 0, 0]) + u32(70) + b'\1' + base(parent)[2:]


def track(*, parent=0, localized=False, callback=0, tail=None):
    source = b'\x01\0\x14\0\x02' + u32(404) + bytes(8) + bytes([9 if localized else 8])
    clip = u32(0) + u32(404) + u32(0) + u32(callback) + struct.pack('<4d', 0., 0., 0., 1000.)
    return (u32(1) + source + b'\0' + u32(1) + clip + u32(1) + u32(0)
            + base(parent, tail=tail) + b'\0' + struct.pack('<i', 0))


def stop(target=40, *, bus=0, flags=6, exceptions=b'\0'):
    return b'\x03\x01' + u32(target) + bytes([bus, 1, 59]) + u32(2000) + bytes([0, 4, flags]) + exceptions


def post(target=80, delay=100):
    return b'\x03\x21' + u32(target) + bytes([0, 1, 58]) + u32(delay) + b'\0'


def music_selector(leaf):
    return (b'\0' + base() + children([40]) + struct.pack('<ddfBBB', 0., 0., 120., 4, 4, 0)
            + u32(0) + u32(0) + b'\0' + u32(0) + u32(12) + b'\0'
            + struct.pack('<IIHH', 0, leaf, 100, 100))


def mixed(*, change=None, selector=False, posted_selector=False):
    nodes = {key: (kind, data) for kind, key, data in gendered(default='female')}
    common = bytearray(sound(303, 60)); common[17] = 8
    nodes.update({
        40: (11, track(parent=42 if selector else 0)),
        60: (7, effected_base() + children([61])), 61: (2, bytes(common)),
        70: (17, compressor()), 51: (3, play(61)), 52: (3, stop(42 if selector else 40)),
        53: (3, post()), 54: (3, play(42 if posted_selector else 40)),
        80: (4, bytes(7) + b'\1' + u32(54)),
    })
    if selector:
        nodes[42] = 12, music_selector(999)
    if change:
        change(nodes)
    return bank([(kind, key, data) for key, (kind, data) in nodes.items()], actions=(50, 51, 52, 53))


EXPECTED = (SceneSource(102, 'female', 0), SceneSource(101, 'male', 0))


def test_common_companion_actions_preserve_the_exact_immediate_protagonist_sources():
    assert scene_sources(mixed(), 'owned_scene', {101, 102}) == EXPECTED
    assert scene_sources(mixed(), 'owned_scene', iter([101, 102])) == EXPECTED
    assert not scene_sources(mixed(), 'owned_scene', {101})
    assert not song_sources(mixed(), 'owned_scene', {303, 404})
    assert not scene_sources(mixed(), None, {101, 102})


def test_an_unexecuted_ancestor_selector_is_not_falsely_resolved_as_played_music():
    assert scene_sources(mixed(selector=True), 'owned_scene', {101, 102}) == EXPECTED
    assert not scene_sources(mixed(selector=True, posted_selector=True), 'owned_scene', {101, 102})


@pytest.mark.parametrize('target', [10, 20, 30])
def test_a_stop_cannot_target_the_voice_or_any_voice_ancestor(target):
    assert not scene_sources(mixed(change=lambda n: n.update({52: (3, stop(target))})), 'owned_scene', {101, 102})


@pytest.mark.parametrize('replacement', [
    stop(bus=1), stop(flags=128), stop(exceptions=b'\1' + u32(30)),
    stop() + b'\0', post(80, 300001), post(900),
])
def test_unknown_action_scope_flags_external_events_or_trailing_bytes_refuse(replacement):
    key = 53 if replacement[:2] == b'\x03\x21' else 52
    assert not scene_sources(mixed(change=lambda n: n.update({key: (3, replacement)})), 'owned_scene', {101, 102})


@pytest.mark.parametrize('replacement', [
    compressor(plugin=0x77770003), compressor(value=float('nan')),
    compressor(extra=b'\1' + bytes(6)), compressor(extra=b'\0\1' + bytes(5)),
    compressor(extra=bytes(3) + b'\1' + bytes(3)), compressor() + b'\0',
])
def test_only_a_complete_static_stock_compressor_is_allowed_on_the_common_subtree(replacement):
    assert not scene_sources(mixed(change=lambda n: n.update({70: (17, replacement)})), 'owned_scene', {101, 102})


def test_the_same_compressor_on_a_voice_ancestor_is_still_unsupported():
    assert not scene_sources(mixed(change=lambda n: n.update({20: (7, effected_base() + children([30]))})),
                             'owned_scene', {101, 102})


@pytest.mark.parametrize('replacement', [track(localized=True), track(callback=123),
    track(tail=bytes.fromhex('00000000000000010000000000000100'))])
def test_played_music_cannot_hide_a_localized_source_callback_or_dynamic_property(replacement):
    assert not scene_sources(mixed(change=lambda n: n.update({40: (11, replacement)})), 'owned_scene', {101, 102})


def test_delayed_or_child_posted_voice_is_not_an_immediate_scene_source():
    delayed = play(30)[:7] + bytes([1, 58]) + u32(100) + play(30)[8:]
    assert not scene_sources(mixed(change=lambda n: n.update({50: (3, delayed)})), 'owned_scene', {101, 102})
    assert not scene_sources(mixed(change=lambda n: n.update({54: (3, play(30))})), 'owned_scene', {101, 102})
    assert not scene_sources(mixed(change=lambda n: n.update({10: (2, sound(101, 30, delay=.1))})),
                             'owned_scene', {101, 102})


def test_nested_events_and_shared_source_hierarchies_cannot_cross_into_the_voice():
    assert not scene_sources(mixed(change=lambda n: n.update({54: (3, post())})), 'owned_scene', {101, 102})
    assert not scene_sources(mixed(change=lambda n: n.update({40: (11, track(parent=20))})), 'owned_scene', {101, 102})
