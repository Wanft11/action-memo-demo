import re
import unittest
from pathlib import Path

from app.models.meeting import MeetingMarker
from app.services.meeting_analyzer import (
    build_local_focus_analysis,
    build_local_transcript_analysis,
    dedupe_tasks,
    extract_meeting_title,
    find_context_snippet,
    has_explicit_self_commitment,
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
    def test_recording_titles_support_non_meeting_scenarios(self):
        for label in ("主题", "录音主题", "对话主题", "会议主题"):
            with self.subTest(label=label):
                self.assertEqual(extract_meeting_title([f"{label}：周末出行安排"]), "周末出行安排")

    def test_self_commitment_requires_own_explicit_promise(self):
        self.assertTrue(has_explicit_self_commitment(
            "02:56 小万：好，我会把移动端审批的场景整理成两页说明。", "小万", "小万"
        ))
        self.assertFalse(has_explicit_self_commitment(
            "02:56 小万：我觉得这个场景值得讨论。", "小万", "小万"
        ))
        self.assertFalse(has_explicit_self_commitment(
            "02:56 说话人 1：我会把场景整理成两页说明。", "小万", "小万"
        ))
        self.assertFalse(has_explicit_self_commitment(
            "02:56 小万：我会把场景整理成两页说明。", "小万、说话人 1", "小万"
        ))

    def test_normalized_tasks_mark_only_own_explicit_commitment(self):
        analysis = normalize_llm_analysis({"all_tasks": [
            dict(task("画出产品流程", "小万", "小万：我这边把产品流程先画出来，再想一下 Demo 怎么呈现。"), confidence=0.9, status="已确认"),
            dict(task("填写报名表", "小万", "小万：我还没填，等会提醒我。"), confidence=0.9),
        ]}, TRANSCRIPT, "小万", None)

        self.assertTrue(analysis["all_tasks"][0]["self_committed"])
        self.assertEqual(analysis["all_tasks"][0]["status"], "待确认")
        self.assertFalse(analysis["all_tasks"][1]["self_committed"])

    def test_local_focus_returns_ranked_original_sources(self):
        result = build_local_focus_analysis(TRANSCRIPT, "小万", "技术流程什么时候完成")

        self.assertEqual(result.query, "技术流程什么时候完成")
        self.assertGreaterEqual(len(result.sources), 2)
        self.assertIn("技术流程", result.sources[0].evidence)
        self.assertEqual(result.sources[0].source, "06:03")
        self.assertTrue(all("技术流程" in source.evidence or "今晚" in source.evidence for source in result.sources))
        self.assertIn("本地检索到", result.answer)

    def test_focus_sources_are_not_limited_to_two(self):
        transcript = """10:00
小万：预算安排先控制在两万元以内。
小林：预算安排还要覆盖差旅费用。
阿哲：预算安排周五前发给团队确认。
小周：预算安排确定后我更新方案。"""
        result = build_local_focus_analysis(transcript, "小万", "预算安排")
        self.assertEqual(len(result.sources), 4)

        normalized = normalize_focus_analysis({
            "answer": "预算安排有四个相关信息点。",
            "sources": [{"evidence_ids": ["T001", "T002", "T003", "T004"]}],
        }, transcript, "预算安排")
        self.assertEqual(len(normalized.sources), 4)

    def test_local_focus_abstains_when_question_has_no_matching_evidence(self):
        result = build_local_focus_analysis(TRANSCRIPT, "小万", "餐厅地址在哪里")
        self.assertEqual(result.sources, [])
        self.assertIn("没有找到", result.answer)

        broad = build_local_focus_analysis(TRANSCRIPT, "小万", "我需要准备什么")
        self.assertEqual(broad.sources, [])
        next_steps = build_local_focus_analysis(TRANSCRIPT, "小万", "我接下来要准备什么？")
        self.assertEqual(next_steps.sources, [])

    def test_model_focus_rejects_unrelated_citations(self):
        result = normalize_focus_analysis({
            "title": "餐厅地址", "answer": "餐厅在一号楼", "sources": [{"evidence_ids": ["T001"]}],
        }, TRANSCRIPT, "餐厅地址在哪里")
        self.assertEqual(result.sources, [])
        self.assertNotIn("一号楼", result.answer)

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
        self.assertIn("说话人 2：可以，我今晚弄一下。", sample)
        self.assertIn("阿哲先画一个最简单的链路", sample)
        self.assertNotIn("网页按钮模拟重点标记", sample)

    def test_optional_demo_samples_are_parseable(self):
        sample_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        samples = {
            "client-follow-up-meeting.txt": "客户需求回访",
            "campus-event-planning.txt": "家庭周末出行安排",
        }

        for filename, title in samples.items():
            sample = (sample_dir / filename).read_text(encoding="utf-8")
            self.assertEqual(extract_meeting_title(split_transcript_lines(sample)), title)
            self.assertGreaterEqual(len(transcript_turns(split_transcript_lines(sample))), 10)

    def test_every_demo_speaker_turn_has_a_timestamp(self):
        sample_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        self.assertGreaterEqual(len(list(sample_dir.glob("*.txt"))), 11)
        for sample_path in sample_dir.glob("*.txt"):
            lines = sample_path.read_text(encoding="utf-8").splitlines()
            participant_line = next(line for line in lines if line.startswith("参会人："))
            self.assertRegex(participant_line, r"^参会人：小万(?:、说话人 \d+)+$")
            speaker_lines = [
                line for line in lines
                if re.match(r"^\d{2}:\d{2}\s+[^：]{1,12}：", line)
            ]
            self.assertTrue(speaker_lines, sample_path.name)
            self.assertGreaterEqual(len(speaker_lines), 55, sample_path.name)
            for line in speaker_lines:
                self.assertRegex(line, r"^\d{2}:\d{2}\s+(?:小万|说话人 \d+)：", line)
            self.assertTrue(any(" 小万：" in line for line in speaker_lines), sample_path.name)
            timed_lines = [line for line in lines if re.match(r"^\d{2}:\d{2}\s+", line)]
            seconds = [int(line[:2]) * 60 + int(line[3:5]) for line in timed_lines]
            self.assertEqual(seconds[0], 0, sample_path.name)
            self.assertGreaterEqual(seconds[-1], 600, sample_path.name)
            self.assertLessEqual(seconds[-1], 1200, sample_path.name)
            self.assertTrue(all(5 <= end - start <= 15 for start, end in zip(seconds, seconds[1:])), sample_path.name)
            duration_line = next(line for line in lines if line.startswith("会议时长："))
            stated_minutes = int(re.search(r"\d+", duration_line).group())
            self.assertLessEqual(abs(stated_minutes * 60 - seconds[-1]), 30, sample_path.name)

    def test_recording_bean_marker_is_preserved_with_the_transcript(self):
        marker = MeetingMarker(time="09:01", note="录音豆按压", source="recording_bean")
        result = build_local_transcript_analysis(TRANSCRIPT, "小万", [marker])

        self.assertEqual(result.marked_moments[0].time, "09:01")
        self.assertEqual(result.marked_moments[0].source, "recording_bean")

    def test_marker_insight_uses_a_bounded_context_window(self):
        transcript = """00:10 说话人 1：先聊一下无关背景。
00:55 说话人 1：小万，请在周五前整理演示脚本。
01:05 小万：好，我周五下午前发出来。
01:25 说话人 1：如果客户确认预算，我们再安排试用。
02:10 说话人 2：这里已经超出重点窗口。"""
        result = build_local_transcript_analysis(transcript, "小万", [MeetingMarker(time="01:05")])
        insight = result.marker_insights[0]
        self.assertEqual(insight.window_start, "00:20")
        self.assertEqual(insight.window_end, "01:50")
        self.assertEqual(insight.personal_action, "整理演示脚本")
        self.assertEqual(insight.deadline, "周五前")
        self.assertTrue(insight.conditions)
        self.assertNotIn("超出重点窗口", "\n".join(item.evidence for item in insight.evidence))

    def test_marker_prefers_the_users_nearest_unfinished_commitment(self):
        transcript = """11:22 说话人 1：报名表十二点半要交。
11:42 小万：我还没填，等会提醒我。
12:26 说话人 1：小万，请在明天下午前整理一页演示脚本。"""
        result = build_local_transcript_analysis(transcript, "小万", [MeetingMarker(time="11:42")])
        insight = result.marker_insights[0]
        self.assertEqual(insight.personal_action, "填写报名表")
        self.assertEqual(insight.deadline, "十二点半")
        self.assertIn("明确了你的行动：填写报名表", insight.summary)
        self.assertIn("我还没填", insight.evidence[0].evidence)

    def test_model_marker_insight_keeps_only_cited_source(self):
        data = {
            "all_tasks": [{"task": "填写报名表", "assignee": "小万", "deadline": "12:30", "evidence_ids": ["T003", "T004"]}],
            "marker_insights": [{
                "marker_time": "08:06", "summary": "报名表需要尽快填写。", "personal_action": "填写报名表",
                "deadline": "12:30", "conditions": [], "risks": ["临近截止"], "evidence_ids": ["T003", "T004"],
            }],
        }
        result = normalize_llm_analysis(data, TRANSCRIPT, "小万", [MeetingMarker(time="08:06")])
        insight = result["marker_insights"][0]
        self.assertEqual(insight["marker_time"], "08:06")
        self.assertEqual([item["source"] for item in insight["evidence"]], ["08:06", "08:06"])

    def test_demo_marker_times_still_point_to_the_intended_turns(self):
        markers = {
            "recording-bean-preliminary-meeting.txt": [("11:42", "我还没填"), ("13:25", "今晚给你们")],
            "client-follow-up-meeting.txt": [("05:29", "报价单我今天"), ("08:14", "我来发会议邀请")],
            "campus-event-planning.txt": [("05:22", "足球课请假"), ("08:14", "我总结一下")],
            "friends-gathering-plan.txt": [("05:43", "共享相册"), ("08:54", "总结一下")],
            "parent-school-chat.txt": [("02:52", "阅读记录我"), ("10:33", "我负责订正")],
            "career-mentor-chat.txt": [("02:54", "周五前发给我"), ("08:31", "周末前完成")],
            "study-group-plan.txt": [("02:55", "第一周先过"), ("10:48", "我维护表格")],
            "travel-plan.txt": [("02:53", "集合放地铁站"), ("08:08", "确认酒店")],
            "fitness-coaching.txt": [("02:51", "周三晚上七点"), ("08:00", "周六上午跑步")],
            "home-repair-chat.txt": [("02:52", "清出来"), ("07:59", "负责确认报价")],
            "elder-care-plan.txt": [("02:52", "周一请半天假"), ("10:36", "负责接送")],
        }
        sample_dir = Path(__file__).resolve().parents[1] / "static" / "samples"
        demo_page = (sample_dir.parent / "index.html").read_text(encoding="utf-8")
        for filename, expected in markers.items():
            sample = (sample_dir / filename).read_text(encoding="utf-8")
            for time, phrase in expected:
                self.assertRegex(sample, rf"(?m)^{time} (?:小万|说话人 \d+)：[^\n]*{phrase}")
            marker_config = re.search(rf'file: "{re.escape(filename)}".*?markers: \[(.*?)\]', demo_page, re.S)
            self.assertIsNotNone(marker_config, filename)
            self.assertEqual(re.findall(r'time: "([^"]+)"', marker_config.group(1)), [time for time, _ in expected])

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
