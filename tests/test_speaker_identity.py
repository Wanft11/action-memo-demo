import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.meeting_analyzer import build_local_transcript_analysis


TRANSCRIPT = "00:10 说话人 1：我负责整理访谈记录。\n00:20 说话人 2：我负责准备演示稿。"


class SpeakerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def analyze(self, data, files=None):
        with patch("app.api.routes.analyze_transcript_with_llm", side_effect=lambda **kwargs: build_local_transcript_analysis(
            kwargs["transcript"], kwargs["current_user"], kwargs["markers"]
        )), patch("app.api.routes.personalization", return_value={"context": "", "notes": []}):
            return self.client.post("/api/meetings/analyze", data=data, files=files)

    def test_unconfirmed_speaker_cannot_auto_populate_my_tasks(self):
        response = self.analyze({"transcript": TRANSCRIPT, "current_user": "小万"})

        self.assertEqual(response.status_code, 200)
        analysis = response.json()
        self.assertFalse(analysis["identity_confirmed"])
        self.assertEqual(analysis["my_tasks"], [])
        self.assertGreaterEqual(len(analysis["all_tasks"]), 1)

    def test_timestamp_is_not_accepted_as_a_speaker(self):
        transcript = "09:05 第二，MVP 输出两类：行动和信息。\n10:02 会议结束"
        response = self.analyze({"transcript": transcript, "current_user": "小万", "confirmed_speaker": "09"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["identity_confirmed"])

    def test_confirmed_generic_speaker_becomes_current_user(self):
        response = self.analyze({
            "transcript": TRANSCRIPT,
            "current_user": "小万",
            "confirmed_speaker": "说话人 1",
        })

        self.assertEqual(response.status_code, 200)
        analysis = response.json()
        self.assertTrue(analysis["identity_confirmed"])
        self.assertIn("00:10 小万：", analysis["transcript"][0])
        self.assertIn("00:20 说话人 2：", analysis["transcript"][1])
        self.assertTrue(analysis["my_tasks"])
        self.assertTrue(all(task["assignee"] == "小万" for task in analysis["my_tasks"]))

    def test_confirmed_named_self_keeps_other_speakers_anonymous(self):
        response = self.analyze({
            "transcript": "00:10 小万：我负责整理访谈记录。\n00:20 说话人 1：我负责准备演示稿。",
            "current_user": "小万",
            "confirmed_speaker": "小万",
        })

        self.assertEqual(response.status_code, 200)
        analysis = response.json()
        self.assertTrue(analysis["identity_confirmed"])
        self.assertEqual(len(analysis["my_tasks"]), 1)
        self.assertEqual(analysis["my_tasks"][0]["assignee"], "小万")
        self.assertIn("说话人 1：", analysis["transcript"][1])

    def test_audio_without_speaker_labels_stays_unconfirmed(self):
        with patch("app.api.routes.has_openai_key", return_value=True), patch(
            "app.api.routes.transcribe_audio_bytes", return_value="我负责整理访谈记录。"
        ):
            response = self.analyze(
                {"current_user": "小万"},
                files={"audio": ("meeting.wav", b"fake audio", "audio/wav")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["identity_confirmed"])
        self.assertEqual(response.json()["my_tasks"], [])

    def test_demo_without_audio_or_transcript_does_not_claim_identity(self):
        response = self.client.post("/api/meetings/analyze", data={"current_user": "小万"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["identity_confirmed"])
        self.assertEqual(response.json()["my_tasks"], [])
        self.assertTrue(all(task["assignee"] != "我" for task in response.json()["all_tasks"]))


if __name__ == "__main__":
    unittest.main()
