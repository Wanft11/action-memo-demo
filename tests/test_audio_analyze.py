import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class AudioAnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def upload(self, content=b"not audio", filename="sample.mp3"):
        return self.client.post(
            "/api/meetings/analyze",
            data={"current_user": "小万"},
            files={"audio": (filename, content, "audio/mpeg")},
        )

    @patch("app.api.routes.has_openai_key", return_value=False)
    def test_no_key_never_returns_demo_transcript(self, _):
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn("API Key", response.json()["detail"])
        transcription = self.client.post(
            "/api/meetings/transcribe", files={"audio": ("sample.mp3", b"fake", "audio/mpeg")}
        )
        self.assertEqual(transcription.status_code, 503)

    @patch("app.api.routes.transcribe_audio_bytes", return_value="00:10 小万：我会整理脚本。")
    @patch("app.api.routes.has_openai_key", return_value=True)
    def test_transcription_has_its_own_stage(self, *_):
        response = self.client.post(
            "/api/meetings/transcribe", files={"audio": ("sample.mp3", b"fake", "audio/mpeg")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("整理脚本", response.json()["transcript"])

    @patch("app.api.routes.has_openai_key", return_value=True)
    def test_empty_audio_is_rejected(self, _):
        self.assertEqual(self.upload(b"").status_code, 422)

    @patch("app.api.routes.transcribe_audio_bytes", side_effect=ValueError("invalid audio"))
    @patch("app.api.routes.has_openai_key", return_value=True)
    def test_transcription_failure_is_not_replaced_with_demo(self, *_):
        response = self.upload()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("黑客松", str(response.json()))

    def test_missing_input_is_rejected(self):
        response = self.client.post("/api/meetings/analyze", data={"current_user": "小万"})
        self.assertEqual(response.status_code, 422)
