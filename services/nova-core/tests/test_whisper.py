import pytest
import struct
from unittest.mock import AsyncMock, MagicMock, patch
from app.whisper import wav_to_pcm, transcribe_audio


def _make_wav(sample_rate: int = 16000, pcm_data: bytes | None = None) -> bytes:
    if pcm_data is None:
        pcm_data = struct.pack("<h", 0) * 160  # 10ms of silence at 16kHz
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        sample_rate * 2,  # byte rate
        2,  # block align
        16,  # bits per sample
        b"data",
        data_size,
    )
    return header + pcm_data


class TestWavToPcm:
    def test_valid_wav_returns_pcm_and_sample_rate(self):
        pcm_data = struct.pack("<h", 42) * 10
        wav = _make_wav(16000, pcm_data)
        result, rate = wav_to_pcm(wav)
        assert rate == 16000
        assert result == pcm_data

    def test_wav_44100hz(self):
        pcm_data = struct.pack("<h", 1) * 10
        wav = _make_wav(44100, pcm_data)
        result, rate = wav_to_pcm(wav)
        assert rate == 44100
        assert result == pcm_data

    def test_wav_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            wav_to_pcm(b"\x00" * 10)

    def test_wav_empty_raises(self):
        with pytest.raises(ValueError, match="too short"):
            wav_to_pcm(b"")

    def test_wav_all_silence(self):
        pcm_data = b"\x00\x00" * 100
        wav = _make_wav(16000, pcm_data)
        result, rate = wav_to_pcm(wav)
        assert rate == 16000
        assert result == pcm_data
        assert all(b == 0 for b in result)


class TestTranscribeAudio:
    @pytest.fixture
    def mock_connection(self):
        reader = AsyncMock()
        writer = AsyncMock()
        # Simulate a transcript response
        msg_header = struct.pack("<I", len(b'{"type":"transcript","data":{"text":"hello world"}}'))
        msg_body = b'{"type":"transcript","data":{"text":"hello world"}}'
        reader.readexactly = AsyncMock(side_effect=[
            msg_header,
            msg_body,
        ])
        coro = AsyncMock(return_value=(reader, writer))
        return reader, writer, coro

    @pytest.mark.asyncio
    async def test_transcribe_success(self, mock_connection):
        reader, writer, coro = mock_connection
        with patch("app.whisper.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = (reader, writer)
            result = await transcribe_audio(b"\x00\x00" * 160, 16000)
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_transcribe_connection_timeout(self):
        with patch("app.whisper.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.side_effect = OSError("Connection refused")
            result = await transcribe_audio(b"\x00\x00" * 160, 16000)
            assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_empty_transcript(self, mock_connection):
        reader, writer, coro = mock_connection
        # Return transcript with empty text
        msg_header = struct.pack("<I", len(b'{"type":"transcript","data":{"text":""}}'))
        msg_body = b'{"type":"transcript","data":{"text":""}}'
        reader.readexactly = AsyncMock(side_effect=[msg_header, msg_body])
        with patch("app.whisper.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = (reader, writer)
            result = await transcribe_audio(b"\x00\x00" * 160, 16000)
            assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_no_transcript_events(self):
        reader = AsyncMock()
        writer = AsyncMock()
        # Simulate connection close (IncompleteReadError)
        reader.readexactly = AsyncMock(side_effect=OSError("Connection lost"))
        with patch("app.whisper.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.return_value = (reader, writer)
            result = await transcribe_audio(b"\x00\x00" * 160, 16000)
            assert result == ""
