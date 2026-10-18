"""Original Quantic MP3 blocks, preserving reservoirs and authored silence."""
import io
import subprocess
import wave


def decode_blocks(blocks, destination, *, executable, decode):
    # Decode contiguous MP3 runs together to preserve their frame reservoir.
    # NULL partitions retain their authored position as PCM silence.
    rate = 44100
    pcm = bytearray(len(blocks) * rate * 2)
    index = 0
    while index < len(blocks):
        if blocks[index] is None:
            index += 1; continue
        start = index
        run = []
        while index < len(blocks) and blocks[index] is not None:
            run.append(blocks[index]); index += 1
        encoded = b''.join(run)
        samples, encoded_rate = mp3_format(encoded)
        # FFmpeg's demuxer needs two consecutive frames to identify a stream.
        # A shipped single-frame tail is decoded with a duplicate probe frame;
        # discard the probe's PCM, retaining only the original frame's samples.
        probe = samples == 1152
        path = destination / f'run-{start}.mp3'; path.write_bytes(encoded * (2 if probe else 1))
        result = decode([str(executable), '-v', 'error', '-nostdin', '-i', str(path),
                                 '-f', 's16le', '-ac', '1', '-ar', str(rate), 'pipe:1'],
                                check=True, capture_output=True, timeout=90,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        decoded = result.stdout
        expected = (samples * rate + encoded_rate - 1) // encoded_rate
        if probe:
            decoded = decoded[:expected*2]
        # FFmpeg resamples original 32/48 kHz performances to the shared WAV
        # rate. Its final sample may round either way; larger differences
        # indicate a truncated stream rather than normal resampler rounding.
        if len(decoded) % 2 or abs(len(decoded)//2 - samples*rate/encoded_rate) > 1 or samples/encoded_rate > index-start+.1:
            raise ValueError('Original MP3 duration disagrees with authored partitions')
        length = min(len(decoded), (index-start)*rate*2)
        pcm[start*rate*2:start*rate*2+length] = decoded[:length]
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(pcm)
    return output.getvalue()


def mp3_samples(data):
    return mp3_format(data)[0]


def mp3_format(data):
    """Validate contiguous MPEG-1 Layer III frames and their common sample rate."""
    position, samples, rate = 0, 0, None
    bitrates = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
    while position < len(data):
        if position + 4 > len(data):
            raise ValueError('Incomplete original MPEG audio frame')
        header = int.from_bytes(data[position:position+4], 'big')
        bitrate, frequency = (header >> 12) & 15, (header >> 10) & 3
        if header >> 21 != 0x7ff or (header >> 19) & 3 != 3 or (header >> 17) & 3 != 1 or not bitrates[bitrate] or frequency == 3:
            raise ValueError('Unsupported original MPEG dialogue frame')
        frame_rate = (44100, 48000, 32000)[frequency]
        if rate is not None and rate != frame_rate:
            raise ValueError('Original MPEG dialogue sample rate changed within a stream')
        rate = frame_rate
        length = 144000 * bitrates[bitrate] // rate + ((header >> 9) & 1)
        if position + length > len(data):
            raise ValueError('Original MPEG dialogue frame exceeds its block')
        position += length
        samples += 1152
    if not samples:
        raise ValueError('Original MPEG dialogue is empty')
    return samples, rate

