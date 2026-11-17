"""Original table/configuration adapter; no third-party data fallback."""
import re

from . import hoyo_dialogue as common, starrail_design as design
from .starrail_caption_compat import LEGACY_IDENTITIES
from .starrail_metadata import _check
from .starrail_original_configs import decode
from .xxhash64 import xxhash64


def _legacy(value):
    _check(isinstance(value, dict) and len(value) <= 4096)
    result = {}
    for filename, identity in value.items():
        _check(isinstance(filename, str) and re.fullmatch(r'[A-Za-z0-9_-]+_Caption\.json', filename)
               and identity == filename[:-len('_Caption.json')] and identity not in result.values())
        result[filename] = identity
    return result


class OriginalCatalog:
    """Provide the existing dialogue API using independently acquired originals.

    This adapter alone does not enable the normal publisher lifecycle. The
    caller must authenticate matching native/table/index generations first.
    """
    text_locales = {locale: ('Main' + code, code) for locale, code in common.TEXT_LOCALES.items()}

    def __init__(self, tables, configs, movie_files, *, revision, build, legacy=None):
        self.tables, self.configs, self.movie_files = tables, configs, movie_files
        self.build = build
        self.revision, self.revision_title = revision, ''
        self.legacy = _legacy(LEGACY_IDENTITIES if legacy is None else legacy)
        self.legacy.update({name: name[:-len('_Caption.json')] for name in design._LEGACY_NAMED_IDENTITIES})
        self.caption_identities, self.caption_identity_aliases, self.unresolved_caption_paths = {}, {}, []
        self._files, self._captions = {}, None

    def file(self, relative, *, optional=False):
        if relative not in self._files:
            self._files[relative] = (self.tables.file(relative, optional=optional)
                if relative.startswith(('ExcelOutput/', 'TextMap/')) else self.configs.file(relative))
        return self._files[relative]

    def _mission_paths(self, videos):
        tasks = set()
        for row in videos:
            if not row.get('CaptionPath'):
                continue
            path = row['VideoPath']
            variants = [path[:-4] + suffix + '.usm' for suffix in ('_m', '_f')] if row.get('IsPlayerInvolved') else [path]
            for variant in variants:
                asset = self.movie_files.get(variant.casefold())
                if asset:
                    tasks.update(asset.task_ids)
        return {row['PerformancePath'] for row in self.file('ExcelOutput/PerformanceVideo.json')
                if (match := re.fullmatch(r'Config/Level/Mission/([0-9]+)/Act/Act[0-9]+\.json', row['PerformancePath']))
                and int(match[1]) in tasks}

    def _overrides(self, value, videos, paths, depth=0):
        _check(depth <= 128)
        if isinstance(value, dict):
            if value.get('$type') == 'RPG.GameCore.PlayVideo' and value.get('VideoID') in videos and value.get('OverrideCaptionPath'):
                paths.add(value['OverrideCaptionPath'])
            for child in value.values():
                self._overrides(child, videos, paths, depth + 1)
        elif isinstance(value, list):
            for child in value:
                self._overrides(child, videos, paths, depth + 1)

    def _caption(self, data):
        value = decode(data, self.configs.descriptions, root='RPG.GameCore.VideoCaptionConfig')
        return self._caption_value(value)

    @staticmethod
    def _caption_value(value):
        rows = value.get('CaptionList', [])
        _check(isinstance(rows, list))
        for row in rows:
            _check(isinstance(row.get('CaptionTextID'), dict) and type(row['CaptionTextID'].get('Hash')) is int
                   and row['CaptionTextID']['Hash'] > 0 and 0 <= row.get('StartTime', 0) < row.get('EndTime', 0))
        return value | {'CaptionList': rows}

    def caption_scripts(self):
        if self._captions is not None:
            return self._captions
        videos = self.file('ExcelOutput/VideoConfig.json')
        paths = {row['CaptionPath'] for rows in (videos, self.file('ExcelOutput/CutSceneConfig.json'),
                     self.file('ExcelOutput/LoopCGConfig.json')) for row in rows if row.get('CaptionPath')}
        available = {row['VideoID'] for row in videos if row.get('CaptionPath')}
        for path in sorted(self._mission_paths(videos)):
            self._overrides(self.file(path), available, paths)
        published, keys = {}, {}
        for path in sorted(paths):
            filename = design.caption_filename(path)
            key = xxhash64(self.configs.descriptions.binary_path(path).encode('utf-8'))
            _check(key not in keys and filename not in published)
            keys[key] = filename
            published[filename] = self._caption_value(self.file(path))
        identities, unresolved = {}, []
        extras = design.extra_captions(self.tables.directory, self.build, published, paths,
            identities=identities, unresolved=unresolved, package_reader=self.tables._package, decoder=self._caption,
            resource_id=lambda path: xxhash64(self.configs.descriptions.binary_path(path).encode('utf-8')),
            **({'fetch': self.tables.fetch} if getattr(self.tables, 'fetch', None) is not None else {}))
        scripts = {**published, **extras}
        aliases = {}
        legacy_keys = {xxhash64(self.configs.descriptions.binary_path('Config/CutSceneCaption/' + filename).encode('utf-8')): identity
                       for filename, identity in self.legacy.items()}
        _check(len(legacy_keys) == len(self.legacy))
        for filename in scripts:
            match = re.fullmatch(r'design_([0-9a-f]{16})_Caption\.json', filename)
            key = int(match[1], 16) if match else xxhash64(self.configs.descriptions.binary_path(
                'Config/' + filename if filename.startswith('BattleCollegeCaption/')
                else 'Config/CutSceneCaption/' + filename).encode('utf-8'))
            identity = legacy_keys.get(key, f'design_{key:016x}')
            identities[filename] = identity
            if key in legacy_keys and filename != identity + '_Caption.json':
                aliases[filename] = identity
        _check(len(set(identities.values())) == len(identities))
        self.caption_identities, self.caption_identity_aliases = identities, aliases
        self.unresolved_caption_paths = unresolved
        self._captions = list(scripts.items())
        return self._captions
