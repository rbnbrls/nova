import pytest
import struct
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app


def _make_wav(sample_rate: int = 16000, pcm_data: bytes | None = None) -> bytes:
    if pcm_data is None:
        pcm_data = struct.pack("<h", 0) * 160
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        data_size,
    )
    return header + pcm_data


@pytest.fixture
def client():
    return TestClient(app)


class TestDashboardTranscribe:
    def test_transcribe_valid_wav_returns_transcript(self, client):
        wav_data = _make_wav()
        with patch("app.main.whisper.wav_to_pcm") as mock_wav_to_pcm, \
             patch("app.main.whisper.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:
            mock_wav_to_pcm.return_value = (b"\x00\x00" * 160, 16000)
            mock_transcribe.return_value = "hello world"
            resp = client.post(
                "/dashboard/transcribe",
                files={"audio": ("test.wav", wav_data, "audio/wav")},
            )
            assert resp.status_code == 200
            assert resp.json()["transcript"] == "hello world"

    def test_transcribe_non_audio_content_type(self, client):
        resp = client.post(
            "/dashboard/transcribe",
            files={"audio": ("test.txt", b"not audio", "text/plain")},
        )
        assert resp.status_code == 400
        assert "audio" in resp.json()["detail"].lower()

    def test_transcribe_tiny_file(self, client):
        resp = client.post(
            "/dashboard/transcribe",
            files={"audio": ("tiny.wav", b"\x00\x00", "audio/wav")},
        )
        assert resp.status_code == 400
        assert "small" in resp.json()["detail"].lower()

    def test_transcribe_whisper_down(self, client):
        wav_data = _make_wav()
        with patch("app.main.whisper.wav_to_pcm") as mock_wav_to_pcm, \
             patch("app.main.whisper.transcribe_audio", new_callable=AsyncMock) as mock_transcribe:
            mock_wav_to_pcm.return_value = (b"\x00\x00" * 160, 16000)
            mock_transcribe.return_value = ""
            resp = client.post(
                "/dashboard/transcribe",
                files={"audio": ("test.wav", wav_data, "audio/wav")},
            )
            assert resp.status_code == 502
            assert "empty" in resp.json()["detail"].lower()

    def test_transcribe_wav_parsing_error(self, client):
        wav_data = _make_wav()
        with patch("app.main.whisper.wav_to_pcm") as mock_wav_to_pcm:
            mock_wav_to_pcm.side_effect = ValueError("Invalid WAV format")
            resp = client.post(
                "/dashboard/transcribe",
                files={"audio": ("test.wav", wav_data, "audio/wav")},
            )
            assert resp.status_code == 500

    def test_transcribe_missing_file(self, client):
        resp = client.post("/dashboard/transcribe")
        assert resp.status_code == 422
