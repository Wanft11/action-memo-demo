import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
