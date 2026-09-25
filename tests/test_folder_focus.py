import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.meeting import MeetingFocusAnalysis, MeetingFocusSource


class FolderFocusTests(unittest.TestCase):
    def test_folder_focus_combines_only_selected_folder_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ), patch.object(settings, "openai_api_key", ""), patch("app.api.routes.analyze_personal_focus") as analyze:
                analyze.return_value = MeetingFocusAnalysis(
                    query="客户上次最在意什么？",
                    title="客户关注点",
                    answer="客户最在意报价与交付时间。",
                    sources=[MeetingFocusSource(source="00:10", evidence="报价需要本周确认。", reason="直接说明需求")],
                    demo_mode=True,
                )
                client = TestClient(app)
                folder = client.post("/api/meetings/folders", json={
                    "current_user": "演示用户",
                    "name": "客户沟通",
                    "keywords": ["客户", "报价"],
                    "focus_modes": ["需求", "异议", "报价承诺", "下一步"],
                }).json()
                self.assertEqual(folder["focus_modes"], ["需求", "异议", "报价承诺", "下一步"])

                for title, transcript, folder_id in [
                    ("客户甲回访", "00:10 说话人 1：客户最在意报价和交付时间。", folder["id"]),
                    ("客户乙跟进", "01:05 说话人 2：下周前确认报价方案。", folder["id"]),
                    ("家庭安排", "00:20 说话人 1：周末带孩子去学校活动。", ""),
                ]:
                    response = client.post("/api/meetings/history", json={
                        "current_user": "演示用户",
                        "transcript": transcript,
                        "folder_id": folder_id,
                        "analysis": {"meeting_title": title, "all_tasks": []},
                    })
                    self.assertEqual(response.status_code, 200)

                response = client.post("/api/meetings/focus", data={
                    "current_user": "演示用户",
                    "folder_id": folder["id"],
                    "focus_query": "客户上次最在意什么？",
                })
                self.assertEqual(response.status_code, 200)
                combined = analyze.call_args.kwargs["transcript"]
                self.assertIn("【客户甲回访】", combined)
                self.assertIn("【客户乙跟进】", combined)
                self.assertNotIn("【家庭安排】", combined)


if __name__ == "__main__":
    unittest.main()
