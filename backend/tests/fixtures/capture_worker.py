"""Authored subprocess fixture: exercises IPC and exit/hang cleanup without GPU."""
import os
import struct
import sys
import time

mode = sys.argv[1]
count = 0
while sys.stdin.buffer.read(1) == b'f':
    if mode == 'crash':
        os._exit(37)
    if mode == 'hang':
        time.sleep(60)
    if mode == 'oversized':
        sys.stdout.buffer.write(struct.pack('!4sIII', b'RGB1', 16384, 8640, 16384 * 8640 * 3))
        sys.stdout.buffer.flush()
    elif mode == 'truncated':
        sys.stdout.buffer.write(struct.pack('!4sIII', b'RGB1', 2, 1, 6) + b'\xff')
        sys.stdout.buffer.flush()
        os._exit(1)
    else:
        color = b'\xff\0\0' if count == 0 else b'\0\xff\0'
        sys.stdout.buffer.write(struct.pack('!4sIII', b'RGB1', 2, 1, 6) + color * 2)
        sys.stdout.buffer.flush()
        count += 1
