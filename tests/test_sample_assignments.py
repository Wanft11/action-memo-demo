import re
import unittest
from pathlib import Path

from app.services.meeting_analyzer import build_local_transcript_analysis


SAMPLES = Path(__file__).resolve().parents[1] / "static" / "samples"


class SampleAssignmentTests(unittest.TestCase):
    def test_every_sample_has_a_task_assigned_by_someone_else(self):
        samples = sorted(SAMPLES.glob("*.txt"))
        self.assertGreaterEqual(len(samples), 10)

        for sample in samples:
            with self.subTest(sample=sample.name):
                analysis = build_local_transcript_analysis(sample.read_text(encoding="utf-8"), "小万")
                assignments = [
                    task for task in analysis.all_tasks
                    if task.assignee == "小万" and "小万，请" in task.evidence
                ]
                self.assertTrue(assignments)
                for task in assignments:
                    self.assertRegex(task.evidence, r"^\d{2}:\d{2} 说话人 [123]：")
                    self.assertEqual(task.source, re.match(r"^\d{2}:\d{2}", task.evidence).group())
                    self.assertGreaterEqual(task.confidence, 0.75)
                    self.assertFalse(task.self_committed)


if __name__ == "__main__":
    unittest.main()
