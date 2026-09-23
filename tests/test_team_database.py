import sqlite3
import unittest
from pathlib import Path


class TeamDatabaseTests(unittest.TestCase):
    def test_team_snapshot_contains_only_expected_demo_record(self):
        database_path = Path(__file__).resolve().parents[1] / "static" / "samples" / "action_memo_team.db"
        with sqlite3.connect(database_path) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            meetings = connection.execute(
                "SELECT current_user, meeting_title, audio_name FROM saved_meetings"
            ).fetchall()
            folders = connection.execute(
                "SELECT current_user, name FROM recording_folders"
            ).fetchall()

        self.assertEqual(tables, {"saved_meetings", "recording_folders"})
        self.assertEqual(meetings, [("小万", "录音豆预赛方案讨论", "")])
        self.assertEqual(len(folders), 6)
        self.assertTrue(all(user == "小万" for user, _ in folders))


if __name__ == "__main__":
    unittest.main()
