import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
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
            folder_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_meetings)")}
    if "folder_id" not in columns:
        connection.execute("ALTER TABLE saved_meetings ADD COLUMN folder_id TEXT NOT NULL DEFAULT ''")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recording_folders (
            id TEXT PRIMARY KEY,
            current_user TEXT NOT NULL,
            name TEXT NOT NULL,
            keywords_json TEXT NOT NULL DEFAULT '[]',
            aliases_json TEXT NOT NULL DEFAULT '[]',
            image_keywords_json TEXT NOT NULL DEFAULT '[]',
            image_status TEXT NOT NULL DEFAULT '',
            image_requested_at TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    folder_columns = {row["name"] for row in connection.execute("PRAGMA table_info(recording_folders)")}
    if "image_status" not in folder_columns:
        connection.execute("ALTER TABLE recording_folders ADD COLUMN image_status TEXT NOT NULL DEFAULT ''")
    if "image_keywords_json" not in folder_columns:
        connection.execute("ALTER TABLE recording_folders ADD COLUMN image_keywords_json TEXT NOT NULL DEFAULT '[]'")
    if "image_requested_at" not in folder_columns:
        connection.execute("ALTER TABLE recording_folders ADD COLUMN image_requested_at TEXT NOT NULL DEFAULT ''")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_todos (
            id TEXT PRIMARY KEY,
            current_user TEXT NOT NULL,
            title TEXT NOT NULL,
            deadline TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _todo_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "current_user": row["current_user"],
        "title": row["title"],
        "deadline": row["deadline"],
        "completed": bool(row["completed"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_personal_todos(current_user: str) -> list[dict[str, Any]]:
    if not current_user.strip():
        return []
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM personal_todos WHERE current_user = ? ORDER BY completed ASC, created_at DESC",
            (current_user.strip(),),
        ).fetchall()
    return [_todo_from_row(row) for row in rows]


def create_personal_todo(payload: dict[str, Any]) -> dict[str, Any]:
    user = str(payload["current_user"]).strip()
    title = str(payload["title"]).strip()
    if not user or not title:
        raise ValueError("账号和任务内容不能为空")
    now = datetime.now(timezone.utc).isoformat()
    todo_id = str(uuid.uuid4())
    with _connection() as connection:
        connection.execute(
            "INSERT INTO personal_todos (id, current_user, title, deadline, completed, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (todo_id, user, title, str(payload.get("deadline") or "").strip(), int(bool(payload.get("completed", False))), now, now),
        )
        row = connection.execute("SELECT * FROM personal_todos WHERE id = ?", (todo_id,)).fetchone()
    return _todo_from_row(row)


def update_personal_todo(todo_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    user = str(payload["current_user"]).strip()
    title = str(payload["title"]).strip()
    if not user or not title:
        raise ValueError("账号和任务内容不能为空")
    with _connection() as connection:
        changed = connection.execute(
            """UPDATE personal_todos SET title = ?, deadline = ?, completed = ?, updated_at = ?
            WHERE id = ? AND current_user = ?""",
            (title, str(payload.get("deadline") or "").strip(), int(bool(payload.get("completed", False))), datetime.now(timezone.utc).isoformat(), todo_id, user),
        ).rowcount
        if not changed:
            return None
        row = connection.execute("SELECT * FROM personal_todos WHERE id = ?", (todo_id,)).fetchone()
    return _todo_from_row(row)


def delete_personal_todo(todo_id: str, current_user: str) -> bool:
    with _connection() as connection:
        deleted = connection.execute(
            "DELETE FROM personal_todos WHERE id = ? AND current_user = ?",
            (todo_id, current_user.strip()),
        ).rowcount
    return bool(deleted)


def _folder_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "current_user": row["current_user"],
        "name": row["name"],
        "keywords": json.loads(row["keywords_json"] or "[]"),
        "aliases": json.loads(row["aliases_json"] or "[]"),
        "image_keywords": json.loads(row["image_keywords_json"] or "[]"),
        "image_status": row["image_status"],
        "image_available": (DATA_DIR / "folder-images" / f"{row['id']}.webp").is_file(),
        "is_default": bool(row["is_default"]),
    }


def ensure_default_folder(current_user: str) -> dict[str, Any]:
    user = current_user.strip()
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM recording_folders WHERE current_user = ? AND is_default = 1 LIMIT 1",
            (user,),
        ).fetchone()
        if not row:
            folder_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO recording_folders
                (id, current_user, name, keywords_json, aliases_json, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (folder_id, user, "默认文件夹", "[]", json.dumps([user], ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
            row = connection.execute("SELECT * FROM recording_folders WHERE id = ?", (folder_id,)).fetchone()
        connection.execute(
            "UPDATE saved_meetings SET folder_id = ? WHERE current_user = ? AND folder_id = ''",
            (row["id"], user),
        )
    return _folder_from_row(row)


def list_folders(current_user: str) -> list[dict[str, Any]]:
    user = current_user.strip()
    if not user:
        return []
    ensure_default_folder(user)
    with _connection() as connection:
        connection.execute(
            """UPDATE recording_folders SET image_status = 'failed'
            WHERE current_user = ? AND image_status = 'pending' AND image_requested_at < ?""",
            (user, (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()),
        )
        rows = connection.execute(
            "SELECT * FROM recording_folders WHERE current_user = ? ORDER BY is_default DESC, created_at ASC",
            (user,),
        ).fetchall()
        counts = {
            row["folder_id"]: row["count"]
            for row in connection.execute(
                "SELECT folder_id, COUNT(*) AS count FROM saved_meetings WHERE current_user = ? GROUP BY folder_id",
                (user,),
            )
        }
    folders = [_folder_from_row(row) for row in rows]
    for folder in folders:
        folder["meeting_count"] = counts.get(folder["id"], 0)
    return folders


def suggest_folder(current_user: str, transcript: str, meeting_title: str = "", summary: str = "") -> dict[str, Any] | None:
    title = meeting_title.casefold()
    overview = summary.casefold()
    body = transcript.casefold()
    ranked = []
    for folder in list_folders(current_user):
        if folder["is_default"]:
            continue
        matched = []
        score = 0
        for keyword in dict.fromkeys(item.strip().casefold() for item in folder["keywords"] if len(item.strip()) >= 2):
            weight = 3 if keyword in title else 2 if keyword in overview else 1 if keyword in body else 0
            if weight:
                matched.append(keyword)
                score += weight
        ranked.append((score, folder, matched))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return None
    score, folder, matched = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0
    if len(matched) < 2 or score - runner_up < 2:
        return None
    return {"folder_id": folder["id"], "name": folder["name"], "matched_keywords": matched}


def create_folder(payload: dict[str, Any]) -> dict[str, Any]:
    user = str(payload["current_user"]).strip()
    name = str(payload["name"]).strip()
    ensure_default_folder(user)
    folder_id = str(uuid.uuid4())
    with _connection() as connection:
        connection.execute(
            """INSERT INTO recording_folders
            (id, current_user, name, keywords_json, aliases_json, image_keywords_json, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                folder_id,
                user,
                name,
                json.dumps([item.strip() for item in payload.get("keywords", []) if item.strip()], ensure_ascii=False),
                json.dumps([item.strip() for item in payload.get("aliases", []) if item.strip()], ensure_ascii=False),
                json.dumps(list(dict.fromkeys(item.strip() for item in payload.get("image_keywords", []) if item.strip())), ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row = connection.execute("SELECT * FROM recording_folders WHERE id = ?", (folder_id,)).fetchone()
    return _folder_from_row(row)


def set_folder_image_keywords(folder_id: str, current_user: str, keywords: list[str]) -> bool:
    cleaned = list(dict.fromkeys(item.strip() for item in keywords if item.strip()))
    with _connection() as connection:
        changed = connection.execute(
            """UPDATE recording_folders SET image_keywords_json = ?
            WHERE id = ? AND current_user = ? AND is_default = 0""",
            (json.dumps(cleaned, ensure_ascii=False), folder_id, current_user.strip()),
        ).rowcount
    return bool(changed)


def set_folder_image_status(folder_id: str, current_user: str, status: str) -> bool:
    if status not in {"pending", "ready", "failed", "unavailable"}:
        raise ValueError("无效的图片状态")
    requested_at = datetime.now(timezone.utc).isoformat() if status == "pending" else None
    with _connection() as connection:
        changed = connection.execute(
            """UPDATE recording_folders
            SET image_status = ?, image_requested_at = COALESCE(?, image_requested_at)
            WHERE id = ? AND current_user = ? AND is_default = 0""",
            (status, requested_at, folder_id, current_user.strip()),
        ).rowcount
    return bool(changed)


def update_folder(folder_id: str, current_user: str, keywords: list[str], aliases: list[str]) -> dict[str, Any] | None:
    with _connection() as connection:
        cursor = connection.execute(
            """UPDATE recording_folders SET keywords_json = ?, aliases_json = ?
            WHERE id = ? AND current_user = ?""",
            (
                json.dumps(list(dict.fromkeys(item.strip() for item in keywords if item.strip())), ensure_ascii=False),
                json.dumps(list(dict.fromkeys(item.strip() for item in aliases if item.strip())), ensure_ascii=False),
                folder_id,
                current_user.strip(),
            ),
        )
        if not cursor.rowcount:
            return None
        row = connection.execute("SELECT * FROM recording_folders WHERE id = ?", (folder_id,)).fetchone()
    return _folder_from_row(row)


def delete_folder(folder_id: str, current_user: str) -> int | None:
    user = current_user.strip()
    with _connection() as connection:
        row = connection.execute(
            "SELECT is_default FROM recording_folders WHERE id = ? AND current_user = ?",
            (folder_id, user),
        ).fetchone()
        if row is None:
            return None
        if row["is_default"]:
            raise ValueError("默认文件夹不能删除")
        default_row = connection.execute(
            "SELECT id FROM recording_folders WHERE current_user = ? AND is_default = 1",
            (user,),
        ).fetchone()
        if default_row:
            default_id = default_row["id"]
        else:
            default_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO recording_folders
                (id, current_user, name, keywords_json, aliases_json, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (default_id, user, "默认文件夹", "[]", json.dumps([user], ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
        moved = connection.execute(
            "UPDATE saved_meetings SET folder_id = ? WHERE current_user = ? AND folder_id = ?",
            (default_id, user, folder_id),
        ).rowcount
        connection.execute(
            "DELETE FROM recording_folders WHERE id = ? AND current_user = ?",
            (folder_id, user),
        )
    (DATA_DIR / "folder-images" / f"{folder_id}.webp").unlink(missing_ok=True)
    return moved


def get_folder(folder_id: str, current_user: str) -> dict[str, Any] | None:
    if not folder_id:
        return ensure_default_folder(current_user)
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM recording_folders WHERE id = ? AND current_user = ?",
            (folder_id, current_user.strip()),
        ).fetchone()
    return _folder_from_row(row) if row else None


def _record_from_row(row: sqlite3.Row, include_content: bool = False) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "current_user": row["current_user"],
        "meeting_title": row["meeting_title"],
        "audio_name": row["audio_name"],
        "folder_id": row["folder_id"],
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
    folder = get_folder(str(payload.get("folder_id") or ""), payload["current_user"])
    folder_id = folder["id"] if folder else ensure_default_folder(payload["current_user"])["id"]
    values = (
        record_id,
        payload["current_user"].strip(),
        title,
        payload["transcript"],
        json.dumps(analysis, ensure_ascii=False),
        payload.get("audio_name", ""),
        folder_id,
        now,
        now,
    )
    with _connection() as connection:
        if meeting_id:
            connection.execute(
                """
                UPDATE saved_meetings
                SET current_user = ?, meeting_title = ?, transcript = ?, analysis_json = ?,
                    audio_name = ?, folder_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (values[1], values[2], values[3], values[4], values[5], values[6], now, record_id),
            )
        else:
            connection.execute(
                """
                INSERT INTO saved_meetings (
                    id, current_user, meeting_title, transcript, analysis_json,
                    audio_name, folder_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        row = connection.execute("SELECT * FROM saved_meetings WHERE id = ?", (record_id,)).fetchone()
    return _record_from_row(row, include_content=True)


def list_meetings(current_user: str, folder_id: str = "") -> list[dict[str, Any]]:
    folder = get_folder(folder_id, current_user) if folder_id else None
    with _connection() as connection:
        if folder:
            rows = connection.execute(
                "SELECT * FROM saved_meetings WHERE current_user = ? AND folder_id = ? ORDER BY updated_at DESC",
                (current_user.strip(), folder["id"]),
            ).fetchall()
        else:
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


def delete_meeting(meeting_id: str, current_user: str) -> bool:
    with _connection() as connection:
        deleted = connection.execute(
            "DELETE FROM saved_meetings WHERE id = ? AND current_user = ?",
            (meeting_id, current_user.strip()),
        ).rowcount
    return bool(deleted)


def build_personal_profile(current_user: str, folder_id: str = "") -> dict[str, Any]:
    meetings = [get_meeting(item["id"], current_user) for item in list_meetings(current_user, folder_id)]
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


def relevant_feedback(current_user: str, transcript: str, limit: int = 4, folder_id: str = "") -> list[dict[str, str]]:
    transcript_key = _compact_text(transcript)
    candidates = []
    for item in list_meetings(current_user, folder_id):
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


def personalization(current_user: str, transcript: str = "", folder_id: str = "") -> dict[str, Any]:
    if not current_user.strip():
        return {"context": "", "notes": []}
    profile = build_personal_profile(current_user, folder_id)
    folder = get_folder(folder_id, current_user) if folder_id else None
    if not profile["confirmed_tasks"] and not profile["excluded_tasks"] and not folder:
        return {"context": "", "notes": []}

    lines = ["用户历史反馈（仅用于辅助判断模糊候选任务）："]
    notes = [f"已读取 {profile['saved_meeting_count']} 场历史会议中的人工反馈"]
    if folder:
        aliases = [current_user, *folder["aliases"]]
        lines.append(f"- 当前场景文件夹：{folder['name']}")
        lines.append(f"- 当前账号本人可被称为：{'、'.join(dict.fromkeys(alias for alias in aliases if alias))}")
        if folder["keywords"]:
            lines.append(f"- 当前场景关键词：{'、'.join(folder['keywords'])}")
        notes.append(f"当前场景：{folder['name']}")
    if profile["confirmed_tasks"]:
        lines.append(f"- 常被用户确认是自己的任务：{'、'.join(profile['confirmed_tasks'])}")
    if profile["excluded_tasks"]:
        lines.append(f"- 常被用户排除的任务：{'、'.join(profile['excluded_tasks'])}")
    if profile["collaborators"]:
        lines.append(f"- 近期协作者：{'、'.join(profile['collaborators'])}")
    feedback = relevant_feedback(current_user, transcript, folder_id=folder_id)
    if feedback:
        lines.append("- 与当前会议最相关的历史判断：")
        lines.extend(f"  - {item['task']}：用户曾选择“{item['decision']}”" for item in feedback)
        notes.append("本次重点参考：" + "、".join(item["task"] for item in feedback[:3]))
    lines.append("当前会议原文中的明确负责人、否定或任务状态优先级更高，不可被历史反馈覆盖。")
    return {"context": "\n".join(lines), "notes": notes}


def personal_context(current_user: str, transcript: str = "", folder_id: str = "") -> str:
    return str(personalization(current_user, transcript, folder_id)["context"])
