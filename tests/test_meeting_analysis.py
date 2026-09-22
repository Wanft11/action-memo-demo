import re
import unittest
from pathlib import Path

from app.services.meeting_analyzer import (
    build_local_focus_analysis,
    build_local_transcript_analysis,
    dedupe_tasks,
    extract_meeting_title,
    find_context_snippet,
    normalize_llm_analysis,
    normalize_focus_analysis,
    split_transcript_lines,
    transcript_turns,
)


TRANSCRIPT = """参会人：小万、小林、小周、阿哲
06:03
小周：这个你之后能不能画一个很简单的技术流程？
阿哲：可以，我今晚弄一下。
08:06
小周：报名表十二点半要交。
小万：我还没填，等会提醒我。
09:01
小万：然后小林和小周可以把访谈或者问卷再看一下，找证据支持需求。
小林：可以，我今晚整理。
小周：我也一起。
小万：我这边把产品流程先画出来，再想一下 Demo 怎么呈现。我们明天再对一版。
"""


def task(title, assignee, evidence, deadline="待确认"):
    return dict(task=title, assignee=assignee, evidence=evidence, deadline=deadline)


class MeetingAnalysisTests(unittest.TestCase):
    def test_local_focus_returns_ranked_original_sources(self):
        result = build_local_focus_analysis(TRANSCRIPT, "小万", "技术流程什么时候完成")

        self.assertEqual(result.query, "技术流程什么时候完成")
        self.assertGreaterEqual(len(result.sources), 2)
        self.assertIn("技术流程", result.sources[0].evidence)
        self.assertEqual(result.sources[0].source, "06:03")
        self.assertIn("今晚", result.sources[1].evidence)
        self.assertIn("阿哲表示", result.answer)
        self.assertIn("今晚", result.answer)
        self.assertNotIn("这个你之后", result.answer)

    def test_focus_citations_reconstruct_original_turns(self):
        result = normalize_focus_analysis(
            {
                "title": "技术流程安排",
                "answer": "阿哲会在今晚给出技术流程版本。",
                "sources": [{"evidence_ids": ["T001", "T002", "T999"], "reason": "说明任务与期限"}],
            },
            TRANSCRIPT,
            "技术流程",
        )

        self.assertFalse(result.demo_mode)
        self.assertEqual([source.source for source in result.sources], ["06:03", "06:03"])
        self.assertIn("小周：这个你之后能不能画一个很简单的技术流程？", result.sources[0].evidence)
        self.assertIn("阿哲：可以，我今晚弄一下。", result.sources[1].evidence)

    def test_full_demo_sample_is_available_and_parseable(self):
        sample_path = Path(__file__).resolve().parents[1] / "static" / "samples" / "recording-bean-preliminary-meeting.txt"
        sample = sample_path.read_text(encoding="utf-8")
        turns = transcript_turns(split_transcript_lines(sample))

        self.assertEqual(extract_meeting_title(split_transcript_lines(sample)), "录音豆预赛方案讨论")
        self.assertGreaterEqual(len(turns), 50)
        self.assertIn("小万：我还没填，等会提醒我。", sample)
        self.assertIn("阿哲：可以，我今晚弄一下。", sample)

    def test_optional_demo_samples_are_parseable(self):
        sample_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        samples = {
            "client-follow-up-meeting.txt": "客户需求回访",
            "campus-event-planning.txt": "校园创意市集筹备沟通",
        }

        for filename, title in samples.items():
            sample = (sample_dir / filename).read_text(encoding="utf-8")
            self.assertEqual(extract_meeting_title(split_transcript_lines(sample)), title)
            self.assertGreaterEqual(len(transcript_turns(split_transcript_lines(sample))), 10)

    def test_every_demo_speaker_turn_has_a_timestamp(self):
        sample_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        for sample_path in sample_dir.glob("*.txt"):
            lines = sample_path.read_text(encoding="utf-8").splitlines()
            speaker_lines = [
                line for line in lines
                if "：" in line and not line.startswith(("会议主题：", "参会人：", "会议时长："))
            ]
            self.assertTrue(speaker_lines, sample_path.name)
            for line in speaker_lines:
                self.assertRegex(line, r"^\d{2}:\d{2}\s+[^：]+：", line)

    def test_explicit_meeting_subject_replaces_model_title(self):
        transcript = "会议主题：录音豆预赛方案讨论\n小万：今天确定分工。"
        result = normalize_llm_analysis({"meeting_title": "录音豆项目会议"}, transcript, "小万", None)
        self.assertEqual(result["meeting_title"], "录音豆预赛方案讨论")
        self.assertEqual(build_local_transcript_analysis(transcript, "小万").meeting_title, "录音豆预赛方案讨论")

    def test_personal_tasks_come_from_team_tasks_and_self_means_speaker(self):
        data = {"all_tasks": [
            task("画出产品流程", "我这边把产品流程先画出", "我这边把产品流程先画出来，再想一下 Demo 怎么呈现。我们明天再对一版。", "明天"),
            task("填写报名表", "小万", "小周：报名表十二点半要交。\n小万：我还没填，等会提醒我。", "12:30"),
            task("整理访谈证据", "小万", "小万：然后小林和小周可以把访谈或者问卷再看一下，找证据支持需求。"),
        ], "my_tasks": []}
        result = normalize_llm_analysis(data, TRANSCRIPT, "小万", None)
        self.assertEqual([t["task"] for t in result["my_tasks"]], ["画出产品流程", "填写报名表"])
        self.assertEqual(result["all_tasks"][2]["assignee"], "小林、小周")
        self.assertEqual(result["my_tasks"][0]["source"], "09:01")
        self.assertEqual(result["my_tasks"][1]["source"], "08:06")

    def test_task_titles_are_short_actions_not_transcript_sentences(self):
        data = {"all_tasks": [task(
            "小万：我这边把产品流程先画出来，再想一下 Demo 怎么呈现。",
            "小万",
            "小万：我这边把产品流程先画出来，再想一下 Demo 怎么呈现。我们明天再对一版。",
            "明天",
        )]}
        result = normalize_llm_analysis(data, TRANSCRIPT, "小万", None)
        self.assertEqual(result["all_tasks"][0]["task"], "画出产品流程")
        self.assertLessEqual(len(result["all_tasks"][0]["task"]), 14)

    def test_vague_task_titles_are_rejected_even_when_model_returns_them(self):
        transcript = "小万：我会跟进一下。"
        result = normalize_llm_analysis(
            {"all_tasks": [task("跟进一下", "小万", transcript)]},
            transcript,
            "小万",
            None,
        )
        self.assertEqual(result["all_tasks"], [])

    def test_joint_task_is_visible_for_each_owner_only(self):
        data = {"all_tasks": [task("整理访谈证据", "小林、小周", "小万：然后小林和小周可以把访谈或者问卷再看一下，找证据支持需求。") ]}
        for user, count in [("小万", 0), ("小林", 1), ("小周", 1), ("阿哲", 0)]:
            self.assertEqual(len(normalize_llm_analysis(data, TRANSCRIPT, user, None)["my_tasks"]), count)

    def test_one_joint_owner_accepting_does_not_remove_the_other(self):
        data = {"all_tasks": [task("整理访谈证据", "小林、小周", "小林：可以，我今晚整理。", "今晚")]}
        result = normalize_llm_analysis(data, TRANSCRIPT, "小周", None)
        self.assertEqual(result["all_tasks"][0]["assignee"], "小林、小周")
        self.assertEqual(len(result["my_tasks"]), 1)

    def test_evidence_cannot_be_replaced_with_unrelated_speech_by_same_person(self):
        lines = ["阿哲：我们可以做声纹。", "小周：请画出技术流程。"]
        self.assertEqual(find_context_snippet("设计接口", "阿哲", "不存在的证据句子。", lines), "")
        self.assertEqual(find_context_snippet("画出技术流程", "阿哲", "请画出技术流程。", lines), lines[1])

    def test_source_uses_actual_transcript_timestamp(self):
        data = {"all_tasks": [dict(task("画出技术流程", "阿哲", "小周：这个你之后能不能画一个很简单的技术流程？\n阿哲：可以，我今晚弄一下。", "今晚"), source="07:05")]}
        result = normalize_llm_analysis(data, TRANSCRIPT, "小万", None)
        self.assertEqual(result["all_tasks"][0]["source"], "06:03")
        self.assertEqual(result["all_tasks"][0]["assignee"], "阿哲")
        self.assertEqual(result["my_tasks"], [])

    def test_deduplicate_same_action_but_keep_separate_actions_and_owners(self):
        evidence = "小万：小林和小周可以整理访谈证据。"
        tasks = [
            task("整理访谈证据", "小林、小周", evidence),
            task("整理访谈或问卷证据", "小周、小林", evidence, "今晚"),
            task("设计登录页面", "小万", "小万：我负责设计登录页面并测试登录页面。"),
            task("测试登录页面", "小万", "小万：我负责设计登录页面并测试登录页面。"),
            task("测试登录页面", "阿哲", "阿哲：我也测试登录页面。"),
        ]
        result = dedupe_tasks(tasks)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["deadline"], "今晚")

    def test_valid_tasks_not_filtered_by_background_words_or_five_item_cap(self):
        tasks = [task(f"填写报名表{i}", "小万", f"因为容易忘掉信息，我要填写报名表{i}。") for i in range(7)]
        self.assertEqual(len(dedupe_tasks(tasks)), 7)

    def test_unverified_evidence_does_not_create_a_task(self):
        result = normalize_llm_analysis({"all_tasks": [task("购买服务器", "小万", "小万：明天买十台服务器。") ]}, TRANSCRIPT, "小万", None)
        self.assertEqual(result["all_tasks"], [])

    def test_local_fallback_never_maps_other_speakers_me_to_current_user(self):
        result = build_local_transcript_analysis("09:01 小林：我今晚整理访谈证据。", "小万")
        self.assertEqual(result.my_tasks, [])
        self.assertEqual(result.all_tasks[0].assignee, "小林")
        self.assertEqual(result.all_tasks[0].task, "整理访谈证据")

    def test_identical_quotes_keep_the_named_speaker(self):
        lines = ["小林：我今晚整理访谈证据。", "小万：我今晚整理访谈证据。"]
        self.assertEqual(find_context_snippet("整理访谈证据", "小万", lines[1], lines), lines[1])

    def test_citation_ids_reconstruct_exact_context_and_deadline(self):
        data = {"all_tasks": [{"task": "画出技术流程", "assignee": "阿哲", "evidence_ids": ["T001", "T002", "T999"], "deadline": "待确认"}]}
        result = normalize_llm_analysis(data, TRANSCRIPT, "阿哲", None)
        action = result["my_tasks"][0]
        self.assertEqual(action["source"], "06:03")
        self.assertEqual(action["deadline"], "今晚")
        self.assertEqual(action["evidence"], "小周：这个你之后能不能画一个很简单的技术流程？\n阿哲：可以，我今晚弄一下。")


if __name__ == "__main__":
    unittest.main()
