"""Local original PCK/event ownership with an explicit caller-bound reader.

The reader may request a separately consented metadata/source stage. This
catalogue never opens a connection, runs codecs or retains a global context.
"""
from pathlib import Path
import re
import struct

from . import zzz_publisher_cinematics as cinema
from .wwise_tables import package_tables_from_reader, bank_sources_from_reader, external_table, voice_hash
from .zzz_dialogue_records import voice_namespace


class Catalogue:
    def __init__(self, files, locale, publisher, read):
        self.files, self.locale, self.publisher, self._read = files, locale, publisher, read
        self.namespace = voice_namespace(locale).lower()
        folder = re.escape(cinema.VOICE_FOLDERS[locale])
        pattern = r'ZenlessZoneZero_Data/(?:StreamingAssets|Persistent)/Audio/Windows/Full/(?:' + folder + r'/)?[A-Za-z0-9_.-]+\.pck'
        if not files or any(not re.fullmatch(pattern, name) for name in files):
            raise ValueError('Original ZZZ packages cross the selected dub or edition.')
        self._tables, self._banks, self._external, self._external_by_id, self._entries = {}, {}, {}, {}, None

    def read(self, name, start, size):
        source = self.files[name]
        if (type(start) is not int or type(size) is not int or not 0 < size <= 64 * 1024**2
                or not 0 <= start <= source.size - size):
            raise ValueError('Original ZZZ audio range leaves its owner.')
        raw = self._read(source, start, size)
        if not isinstance(raw, bytes) or len(raw) != size:
            raise ValueError('Original ZZZ audio range is incomplete.')
        return raw

    def tables(self, name):
        if name not in self._tables:
            self._tables[name] = package_tables_from_reader(self.files[name].size,
                lambda start, size: self.read(name, start, size))
        return self._tables[name]

    def inventory(self, wanted):
        return cinema._inventory_from_files(self.files, self.locale, wanted, self.tables)

    def bank(self, name, bank_id, mode='direct'):
        key = name, bank_id, mode
        if key not in self._banks:
            languages, banks, _ = self.tables(name)
            entry, = [entry for (identifier, language), entry in banks.items()
                      if identifier == bank_id and languages[language] == self.namespace]
            if not 0 < entry.size <= 64 * 1024**2:
                raise ValueError('Original ZZZ cinematic bank is outside supported bounds.')
            self._banks[key] = cinema._read_bank(entry, lambda start, size: self.read(name, start, size),
                bank_id, self.namespace, mode, self.initial_buses)
        return self._banks[key]

    def dependency(self, name, bank_id):
        if not name.rpartition('/')[0].endswith('/Audio/Windows/Full'):
            raise ValueError('Original ZZZ dependency crosses the common-bank directory.')
        languages, banks, _ = self.tables(name)
        entry, = [entry for (identifier, language), entry in banks.items()
                  if identifier == bank_id and languages[language] == 'sfx']
        if not 0 < entry.size <= 64 * 1024**2:
            raise ValueError('Original ZZZ dependency is outside supported bounds.')
        bank_sources_from_reader(entry.size, lambda start, size: self.read(name, entry.offset + start, size),
                                 bank_id, language='sfx')

    def initial_buses(self):
        identity = cinema.wwise_hash(cinema.INITIAL_BANK_FILENAME.rsplit('.', 1)[0])
        banks, _, common = self.inventory({identity})
        if banks or set(common) != {identity}:
            raise ValueError('Original ZZZ initialization bank is missing or ambiguous.')
        name, entry = common[identity]
        return cinema.bus_parents_from_reader(entry.size,
            lambda start, size: self.read(name, entry.offset + start, size), identity)

    def externals(self):
        if self._entries is not None:return self._entries
        result = {}
        folder = '/Audio/Windows/Full/' + cinema.VOICE_FOLDERS[self.locale] + '/'
        for layer in ('StreamingAssets', 'Persistent'):
            current, ambiguous = {}, set()
            for name in sorted(name for name in self.files if name.split('/')[1] == layer and folder in name):
                if name not in self._external:
                    self._external[name] = external_table(name, self.files[name].size,
                        lambda start, size: self.read(name, start, size))
                    self._external_by_id[name] = {entry.file_id: entry for entry in self._external[name]}
                for entry in self._external[name]:
                    if entry.file_id in current:ambiguous.add(entry.file_id)
                    current[entry.file_id] = {'publisher': self.publisher, 'package': name}
            # A conflicting patch must not reveal a lower-priority base take.
            result.update(current)
            for identity in ambiguous:result.pop(identity, None)
        self._entries = result
        return result

    def bindings(self, links, registry):
        return cinema.bindings(Path('.'), self.publisher, self.locale, links, registry, catalogue=self)

    def recording(self, audio):
        if audio.get('publisher') != self.publisher or audio.get('locale') != self.locale:
            raise ValueError('Original ZZZ recording belongs to another source generation or dub.')
        if audio.get('matched_by') == 'publisher_cinematic_event':
            return cinema.recording(audio, Path('.'), catalogue=self)
        source = audio.get('source', '')
        if (not isinstance(source, str) or re.split(r'[/\\]', source, maxsplit=1)[0].lower() != self.namespace
                or f'{voice_hash(source):016x}' != audio.get('file_id')):
            raise ValueError('Original ZZZ sentence does not identify the selected dub.')
        name = audio['package']
        expected = {'publisher': self.publisher, 'package': name}
        if self.externals().get(voice_hash(source)) != expected:
            raise ValueError('Original ZZZ sentence has missing or ambiguous package ownership.')
        return name, self._external_by_id[name][voice_hash(source)]

    def extract(self, audio):
        name, entry = self.recording(audio)
        raw = self.read(name, entry.offset, entry.size)
        if (len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE'
                or len(raw) != struct.unpack_from('<I', raw, 4)[0] + 8):
            raise ValueError('Original ZZZ recording is not a complete Wwise source.')
        return raw
