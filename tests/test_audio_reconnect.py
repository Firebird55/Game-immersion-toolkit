from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.audio import AudioCaptureService


class AudioReconnectTests(unittest.TestCase):
    def test_active_loopback_without_callbacks_is_reopened(self):
        with tempfile.TemporaryDirectory() as folder, patch("backend.audio.FireRedVad", return_value=Mock()):
            service = AudioCaptureService(Path(folder))
            device = {"index": 3, "name": "Old output [Loopback]",
                      "defaultSampleRate": 48000, "maxInputChannels": 2}
            stale = Mock()
            stale.get_default_wasapi_loopback.return_value = device
            stale.open.return_value.is_active.return_value = True
            fresh = Mock()
            fresh.get_default_wasapi_loopback.return_value = device
            opened = 0

            def new_audio():
                nonlocal opened
                opened += 1
                if opened == 2:
                    service._stop.set()
                    return fresh
                return stale

            try:
                with patch("backend.audio.pyaudio.PyAudio", side_effect=new_audio), \
                     patch("backend.audio.time.monotonic", side_effect=itertools.count()), \
                     patch.object(service._stop, "wait", return_value=False):
                    service._run()
                self.assertEqual(opened, 2)
                stale.open.return_value.close.assert_called_once()
                stale.terminate.assert_called_once()
            finally:
                service._analysis_executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
