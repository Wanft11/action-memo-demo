import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / ".action-memo"
DATABASE_PATH = DATA_DIR / "action_memo.db"
VAGUE_PROFILE_TASKS = {"跟进", "整理", "处理", "准备", "确认", "推进", "复盘", "相关内容", "后续事项"}


def _connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_meetings (
            id TEXT PRIMARY KEY,
            current_user TEXT NOT NULL,
            meeting_title TEXT NOT NULL,
            transcript TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            audio_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _record_from_row(row: sqlite3.Row, include_content: bool = False) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "current_user": row["current_user"],
        "meeting_title": row["meeting_title"],
        "audio_name": row["audio_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    analysis = json.loads(row["analysis_json"])
    tasks = analysis.get("all_tasks", [])
    record["task_count"] = len(tasks)
    record["my_task_count"] = sum(
        task.get("personal") is True
        or (
            task.get("personal") is not False
            and row["current_user"] in str(task.get("assignee") or "").split("、")
        )
        for task in tasks
    )
    record["confirmed_task_count"] = sum(
        str(task.get("status") or "") == "已确认" for task in tasks
    )
    if include_content:
        record["transcript"] = row["transcript"]
        record["analysis"] = analysis
    return record


def save_meeting(payload: dict[str, Any], meeting_id: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    analysis = payload["analysis"]
    record_id = meeting_id or str(uuid.uuid4())
    title = str(analysis.get("meeting_title") or "未命名会议")
    values = (
        record_id,
        payload["current_user"].strip(),
        title,
        payload["transcript"],
        json.dumps(analysis, ensure_ascii=False),
        payload.get("audio_name", ""),
        now,
        now,
    )
    with _connection() as connection:
        if meeting_id:
            connection.execute(
                """
                UPDATE saved_meetings
                SET current_user = ?, meeting_title = ?, transcript = ?, analysis_json = ?,
                    audio_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (values[1], values[2], values[3], values[4], values[5], now, record_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO saved_meetings (
                    id, current_user, meeting_title, transcript, analysis_json,
                    audio_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        row = connection.execute("SELECT * FROM saved_meetings WHERE id = ?", (record_id,)).fetchone()
    return _record_from_row(row, include_content=True)


def list_meetings(current_user: str) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM saved_meetings WHERE current_user = ? ORDER BY updated_at DESC",
            (current_user.strip(),),
        ).fetchall()
    return [_record_from_row(row) for row in rows]


def get_meeting(meeting_id: str, current_user: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM saved_meetings WHERE id = ? AND current_user = ?",
            (meeting_id, current_user.strip()),
        ).fetchone()
    return _record_from_row(row, include_content=True) if row else None


def build_personal_profile(current_user: str) -> dict[str, Any]:
    meetings = [get_meeting(item["id"], current_user) for item in list_meetings(current_user)]
    confirmed: Counter[str] = Counter()
    excluded: Counter[str] = Counter()
    collaborators: Counter[str] = Counter()

    for meeting in meetings:
        if not meeting:
            continue
        for task in meeting["analysis"].get("all_tasks", []):
            title = str(task.get("task") or "").strip()
            if not is_profile_task(title):
                continue
            status = str(task.get("status") or "")
            if task.get("personal") is True or status in {"已确认", "已修改"}:
                confirmed[title] += 1
                for name in str(task.get("assignee") or "").split("、"):
                    if name and name != current_user and name != "待确认":
                        collaborators[name] += 1
            if task.get("personal") is False or status == "已忽略":
                excluded[title] += 1

    return {
        "current_user": current_user,
        "saved_meeting_count": len(meetings),
        "confirmed_tasks": [title for title, _ in confirmed.most_common(5)],
        "excluded_tasks": [title for title, _ in excluded.most_common(5)],
        "collaborators": [name for name, _ in collaborators.most_common(5)],
    }


def _compact_text(value: str) -> str:
    return "".join(character for character in value if character.isalnum())


def is_profile_task(title: str) -> bool:
    compact = _compact_text(title)
    return len(compact) >= 4 and compact not in VAGUE_PROFILE_TASKS and not compact.endswith("一下")


def relevant_feedback(current_user: str, transcript: str, limit: int = 4) -> list[dict[str, str]]:
    transcript_key = _compact_text(transcript)
    candidates = []
    for item in list_meetings(current_user):
        meeting = get_meeting(item["id"], current_user)
        if not meeting:
            continue
        for task in meeting["analysis"].get("all_tasks", []):
            title = str(task.get("task") or "").strip()
            status = str(task.get("status") or "")
            if not is_profile_task(title):
                continue
            if task.get("personal") is True or status in {"已确认", "已修改"}:
                decision = "归入我的任务"
            elif task.get("personal") is False or status == "已忽略":
                decision = "排除为非我的任务"
            else:
                continue
            title_key = _compact_text(title)
            overlap = len(set(title_key) & set(transcript_key))
            score = overlap / max(1, len(set(title_key)))
            candidates.append({"task": title, "decision": decision, "score": score})

    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = [item for item in candidates if item["score"] > 0][:limit]
    return selected or candidates[:limit]


def personalization(current_user: str, transcript: str = "") -> dict[str, Any]:
    if not current_user.strip():
        return {"context": "", "notes": []}
    profile = build_personal_profile(current_user)
    if not profile["confirmed_tasks"] and not profile["excluded_tasks"]:
        return {"context": "", "notes": []}

    lines = ["用户历史反馈（仅用于辅助判断模糊候选任务）："]
    notes = [f"已读取 {profile['saved_meeting_count']} 场历史会议中的人工反馈"]
    if profile["confirmed_tasks"]:
        lines.append(f"- 常被用户确认是自己的任务：{'、'.join(profile['confirmed_tasks'])}")
    if profile["excluded_tasks"]:
        lines.append(f"- 常被用户排除的任务：{'、'.join(profile['excluded_tasks'])}")
    if profile["collaborators"]:
        lines.append(f"- 近期协作者：{'、'.join(profile['collaborators'])}")
    feedback = relevant_feedback(current_user, transcript)
    if feedback:
        lines.append("- 与当前会议最相关的历史判断：")
        lines.extend(f"  - {item['task']}：用户曾选择“{item['decision']}”" for item in feedback)
        notes.append("本次重点参考：" + "、".join(item["task"] for item in feedback[:3]))
    lines.append("当前会议原文中的明确负责人、否定或任务状态优先级更高，不可被历史反馈覆盖。")
    return {"context": "\n".join(lines), "notes": notes}


def personal_context(current_user: str, transcript: str = "") -> str:
    return str(personalization(current_user, transcript)["context"])
