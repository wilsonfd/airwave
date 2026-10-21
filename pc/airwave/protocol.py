# -*- coding: utf-8 -*-
"""AirWave wire protocol.

The protocol is deliberately tiny so the phone can decode it on a real-time
thread without allocations beyond the packet itself.

Client -> PC
    b"HELLO"                register / keep-alive (sent every ~750 ms)
    b"BYE"                  leave immediately

PC -> Client
    [0x01][len:uint16 BE][JSON]      stream metadata (rate/channels/packet size)
    [0x02][seq:uint32 BE][PCM]       one audio packet, signed 16-bit LE interleaved

The JSON metadata is resent on every HELLO and periodically while streaming, so
a single lost UDP datagram can never leave the phone stuck without a format.
"""
from __future__ import annotations

import json
import struct
from typing import Any, Dict

META = 0x01
AUDIO = 0x02
DEFAULT_PORT = 13666
PROTOCOL_VERSION = 2
HELLO = b"HELLO"
BYE = b"BYE"


def build_meta(rate: int, channels: int, packet_frames: int,
               stream_id: str, server_name: str) -> bytes:
    payload: Dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "rate": int(rate),
        "channels": int(channels),
        "width": 2,
        "packet_frames": int(packet_frames),
        "packet_ms": round(packet_frames * 1000.0 / rate, 2),
        "stream_id": stream_id,
        "name": server_name,
        "codec": "pcm_s16le",
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return bytes((META,)) + struct.pack(">H", len(raw)) + raw


def build_audio(seq: int, pcm: bytes) -> bytes:
    return bytes((AUDIO,)) + struct.pack(">I", seq & 0xFFFFFFFF) + pcm


def parse_control(data: bytes) -> str | None:
    """Return 'hello' / 'bye' for a control datagram, else None."""
    head = data[:16].upper()
    if head.startswith(HELLO):
        return "hello"
    if head.startswith(BYE):
        return "bye"
    return None
