import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.personal_memory import (
    build_personal_profile,
    create_folder,
    get_folder,
    get_meeting,
    list_meetings,
    personal_context,
    personalization,
    relevant_feedback,
    save_meeting,
    suggest_folder,
    ensure_default_folder,
)


def payload(tasks):
    return {
        "current_user": "小万",
        "transcript": "小万：我来画产品流程。\n小林：我来整理访谈。",
        "audio_name": "demo.m4a",
        "analysis": {
            "meeting_title": "个人化测试会议",
            "all_tasks": tasks,
        },
    }


class PersonalMemoryTests(unittest.TestCase):
    def test_deleting_a_record_requires_its_owner_and_removes_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                saved = save_meeting(payload([
                    {"task": "画出产品流程", "assignee": "小万", "personal": True, "status": "已确认"},
                ]))
                client = TestClient(app)
                url = f"/api/meetings/history/{saved['id']}"
                self.assertEqual(client.delete(url, params={"current_user": "别人"}).status_code, 404)
                self.assertIsNotNone(get_meeting(saved["id"], "小万"))
                self.assertEqual(client.delete(url, params={"current_user": "小万"}).json(), {"deleted": True})
                self.assertIsNone(get_meeting(saved["id"], "小万"))
                self.assertEqual(build_personal_profile("小万")["confirmed_tasks"], [])

    def test_deleting_a_folder_moves_its_records_to_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                folder = create_folder({
                    "current_user": "小万", "name": "客户沟通", "keywords": ["客户"], "aliases": ["万哥"]
                })
                default_id = ensure_default_folder("小万")["id"]
                saved = save_meeting({**payload([]), "folder_id": folder["id"]})
                client = TestClient(app)
                url = f"/api/meetings/folders/{folder['id']}"
                self.assertEqual(client.delete(url, params={"current_user": "别人"}).status_code, 404)
                self.assertEqual(client.delete(f"/api/meetings/folders/{default_id}", params={"current_user": "小万"}).status_code, 400)
                self.assertEqual(client.delete(url, params={"current_user": "小万"}).json(), {"moved_count": 1})
                self.assertIsNone(get_folder(folder["id"], "小万"))
                self.assertEqual(get_meeting(saved["id"], "小万")["folder_id"], default_id)
                self.assertEqual(len(list_meetings("小万")), 1)

    def test_folder_suggestion_needs_two_keywords_and_a_clear_winner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                client_folder = create_folder({
                    "current_user": "小万", "name": "客户沟通", "keywords": ["客户", "报价", "续费"], "aliases": []
                })
                create_folder({
                    "current_user": "小万", "name": "工作沟通", "keywords": ["产品", "评审"], "aliases": []
                })
                create_folder({
                    "current_user": "别人", "name": "其他", "keywords": ["客户", "报价", "续费"], "aliases": []
                })

                suggestion = suggest_folder("小万", "请给客户更新报价，续费方案明天发送。", "客户回访")
                self.assertEqual(suggestion["folder_id"], client_folder["id"])
                self.assertEqual(suggestion["matched_keywords"], ["客户", "报价", "续费"])
                self.assertEqual(suggest_folder("小万", "客户报价需要更新。 ")["folder_id"], client_folder["id"])
                self.assertIsNone(suggest_folder("小万", "讨论客户需求。"))
                self.assertIsNone(suggest_folder("小万", "客户报价和产品评审都要讨论。"))
                self.assertIsNone(suggest_folder("陌生账号", "客户报价和续费都要讨论。"))

                response = TestClient(app).post("/api/meetings/folders/suggest", json={
                    "current_user": "小万", "transcript": "客户报价和续费都要讨论。"
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["suggestion"]["folder_id"], client_folder["id"])
                self.assertEqual(list_meetings("小万"), [])

    def test_folder_metadata_can_be_edited_without_moving_meetings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                folder = create_folder({
                    "current_user": "小万", "name": "工作沟通", "keywords": ["产品"], "aliases": ["万哥"]
                })
                saved = save_meeting({**payload([]), "folder_id": folder["id"]})
                client = TestClient(app)
                response = client.put(f"/api/meetings/folders/{folder['id']}", json={
                    "current_user": "小万", "keywords": ["客户", "客户", "报价"], "aliases": ["王老师"]
                })

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["keywords"], ["客户", "报价"])
                self.assertEqual(get_folder(folder["id"], "小万")["aliases"], ["王老师"])
                self.assertEqual(get_meeting(saved["id"], "小万")["folder_id"], folder["id"])
                self.assertEqual(client.put(f"/api/meetings/folders/{folder['id']}", json={
                    "current_user": "别人", "keywords": [], "aliases": []
                }).status_code, 404)

                default = ensure_default_folder("小万")
                self.assertEqual(client.put(f"/api/meetings/folders/{default['id']}", json={
                    "current_user": "小万", "keywords": ["临时"], "aliases": ["小万"]
                }).status_code, 200)

    def test_saved_feedback_builds_a_local_personal_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                saved = save_meeting(payload([
                    {"task": "画出产品流程", "assignee": "小万", "personal": True, "status": "待确认"},
                    {"task": "整理访谈证据", "assignee": "小林", "personal": False, "status": "待确认"},
                ]))

                history = list_meetings("小万")
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["task_count"], 2)
                self.assertEqual(history[0]["my_task_count"], 1)
                self.assertEqual(history[0]["confirmed_task_count"], 0)
                self.assertEqual(get_meeting(saved["id"], "小万")["audio_name"], "demo.m4a")

                profile = build_personal_profile("小万")
                self.assertEqual(profile["confirmed_tasks"], ["画出产品流程"])
                self.assertEqual(profile["excluded_tasks"], ["整理访谈证据"])
                self.assertIn("画出产品流程", personal_context("小万"))
                self.assertIn("整理访谈证据", personal_context("小万"))

                feedback = relevant_feedback("小万", "今天要讨论产品流程和 Demo")
                self.assertEqual(feedback[0]["task"], "画出产品流程")
                memory = personalization("小万", "今天要讨论产品流程和 Demo")
                self.assertIn("画出产品流程", memory["context"])
                self.assertIn("本次重点参考", memory["notes"][1])

    def test_updating_a_saved_meeting_replaces_its_feedback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                saved = save_meeting(payload([
                    {"task": "填写报名表", "assignee": "小万", "personal": True, "status": "待确认"},
                ]))
                updated = payload([
                    {"task": "填写报名表", "assignee": "小万", "personal": False, "status": "待确认"},
                ])
                save_meeting(updated, meeting_id=saved["id"])

                profile = build_personal_profile("小万")
                self.assertEqual(profile["confirmed_tasks"], [])
                self.assertEqual(profile["excluded_tasks"], ["填写报名表"])

    def test_vague_feedback_does_not_enter_the_personal_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                save_meeting(payload([
                    {"task": "整理", "assignee": "小万", "personal": True, "status": "已确认"},
                    {"task": "准备方案初稿", "assignee": "小万", "personal": True, "status": "已确认"},
                ]))

                profile = build_personal_profile("小万")
                self.assertEqual(profile["confirmed_tasks"], ["准备方案初稿"])

    def test_folder_keeps_context_and_defaults_unsorted_meetings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                work_folder = create_folder({
                    "current_user": "小万",
                    "name": "工作沟通",
                    "keywords": ["客户", "报价"],
                    "aliases": ["万哥", "王老师"],
                })
                saved = save_meeting({**payload([]), "folder_id": work_folder["id"]})
                default_record = save_meeting(payload([]))

                self.assertEqual(get_meeting(saved["id"], "小万")["folder_id"], work_folder["id"])
                self.assertNotEqual(get_meeting(default_record["id"], "小万")["folder_id"], work_folder["id"])
                self.assertEqual(get_folder(work_folder["id"], "小万")["aliases"], ["万哥", "王老师"])

    def test_folder_feedback_does_not_leak_between_scenarios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                work = create_folder({"current_user": "小万", "name": "工作", "keywords": [], "aliases": ["万哥"]})
                family = create_folder({"current_user": "小万", "name": "家庭", "keywords": [], "aliases": ["爸爸"]})
                save_meeting({**payload([{"task": "发送客户报价单", "assignee": "小万", "personal": True}]), "folder_id": work["id"]})
                save_meeting({**payload([{"task": "购买孩子雨衣", "assignee": "小万", "personal": True}]), "folder_id": family["id"]})

                self.assertEqual(build_personal_profile("小万", work["id"])["confirmed_tasks"], ["发送客户报价单"])
                self.assertEqual(build_personal_profile("小万", family["id"])["confirmed_tasks"], ["购买孩子雨衣"])


if __name__ == "__main__":
    unittest.main()
