import sqlite3
import unittest
from pathlib import Path


class TeamDatabaseTests(unittest.TestCase):
    def test_team_snapshot_contains_only_expected_demo_records(self):
        samples_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        database_path = samples_dir / "action_memo_team.db"
        with sqlite3.connect(database_path) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            meetings = connection.execute(
                "SELECT current_user, meeting_title, audio_name, transcript FROM saved_meetings"
            ).fetchall()
            folders = connection.execute(
                "SELECT current_user, name FROM recording_folders"
            ).fetchall()

        self.assertEqual(tables, {"saved_meetings", "recording_folders"})
        self.assertEqual({row[1] for row in meetings}, {
            "录音豆预赛方案讨论", "周末短途旅行规划", "求职导师交流", "考试复习小组安排"
        })
        self.assertTrue(all(user == "小万" and not audio_name for user, _, audio_name, _ in meetings))
        for title, sample_file in {
            "周末短途旅行规划": "travel-plan.txt",
            "求职导师交流": "career-mentor-chat.txt",
            "考试复习小组安排": "study-group-plan.txt",
        }.items():
            transcript = next(row[3] for row in meetings if row[1] == title)
            self.assertEqual(transcript.strip(), (samples_dir / sample_file).read_text(encoding="utf-8").strip())
        self.assertEqual(len(folders), 7)
        self.assertTrue(all(user == "小万" for user, _ in folders))


if __name__ == "__main__":
    unittest.main()
