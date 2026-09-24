import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBP"


class FolderImageTests(unittest.TestCase):
    def test_create_generates_image_and_owner_can_read_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            response = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(WEBP_BYTES).decode())])
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", data_dir / "action_memo.db"
            ), patch.object(settings, "openai_api_key", "test-key"), patch(
                "app.services.folder_images.OpenAI"
            ) as openai_client:
                openai_client.return_value.images.generate.return_value = response
                client = TestClient(app)
                created = client.post("/api/meetings/folders", json={
                    "current_user": "小万", "name": "办公", "keywords": ["项目"], "aliases": [],
                    "image_keywords": ["笔记本电脑", "咖啡杯"],
                })
                self.assertEqual(created.status_code, 200)
                folder_id = created.json()["id"]
                folders = client.get("/api/meetings/folders", params={"current_user": "小万"}).json()
                folder = next(item for item in folders if item["id"] == folder_id)
                self.assertEqual(folder["image_status"], "ready")
                self.assertEqual(folder["keywords"], ["项目"])
                self.assertEqual(folder["image_keywords"], ["笔记本电脑", "咖啡杯"])
                prompt = openai_client.return_value.images.generate.call_args.kwargs["prompt"]
                self.assertIn("笔记本电脑", prompt)
                self.assertIn("咖啡杯", prompt)
                image_url = f"/api/meetings/folders/{folder_id}/image"
                self.assertEqual(client.get(image_url, params={"current_user": "小万"}).content, WEBP_BYTES)
                self.assertEqual(client.get(image_url, params={"current_user": "别人"}).status_code, 404)
                self.assertEqual(client.post(image_url, json={"current_user": "小万", "image_keywords": ["台灯"]}).status_code, 200)
                self.assertIn("台灯", openai_client.return_value.images.generate.call_args.kwargs["prompt"])
                self.assertEqual(client.delete(f"/api/meetings/folders/{folder_id}", params={"current_user": "小万"}).status_code, 200)
                self.assertFalse((data_dir / "folder-images" / f"{folder_id}.webp").exists())

    def test_failed_generation_can_retry_without_recreating_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            response = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(WEBP_BYTES).decode())])
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", data_dir / "action_memo.db"
            ), patch.object(settings, "openai_api_key", "test-key"), patch(
                "app.services.folder_images.OpenAI"
            ) as openai_client, patch("app.services.folder_images.logger"):
                openai_client.return_value.images.generate.side_effect = RuntimeError("offline")
                client = TestClient(app)
                created = client.post("/api/meetings/folders", json={
                    "current_user": "小万", "name": "家庭", "keywords": [], "aliases": [],
                }).json()
                folder_id = created["id"]
                folders = client.get("/api/meetings/folders", params={"current_user": "小万"}).json()
                self.assertEqual(next(item for item in folders if item["id"] == folder_id)["image_status"], "failed")
                self.assertEqual(client.post(f"/api/meetings/folders/{folder_id}/image", json={"current_user": "别人", "image_keywords": ["相框"]}).status_code, 404)
                openai_client.return_value.images.generate.side_effect = None
                openai_client.return_value.images.generate.return_value = response
                self.assertEqual(client.post(f"/api/meetings/folders/{folder_id}/image", json={"current_user": "小万", "image_keywords": ["相框", "绿植"]}).status_code, 200)
                self.assertIn("相框", openai_client.return_value.images.generate.call_args.kwargs["prompt"])
                folders = client.get("/api/meetings/folders", params={"current_user": "小万"}).json()
                self.assertEqual(next(item for item in folders if item["id"] == folder_id)["image_keywords"], ["相框", "绿植"])
                self.assertEqual(client.get(f"/api/meetings/folders/{folder_id}/image", params={"current_user": "小万"}).status_code, 200)
                openai_client.return_value.images.generate.side_effect = RuntimeError("offline again")
                self.assertEqual(client.post(f"/api/meetings/folders/{folder_id}/image", json={"current_user": "小万", "image_keywords": ["新相框"]}).status_code, 200)
                folder = next(item for item in client.get("/api/meetings/folders", params={"current_user": "小万"}).json() if item["id"] == folder_id)
                self.assertEqual(folder["image_status"], "failed")
                self.assertTrue(folder["image_available"])
                self.assertEqual(client.get(f"/api/meetings/folders/{folder_id}/image", params={"current_user": "小万"}).status_code, 200)

    def test_missing_key_keeps_folder_with_fallback_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / ".action-memo"
            with patch("app.services.personal_memory.DATA_DIR", data_dir), patch(
                "app.services.personal_memory.DATABASE_PATH", data_dir / "action_memo.db"
            ), patch.object(settings, "openai_api_key", ""):
                client = TestClient(app)
                created = client.post("/api/meetings/folders", json={
                    "current_user": "小万", "name": "学习", "keywords": [], "aliases": [],
                })
                self.assertEqual(created.json()["image_status"], "unavailable")
                self.assertEqual(client.post(
                    f"/api/meetings/folders/{created.json()['id']}/image", json={"current_user": "小万", "image_keywords": []}
                ).status_code, 503)
