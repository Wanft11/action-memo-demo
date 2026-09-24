import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class PersonalTodoTests(unittest.TestCase):
    def test_manual_todo_crud_is_scoped_to_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                client = TestClient(app)
                payload = {"current_user": "小万", "title": "整理演示材料", "deadline": "周五", "completed": False}
                created_response = client.post("/api/meetings/todos", json=payload)
                self.assertEqual(created_response.status_code, 200)
                created = created_response.json()
                self.assertFalse(created["completed"])
                self.assertEqual(len(client.get("/api/meetings/todos", params={"current_user": "小万"}).json()), 1)
                self.assertEqual(client.get("/api/meetings/todos", params={"current_user": "别人"}).json(), [])

                url = f"/api/meetings/todos/{created['id']}"
                self.assertEqual(client.put(url, json={**payload, "current_user": "别人"}).status_code, 404)
                updated = client.put(url, json={**payload, "title": "整理最终演示材料", "completed": True}).json()
                self.assertEqual(updated["title"], "整理最终演示材料")
                self.assertTrue(updated["completed"])
                self.assertEqual(client.delete(url, params={"current_user": "别人"}).status_code, 404)
                self.assertEqual(client.delete(url, params={"current_user": "小万"}).json(), {"deleted": True})
                self.assertEqual(client.get("/api/meetings/todos", params={"current_user": "小万"}).json(), [])

    def test_blank_todo_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                response = TestClient(app).post(
                    "/api/meetings/todos", json={"current_user": "小万", "title": "   "}
                )
                self.assertEqual(response.status_code, 422)
