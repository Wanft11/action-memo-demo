import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings


class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch("app.services.personal_memory.DATA_DIR", root),
            patch("app.services.personal_memory.DATABASE_PATH", root / "test.db"),
            patch.object(settings, "openai_api_key", ""),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_independent_generation_states_survive_reopening(self):
        payload = {"current_user": "test-project", "transcript": "00:01 小万：今天提交报价单。",
                   "analysis": {"meeting_title": "报价项目", "tasks_generated": False, "all_tasks": []}}
        saved = self.client.post("/api/meetings/history", json=payload)
        self.assertEqual(saved.status_code, 200)
        record_id = saved.json()["id"]
        focus = {"title": "报价安排", "answer": "今天提交报价单", "sources": []}
        payload["analysis"]["focus_result"] = focus
        payload["analysis"]["focus_query"] = "需要做什么"
        self.assertEqual(self.client.put("/api/meetings/history/" + record_id, json=payload).status_code, 200)
        reopened = self.client.get("/api/meetings/history/" + record_id, params={"current_user": "test-project"}).json()
        self.assertFalse(reopened["analysis"]["tasks_generated"])
        self.assertEqual(reopened["analysis"]["focus_result"], focus)
        payload["analysis"]["tasks_generated"] = True
        self.client.put("/api/meetings/history/" + record_id, json=payload)
        reopened = self.client.get("/api/meetings/history/" + record_id, params={"current_user": "test-project"}).json()
        self.assertTrue(reopened["analysis"]["tasks_generated"])
        self.assertEqual(reopened["analysis"]["focus_result"], focus)

    def test_focus_includes_device_markers_without_task_generation(self):
        response = self.client.post("/api/meetings/focus", data={
            "current_user": "小万", "transcript": "00:01 小万：今天提交报价单。",
            "focus_query": "报价单", "markers": '[{"time":"00:01","label":"重点"}]',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["marker_insights"]), 1)
        self.assertEqual(response.json()["marker_insights"][0]["marker_time"], "00:01")

    def test_invalid_markers_return_validation_error(self):
        response = self.client.post("/api/meetings/focus", data={
            "transcript": "今天提交报价单", "focus_query": "报价", "markers": "invalid",
        })
        self.assertEqual(response.status_code, 422)
