"""Isolated ASR worker: do not import this module into the VAD process."""
import json
from pathlib import Path
import re
import sys
import wave


def main():
    import numpy as np
    import sherpa_onnx

    model, source = map(Path, sys.argv[1:3])
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model), tokens=str(model.parent/'tokens.txt'),
        num_threads=2, language='zh', use_itn=True)
    with wave.open(str(source)) as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32)/32768
        samples = samples.reshape(-1,audio.getnchannels()).mean(axis=1)
        stream = recognizer.create_stream()
        stream.accept_waveform(audio.getframerate(), samples)
    recognizer.decode_stream(stream)
    text = re.sub(r'<\|.*?\|>', '', stream.result.text).strip()
    # ASCII escaping makes the protocol independent of Windows' console codepage.
    print(json.dumps({'text': text}))


if __name__ == '__main__':
    main()
