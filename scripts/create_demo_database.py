"""Create a shareable, de-identified Action Memo demo database."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parents[1] / "static" / "samples" / "action_memo_demo.db"
DEMO_USER = "演示用户"
FOLDERS = [
    {"id": "demo-default", "name": "默认文件夹", "keywords": [], "aliases": [DEMO_USER], "is_default": 1},
    {"id": "demo-project", "name": "项目协作", "keywords": ["产品", "原型", "评审"], "aliases": ["负责人"], "is_default": 0},
    {"id": "demo-client", "name": "客户沟通", "keywords": ["客户", "需求", "方案"], "aliases": ["项目经理"], "is_default": 0},
]


def analysis(title: str, tasks: list[dict]) -> dict:
    return {
        "meeting_title": title,
        "summary": "这是用于团队测试的脱敏会议样本。",
        "decisions": ["优先展示与当前用户有关的行动项。"],
        "all_tasks": tasks,
        "my_tasks": [task for task in tasks if task.get("personal") is True],
        "risks": [],
        "questions": [],
        "evidence_notes": [],
        "marked_moments": [],
        "transcript": [],
        "demo_mode": True,
    }


def task(title: str, assignee: str, deadline: str, evidence: str, personal: bool) -> dict:
    return {
        "task": title,
        "assignee": assignee,
        "deadline": deadline,
        "source": "演示片段",
        "evidence": evidence,
        "status": "已确认" if personal else "待确认",
        "confidence": 0.9,
        "personal": personal,
    }


RECORDS = [
    {
        "id": "demo-product-planning-001",
        "folder_id": "demo-project",
        "title": "产品方案分工讨论",
        "transcript": "成员甲：请演示用户在明天前画出产品流程。\n演示用户：我来处理。\n成员乙：我会整理访谈证据。",
        "analysis": analysis(
            "产品方案分工讨论",
            [
                task("画出产品流程", DEMO_USER, "明天", "演示用户确认负责产品流程。", True),
                task("整理访谈证据", "成员乙", "今晚", "成员乙确认整理访谈证据。", False),
                task("填写报名表", DEMO_USER, "12:30", "演示用户需要填写报名表。", True),
            ],
        ),
    },
    {
        "id": "demo-client-followup-002",
        "folder_id": "demo-client",
        "title": "客户需求沟通",
        "transcript": "成员甲：客户希望明天看到初稿。\n演示用户：我先准备方案初稿。\n成员丙：我负责汇总客户反馈。",
        "analysis": analysis(
            "客户需求沟通",
            [
                task("准备方案初稿", DEMO_USER, "明天", "演示用户承诺准备方案初稿。", True),
                task("汇总客户反馈", "成员丙", "本周五", "成员丙负责汇总客户反馈。", False),
            ],
        ),
    },
]


def main() -> None:
    DATABASE_PATH.unlink(missing_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE saved_meetings (
                id TEXT PRIMARY KEY,
                current_user TEXT NOT NULL,
                meeting_title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                audio_name TEXT NOT NULL DEFAULT '',
                folder_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE recording_folders (
                id TEXT PRIMARY KEY,
                current_user TEXT NOT NULL,
                name TEXT NOT NULL,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                aliases_json TEXT NOT NULL DEFAULT '[]',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        for folder in FOLDERS:
            connection.execute(
                """INSERT INTO recording_folders
                (id, current_user, name, keywords_json, aliases_json, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    folder["id"], DEMO_USER, folder["name"],
                    json.dumps(folder["keywords"], ensure_ascii=False),
                    json.dumps(folder["aliases"], ensure_ascii=False),
                    folder["is_default"], now,
                ),
            )
        for record in RECORDS:
            connection.execute(
                """
                INSERT INTO saved_meetings (
                    id, current_user, meeting_title, transcript, analysis_json,
                    audio_name, folder_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    DEMO_USER,
                    record["title"],
                    record["transcript"],
                    json.dumps(record["analysis"], ensure_ascii=False),
                    "",
                    record["folder_id"],
                    now,
                    now,
                ),
            )
    print(f"Created {DATABASE_PATH}")


if __name__ == "__main__":
    main()
