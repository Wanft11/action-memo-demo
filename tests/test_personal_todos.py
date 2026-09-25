import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class PersonalTodoTests(unittest.TestCase):
    def test_existing_todo_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            data_dir.mkdir()
            database_path = data_dir / "action_memo.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute("""CREATE TABLE personal_todos (
                    id TEXT PRIMARY KEY, current_user TEXT, title TEXT, deadline TEXT,
                    completed INTEGER, created_at TEXT, updated_at TEXT
                )""")
                connection.execute("INSERT INTO personal_todos VALUES (?, ?, ?, ?, ?, ?, ?)",
                                   ("old-1", "小万", "旧待办", "周五", 0, "2026-09-01", "2026-09-01"))
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                response = TestClient(app).get("/api/meetings/todos", params={"current_user": "小万"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()[0]["due_at"], "")

    def test_manual_todo_crud_is_scoped_to_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            database_path = data_dir / "action_memo.db"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", database_path
            ):
                client = TestClient(app)
                payload = {"current_user": "小万", "title": "整理演示材料", "deadline": "2026-09-26 18:00", "due_at": "2026-09-26T18:00", "completed": False}
                created_response = client.post("/api/meetings/todos", json=payload)
                self.assertEqual(created_response.status_code, 200)
                created = created_response.json()
                self.assertFalse(created["completed"])
                self.assertEqual(created["due_at"], "2026-09-26T18:00")
                self.assertEqual(len(client.get("/api/meetings/todos", params={"current_user": "小万"}).json()), 1)
                self.assertEqual(client.get("/api/meetings/todos", params={"current_user": "别人"}).json(), [])

                url = f"/api/meetings/todos/{created['id']}"
                self.assertEqual(client.put(url, json={**payload, "current_user": "别人"}).status_code, 404)
                updated = client.put(url, json={**payload, "title": "整理最终演示材料", "completed": True}).json()
                self.assertEqual(updated["title"], "整理最终演示材料")
                self.assertTrue(updated["completed"])
                self.assertEqual(updated["due_at"], "2026-09-26T18:00")
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

    def test_invalid_due_at_is_rejected(self):
        response = TestClient(app).post("/api/meetings/todos", json={
            "current_user": "小万", "title": "检查材料", "due_at": "明天可能",
        })
        self.assertEqual(response.status_code, 422)
