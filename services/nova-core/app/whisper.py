"""Wyoming protocol client for speech-to-text via wyoming-whisper.
Also provides WAV-to-PCM extraction for audio uploaded from the dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import struct

log = logging.getLogger("nova-core")

WHISPER_HOST = "whisper"
WHISPER_PORT = 10300


def wav_to_pcm(wav_data: bytes) -> tuple[bytes, int]:
    """Extract raw PCM data and sample rate (Hz) from a WAV file.
    
    Expects a standard 44-byte RIFF/WAVE header followed by PCM data.
    Returns (pcm_bytes, sample_rate).
    """
    if len(wav_data) < 44:
        raise ValueError("WAV data too short (minimum 44 bytes)")
    sample_rate = struct.unpack_from("<I", wav_data, 24)[0]
    data_size = struct.unpack_from("<I", wav_data, 40)[0]
    pcm_data = wav_data[44 : 44 + data_size]
    return pcm_data, sample_rate


async def transcribe_audio(pcm_data: bytes, sample_rate: int = 16000) -> str:
    """Send raw PCM audio to wyoming-whisper and return the transcription text.
    
    Connects via the Wyoming protocol (TCP), streams the audio, and returns
    the first hypothesis.  Returns an empty string on any failure.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(WHISPER_HOST, WHISPER_PORT),
            timeout=5,
        )
    except (asyncio.TimeoutError, OSError) as exc:
        log.warning("Cannot connect to wyoming-whisper at %s:%s: %s",
                     WHISPER_HOST, WHISPER_PORT, exc)
        return ""

    try:
        header = json.dumps({"type": "audio-start", "data": {
            "rate": sample_rate, "width": 2, "channels": 1,
        }})
        await _send(writer, header.encode("utf-8"))
        await _send(writer, json.dumps({"type": "audio-chunk"}).encode("utf-8"), pcm_data)
        await _send(writer, json.dumps({"type": "audio-stop"}).encode("utf-8"))
        await writer.drain()

        transcripts: list[str] = []
        while True:
            try:
                msg_type, data = await asyncio.wait_for(
                    _recv(reader), timeout=30
                )
                if msg_type == "transcript":
                    text = data.get("text", "") if isinstance(data, dict) else ""
                    if text:
                        transcripts.append(text)
                    break
                elif msg_type is None:
                    break
            except asyncio.TimeoutError:
                log.warning("Timeout waiting for transcript from whisper")
                break

        return transcripts[0] if transcripts else ""
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _send(writer, header_bytes: bytes, payload: bytes = b""):
    """Send a Wyoming protocol message."""
    writer.write(struct.pack("<I", len(header_bytes)))
    writer.write(header_bytes)
    if payload:
        writer.write(payload)


async def _recv(reader) -> tuple[str | None, dict]:
    """Read one Wyoming protocol message.  Returns (type, data_dict)."""
    try:
        raw = await reader.readexactly(4)
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        return None, {}

    header_len = struct.unpack("<I", raw)[0]
    if header_len == 0:
        return None, {}

    try:
        header_bytes = await reader.readexactly(header_len)
    except (asyncio.IncompleteReadError, ConnectionError):
        return None, {}

    try:
        header = json.loads(header_bytes)
    except json.JSONDecodeError:
        return None, {}

    msg_type = header.get("type", "")
    data = header.get("data", {})

    # Drain payload bytes if indicated by the server
    payload_size = data.get("payload_bytes", 0) if isinstance(data, dict) else 0
    if payload_size > 0:
        try:
            await reader.readexactly(payload_size)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    return msg_type, data
