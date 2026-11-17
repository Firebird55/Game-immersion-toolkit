"""Compose original Star Rail acquisition and the existing dialogue catalog API.

Text and recordings always belong to the same original publisher generation.
No third-party text publication is polled here.
"""
from pathlib import Path
import re

from . import sophon_assets as sophon, hoyo_publisher_voice as voices, starrail_hotfix as hotfix
from . import starrail_native_preparation as native, starrail_original_discovery as discovery
from .starrail_native_configs import Descriptions
from .starrail_native_index import NativeIndex
from .starrail_original_catalog import OriginalCatalog
from .starrail_original_configs import OriginalConfigs
from .starrail_original_tables import OriginalTables
from .starrail_metadata import _check
from . import starrail_metadata as metadata
from .runtime_bundle import discover_layout
from .game_tools import _atomic_file

# Required semantic tables in the existing dialogue consumer, not a release or
# content inventory. Their current fields/paths come from original native data.
TABLES = frozenset({'ActivityHipplenSentence', 'AudioBookData', 'AvatarAtlas', 'ChimeraTalk',
    'ClockParkTalkText', 'CutSceneConfig', 'IdleLiveEventSentence', 'IdleLiveMessageContent',
    'LocalbookConfig', 'LoopCGConfig', 'MessageItemConfig', 'MessageItemTextOverride', 'PerformanceVideo',
    'RestaurantMessageConfig', 'RogueDialogueOptionDisplay', 'TalkSentenceConfig', 'TalkSentenceMultiVoice',
    'TarotBookSentence', 'VideoConfig', 'VoiceAtlas', 'VoiceConfig'})
LOGIC = ('starrail_original_provider.py', 'starrail_original_catalog.py', 'starrail_caption_compat.py',
         'starrail_original_configs.py', 'starrail_native_configs.py', 'starrail_native_usages.py')


def _catalog_identity(generation):
    layout = discover_layout()
    logic = (layout.source_commit if layout.mode == 'bundle' else
        metadata._identity({name: metadata._hash(Path(__file__).with_name(name)) for name in LOGIC}))
    return metadata._identity({'native': generation.identity, 'catalog_logic': logic})


def release(tools, region='global'):
    _check(region in {'global', 'cn'})
    tools = Path(tools)
    build = sophon.release('starrail-' + region)
    generation = native.prepare(tools / 'starrail-original-native' / region, build, TABLES)
    return discovery.prepare(tools / 'sophon', build, generation.routes), generation


def _movie_source(build, revision, stale):
    _check(revision is None or isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision))
    _check(type(stale) is bool)
    build = dict(build)
    if revision:
        build['movie_format_revision'] = revision
    if stale:
        build['movie_format_metadata_stale'] = True
    return build


def _content_source(build, mode):
    _check(mode in {'text', 'text-audio'})
    return build | {'content_mode': 'text'} if mode == 'text' else build


def fingerprint(tools, region='global', *, format_revision=None, format_metadata_stale=False, content_mode='text-audio'):
    build = _movie_source(release(tools, region)[0], format_revision, format_metadata_stale)
    return voices.descriptor(_content_source(build, content_mode))[0]


def current(tools, stamp, region='global', **kwargs):
    return fingerprint(tools, region, **kwargs) == stamp


def prepare(data_dir, region='global', *, format_revision=None, format_metadata_stale=False, content_mode='text-audio'):
    """Prepare original data; optionally reuse a supplied frozen format revision.

    A format revision is an existing immutable format description, not a live
    movie metadata lookup. Native movie-parameter discovery remains separate.
    Failure never publishes a release receipt or replaces a language snapshot.
    """
    _check(format_revision is None or isinstance(format_revision, str)
           and re.fullmatch(r'[0-9a-f]{40}', format_revision))
    _check(content_mode in {'text', 'text-audio'} and (content_mode != 'text' or
           format_revision is None and not format_metadata_stale))
    tools = Path(data_dir) / 'tools'
    build, generation = release(tools, region)
    build = _content_source(_movie_source(build, format_revision, format_metadata_stale), content_mode)
    directory = tools / 'sophon'
    # Dispatch authenticates all five marker identities. These three index
    # bodies supply this catalog; ASB/Lua bodies are not consumed by its readers.
    for name in (('design', 'video') if content_mode == 'text' else ('design', 'audio', 'video')):
        hotfix.index(directory, build, name)
    movies = hotfix.movie_files(directory, build)
    tables = OriginalTables(directory, build, descriptions=generation.tables)
    configs = OriginalConfigs(tables, Descriptions(NativeIndex(generation.native)))
    catalog = OriginalCatalog(tables, configs, movies, revision='original-' + _catalog_identity(generation), build=build)
    stamp, raw = voices.descriptor(build)
    catalog.revision_title = f"{build['version']} / DesignV {build['hotfix']['indexes']['design'][0]}"
    catalog.movie_audio_source = directory, stamp, format_revision
    catalog.movie_format_metadata_stale = format_metadata_stale
    for name in sorted(TABLES):
        catalog.file('ExcelOutput/' + name + '.json')
    # Force every currently required config and caption description before
    # publishing the reusable release descriptor.
    catalog.caption_scripts()
    _atomic_file(directory / 'releases' / stamp, raw)
    return stamp, catalog
