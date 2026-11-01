"""Late codec discovery keeps newly prepared tools available without a restart."""
from pathlib import Path

from .media_tools import vgmstream_executable


class VoiceDecoder:
    """Shared playback dependency, with an explicit source/test path override."""

    @property
    def decoder(self) -> Path | None:
        return self._decoder if self._decoder is not None else vgmstream_executable()

    @decoder.setter
    def decoder(self, value: Path | None) -> None:
        self._decoder = value

    def decoder_available(self) -> bool:
        binary = self.decoder
        return binary is not None and binary.is_file()

    def require_decoder(self) -> Path:
        binary = self.decoder
        if binary is None or not binary.is_file():
            raise RuntimeError('Original voice decoder is unavailable. Prepare voice tools in Setup.')
        return binary
