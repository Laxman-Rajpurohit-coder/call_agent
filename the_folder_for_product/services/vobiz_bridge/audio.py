"""
Audio helpers for the Vobiz bridge.

Pure Python / stdlib only. (The stdlib ``audioop`` module was removed in Python 3.13, so it is not used.)
Telephony audio here is 8 kHz mono; one "frame" is 20 ms = 160 samples = 320 bytes of 16-bit PCM.
"""
import array
import sys
from typing import List

FRAME_BYTES = 320          # 20 ms of 8 kHz mono PCM16 - what the AudioSocket gateway expects
FRAME_S = 0.020

_BIAS = 0x84
_CLIP = 8159
_SEG_UEND = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)
_BIG = sys.byteorder == "big"


def _ulaw_to_linear(u: int) -> int:
    """G.711 mu-law byte -> 16-bit linear sample."""
    u = ~u & 0xFF
    t = ((u & 0x0F) << 3) + _BIAS
    t <<= (u & 0x70) >> 4
    return (_BIAS - t) if (u & 0x80) else (t - _BIAS)


def _linear14_to_ulaw(pcm_val: int) -> int:
    """14-bit linear sample -> G.711 mu-law byte."""
    if pcm_val < 0:
        pcm_val = -pcm_val
        mask = 0x7F
    else:
        mask = 0xFF
    if pcm_val > _CLIP:
        pcm_val = _CLIP
    pcm_val += _BIAS >> 2
    seg = 8
    for i, end in enumerate(_SEG_UEND):
        if pcm_val <= end:
            seg = i
            break
    if seg >= 8:
        return 0x7F ^ mask
    return ((seg << 4) | ((pcm_val >> (seg + 1)) & 0x0F)) ^ mask


_DECODE = [_ulaw_to_linear(i) for i in range(256)]
_ENCODE = bytes(_linear14_to_ulaw(i - 8192) for i in range(16384))   # index = (sample >> 2) + 8192


def ulaw_to_pcm16(data: bytes) -> bytes:
    """mu-law bytes -> little-endian 16-bit PCM."""
    out = array.array("h", [_DECODE[b] for b in data])
    if _BIG:
        out.byteswap()
    return out.tobytes()


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """Little-endian 16-bit PCM -> mu-law bytes."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if _BIG:
        samples.byteswap()
    return bytes(_ENCODE[(s >> 2) + 8192] for s in samples)


def pcm16_16k_to_8k(pcm: bytes) -> bytes:
    """Halve the sample rate by averaging sample pairs (cheap anti-aliasing)."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 4)])
    if _BIG:
        samples.byteswap()
    out = array.array("h", [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)])
    if _BIG:
        out.byteswap()
    return out.tobytes()


def interleave_stereo(left: bytes, right: bytes) -> bytes:
    """Two equal-length mono PCM16 buffers -> one interleaved stereo buffer."""
    l, r = array.array("h"), array.array("h")
    l.frombytes(left)
    r.frombytes(right)
    out = array.array("h", bytes(len(l) * 4))
    out[0::2] = l
    out[1::2] = r
    if _BIG:
        out.byteswap()
    return out.tobytes()


class FrameSlicer:
    """Re-cuts an arbitrary byte stream (any chunk size) into exact fixed-size frames."""

    def __init__(self, frame_bytes: int = FRAME_BYTES):
        self._n = frame_bytes
        self._buf = bytearray()

    def push(self, data: bytes) -> List[bytes]:
        self._buf.extend(data)
        frames = []
        while len(self._buf) >= self._n:
            frames.append(bytes(self._buf[: self._n]))
            del self._buf[: self._n]
        return frames

    @property
    def pending(self) -> int:
        return len(self._buf)
