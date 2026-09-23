import json
import sqlite3
import unittest
from pathlib import Path


class DemoDatabaseTests(unittest.TestCase):
    def test_shared_database_contains_only_deidentified_demo_records(self):
        database_path = Path(__file__).resolve().parents[1] / "static" / "samples" / "action_memo_demo.db"
        with sqlite3.connect(database_path) as connection:
            rows = connection.execute(
                "SELECT current_user, meeting_title, transcript, analysis_json, folder_id FROM saved_meetings"
            ).fetchall()
            folders = connection.execute(
                "SELECT id, current_user, name, keywords_json, aliases_json, is_default FROM recording_folders"
            ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row[0] == "演示用户" for row in rows))
        sample_text = "\n".join("\n".join(str(value) for value in row) for row in rows)
        self.assertNotIn("小万", sample_text)
        self.assertNotIn("小林", sample_text)
        self.assertNotIn("小周", sample_text)
        self.assertNotIn("阿哲", sample_text)
        self.assertTrue(all(json.loads(row[3])["all_tasks"] for row in rows))
        self.assertEqual(len(folders), 3)
        self.assertEqual(sum(folder[5] for folder in folders), 1)
        self.assertTrue(all(folder[1] == "演示用户" for folder in folders))
        self.assertTrue(all(row[4] in {folder[0] for folder in folders} for row in rows))
        self.assertTrue(any(json.loads(folder[3]) for folder in folders))
        folder_text = "\n".join("\n".join(str(value) for value in folder) for folder in folders)
        for private_name in ("小万", "小林", "小周", "阿哲"):
            self.assertNotIn(private_name, folder_text)


if __name__ == "__main__":
    unittest.main()
