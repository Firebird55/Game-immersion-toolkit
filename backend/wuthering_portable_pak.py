"""Original PAK adapter with explicit portable range and Oodle providers."""
from .preparation_errors import PreparationFailure
from .wuthering_release_pak import LIMIT, Package


def _missing_oodle(_blocks):
    raise PreparationFailure('missing_decoder',
        'The Wuthering package needs its app-native Oodle decoder. Existing data is retained.')


class PortablePackage(Package):
    def __init__(self, *args, range_reader, oodle_decoder=None, **kwargs):
        if not callable(range_reader) or oodle_decoder is not None and not callable(oodle_decoder):
            raise ValueError('Portable providers must be callable.')
        self._range_reader = range_reader
        super().__init__(*args, oodle_decoder=oodle_decoder or _missing_oodle, **kwargs)

    def range(self, offset, size):
        if type(offset) is not int or type(size) is not int or not 0 < size <= LIMIT or not 0 <= offset <= self.size - size:
            raise ValueError('Invalid original package range.')
        data = self._range_reader(self.url, self.size, offset, size)
        if not isinstance(data, bytes) or len(data) != size:
            raise ValueError('The original range provider returned incomplete bytes.')
        return data
