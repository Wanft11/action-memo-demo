import json
import mimetypes
import re

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.meeting_analyzer import marker_insights_from_transcript
from app.models.history import FolderSuggestionPayload, MeetingHistoryPayload, PersonalTodoPayload, RecordingFolderImagePayload, RecordingFolderPayload, RecordingFolderUpdatePayload, SavedTaskUpdatePayload
from app.models.meeting import MeetingAnalysis, MeetingFocusAnalysis, MeetingMarker
from app.services.personal_memory import (
    build_personal_profile,
    create_personal_todo,
    create_folder,
    delete_personal_todo,
    delete_folder,
    delete_meeting,
    folder_focus_transcript,
    get_folder,
    get_meeting,
    list_folders,
    list_personal_todos,
    update_folder,
    update_personal_todo,
    list_meetings,
    meeting_audio_path,
    personal_context,
    personalization,
    save_meeting,
    store_meeting_audio,
    set_folder_image_keywords,
    set_folder_image_status,
    suggest_folder,
    update_saved_task,
)
from app.services.folder_images import folder_image_path, generate_folder_image
from app.services.meeting_analyzer import (
    analyze_personal_focus,
    analyze_transcript_with_llm,
    has_openai_key,
    transcribe_audio_bytes,
)


router = APIRouter()


async def _transcribe_upload(audio: UploadFile) -> str:
    if not has_openai_key():
        raise HTTPException(status_code=503, detail="录音转写暂不可用：请先配置语音 API Key，或改用文字转写。")
    audio_bytes = await audio.read(25 * 1024 * 1024 + 1)
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="录音文件为空，请重新选择。")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="录音文件超过 25 MB，请压缩或分段后重试。")
    if not (audio.filename or "").lower().endswith((".mp3", ".mp4", ".m4a", ".wav", ".webm", ".mpeg", ".mpga", ".ogg", ".flac")):
        raise HTTPException(status_code=422, detail="不支持这个录音格式，请选择常见音频文件。")
    try:
        text = transcribe_audio_bytes(audio_bytes, filename=audio.filename or "meeting.mp3", content_type=audio.content_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="录音转写失败，请检查文件或网络后重试。") from exc
    if not text.strip():
        raise HTTPException(status_code=502, detail="没有识别出录音内容，请检查文件后重试。")
    return text


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meetings/history")
def meeting_history(current_user: str = "", folder_id: str = "") -> list[dict]:
    if not current_user.strip():
        return []
    return list_meetings(current_user, folder_id)


@router.get("/meetings/todos")
def personal_todos(current_user: str = "") -> list[dict]:
    return list_personal_todos(current_user)


@router.post("/meetings/todos")
def add_personal_todo(payload: PersonalTodoPayload) -> dict:
    try:
        return create_personal_todo(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/meetings/todos/{todo_id}")
def edit_personal_todo(todo_id: str, payload: PersonalTodoPayload) -> dict:
    try:
        todo = update_personal_todo(todo_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not todo:
        raise HTTPException(status_code=404, detail="没有找到这条待办")
    return todo


@router.delete("/meetings/todos/{todo_id}")
def remove_personal_todo(todo_id: str, current_user: str = "") -> dict:
    if not delete_personal_todo(todo_id, current_user):
        raise HTTPException(status_code=404, detail="没有找到这条待办")
    return {"deleted": True}


@router.get("/meetings/folders")
def meeting_folders(current_user: str = "") -> list[dict]:
    return list_folders(current_user)


@router.post("/meetings/folders")
def create_meeting_folder(payload: RecordingFolderPayload, background_tasks: BackgroundTasks) -> dict:
    folder = create_folder(payload.model_dump())
    status = "pending" if settings.openai_api_key.strip() else "unavailable"
    set_folder_image_status(folder["id"], payload.current_user, status)
    if status == "pending":
        background_tasks.add_task(generate_folder_image, folder["id"], payload.current_user)
    folder["image_status"] = status
    return folder


@router.post("/meetings/folders/{folder_id}/image")
def retry_folder_image(folder_id: str, payload: RecordingFolderImagePayload, background_tasks: BackgroundTasks) -> dict:
    folder = get_folder(folder_id, payload.current_user)
    if not folder or folder["is_default"]:
        raise HTTPException(status_code=404, detail="没有找到这个文件夹")
    if not settings.openai_api_key.strip():
        raise HTTPException(status_code=503, detail="尚未配置图片生成 API Key")
    if folder["image_status"] != "pending":
        set_folder_image_keywords(folder_id, payload.current_user, payload.image_keywords)
        set_folder_image_status(folder_id, payload.current_user, "pending")
        background_tasks.add_task(generate_folder_image, folder_id, payload.current_user)
    return {"image_status": "pending"}


@router.get("/meetings/folders/{folder_id}/image")
def meeting_folder_image(folder_id: str, current_user: str) -> FileResponse:
    folder = get_folder(folder_id, current_user)
    if not folder or not folder["image_available"]:
        raise HTTPException(status_code=404, detail="没有找到文件夹图片")
    path = folder_image_path(folder_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="没有找到文件夹图片")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-store"})


@router.post("/meetings/folders/suggest")
def suggest_meeting_folder(payload: FolderSuggestionPayload) -> dict:
    return {"suggestion": suggest_folder(payload.current_user, payload.transcript, payload.meeting_title, payload.summary)}


@router.put("/meetings/folders/{folder_id}")
def update_meeting_folder(folder_id: str, payload: RecordingFolderUpdatePayload) -> dict:
    folder = update_folder(folder_id, payload.current_user, payload.keywords, payload.aliases, payload.focus_modes)
    if not folder:
        raise HTTPException(status_code=404, detail="没有找到这个文件夹")
    return folder


@router.delete("/meetings/folders/{folder_id}")
def delete_meeting_folder(folder_id: str, current_user: str = "") -> dict:
    try:
        moved_count = delete_folder(folder_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if moved_count is None:
        raise HTTPException(status_code=404, detail="没有找到这个文件夹")
    return {"moved_count": moved_count}


@router.get("/meetings/history/{meeting_id}")
def meeting_history_item(meeting_id: str, current_user: str = "") -> dict:
    record = get_meeting(meeting_id, current_user)
    if not record:
        raise HTTPException(status_code=404, detail="没有找到这条本地记录")
    return record


@router.get("/meetings/tasks")
def meeting_tasks(current_user: str = "") -> list[dict]:
    if not current_user.strip():
        return []
    records = list_meetings(current_user)
    tasks = []
    for summary in records:
        record = get_meeting(summary["id"], current_user)
        if not record:
            continue
        folder = get_folder(record.get("folder_id", ""), current_user)
        aliases = [current_user.strip(), *((folder or {}).get("aliases") or [])]
        analysis = record.get("analysis") or {}
        for index, task in enumerate(analysis.get("all_tasks") or []):
            task = dict(task)
            task.update({
                "record_id": record["id"], "record_title": record["meeting_title"],
                "record_index": index, "record_created_at": record["created_at"],
                "record_folder_id": record.get("folder_id", ""), "identity_confirmed": analysis.get("identity_confirmed", True),
                "identity_aliases": aliases,
            })
            tasks.append(task)
    return tasks


@router.patch("/meetings/history/{meeting_id}/tasks/{task_index}")
def update_meeting_task(meeting_id: str, task_index: int, payload: SavedTaskUpdatePayload) -> dict:
    record = update_saved_task(meeting_id, payload.current_user, task_index, payload.fields.model_dump(exclude_unset=True))
    if not record:
        raise HTTPException(status_code=404, detail="没有找到这条任务或对应记录")
    return record


@router.post("/meetings/history/{meeting_id}/audio")
async def attach_meeting_audio(meeting_id: str, current_user: str = Form(), audio: UploadFile = File()) -> dict:
    audio_bytes = await audio.read()
    try:
        store_meeting_audio(meeting_id, current_user, audio.filename or "", audio_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"audio_available": True}


@router.get("/meetings/history/{meeting_id}/audio")
def get_meeting_audio(meeting_id: str, current_user: str = "") -> FileResponse:
    if not get_meeting(meeting_id, current_user):
        raise HTTPException(status_code=404, detail="没有找到这条本地记录")
    audio = meeting_audio_path(meeting_id)
    if not audio:
        raise HTTPException(status_code=404, detail="这条记录没有保存的原音频")
    return FileResponse(audio, media_type=mimetypes.guess_type(audio.name)[0] or "application/octet-stream")


@router.post("/meetings/history")
def create_meeting_history(payload: MeetingHistoryPayload) -> dict:
    return save_meeting(payload.model_dump())


@router.put("/meetings/history/{meeting_id}")
def update_meeting_history(meeting_id: str, payload: MeetingHistoryPayload) -> dict:
    existing = get_meeting(meeting_id, payload.current_user)
    if not existing:
        raise HTTPException(status_code=404, detail="没有找到这条本地记录")
    return save_meeting(payload.model_dump(), meeting_id=meeting_id)


@router.delete("/meetings/history/{meeting_id}")
def delete_meeting_history(meeting_id: str, current_user: str = "") -> dict:
    if not delete_meeting(meeting_id, current_user):
        raise HTTPException(status_code=404, detail="没有找到这条本地记录")
    return {"deleted": True}


@router.get("/meetings/profile")
def meeting_profile(current_user: str = "", folder_id: str = "") -> dict:
    if not current_user.strip():
        return {
            "current_user": "",
            "saved_meeting_count": 0,
            "confirmed_tasks": [],
            "excluded_tasks": [],
            "collaborators": [],
        }
    return build_personal_profile(current_user, folder_id)


@router.post("/meetings/focus", response_model=MeetingFocusAnalysis)
def analyze_focus(
    transcript: str = Form(default=""),
    current_user: str = Form(default=""),
    focus_query: str = Form(default=""),
    folder_id: str = Form(default=""),
    markers: str = Form(default="[]"),
) -> MeetingFocusAnalysis:
    scoped_transcript = transcript.strip()
    if folder_id.strip():
        scoped_transcript = folder_focus_transcript(current_user, folder_id, focus_query)
    if not scoped_transcript:
        raise HTTPException(status_code=422, detail="请先提供转写内容")
    if not focus_query.strip():
        raise HTTPException(status_code=422, detail="请输入想关注的重点")

    try:
        parsed_markers = [MeetingMarker.model_validate(item) for item in json.loads(markers)]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="重点事件格式不正确")
    analysis = analyze_personal_focus(
        transcript=scoped_transcript,
        current_user=current_user,
        focus_query=focus_query,
        personal_context=personal_context(current_user, scoped_transcript, folder_id),
    )
    if not folder_id:
        analysis.marker_insights = marker_insights_from_transcript(
            scoped_transcript.splitlines(), current_user, parsed_markers, []
        )
    return analysis


@router.post("/meetings/transcribe")
async def transcribe_meeting(audio: UploadFile = File()) -> dict[str, str]:
    return {"transcript": await _transcribe_upload(audio)}


@router.post("/meetings/analyze", response_model=MeetingAnalysis)
async def analyze_meeting(
    audio: UploadFile | None = File(default=None),
    transcript: str = Form(default=""),
    current_user: str = Form(default=""),
    markers: str = Form(default="[]"),
    folder_id: str = Form(default=""),
    confirmed_speaker: str = Form(default=""),
) -> MeetingAnalysis:
    parsed_markers = [
        MeetingMarker.model_validate(marker) for marker in json.loads(markers or "[]")
    ]

    def analyze_with_memory(content: str) -> MeetingAnalysis:
        speakers = {
            match.group(1).strip()
            for line in content.splitlines()
            if (match := re.match(r"^(?:\d{1,2}:\d{2}(?::\d{2})?\s+)?((?:说话人|Speaker)\s*\d+|[\u4e00-\u9fff]{1,8})[：:]", line.strip()))
            and match.group(1).strip() not in {"会议主题", "录音主题", "对话主题", "主题", "参会人", "会议时长"}
        }
        confirmed = bool(current_user.strip() and confirmed_speaker.strip() in speakers)
        analysis_user = current_user.strip() if confirmed else ""
        if confirmed and confirmed_speaker.strip() != analysis_user:
            content = re.sub(
                rf"(?m)^((?:\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s+)?){re.escape(confirmed_speaker.strip())}([：:])",
                lambda match: f"{match.group(1)}{analysis_user}{match.group(2)}",
                content,
            )
        memory = personalization(analysis_user, content, folder_id) if confirmed else {"context": "", "notes": []}
        analysis = analyze_transcript_with_llm(
            transcript=content,
            current_user=analysis_user,
            markers=parsed_markers,
            personal_context=str(memory["context"]),
        )
        if not analysis.demo_mode:
            analysis.personalization_notes = list(memory["notes"])
        analysis.identity_confirmed = confirmed
        if not confirmed:
            analysis.my_tasks = []
            analysis.risks.insert(0, "尚未确认哪位说话人是你；请在任务清单中手动认领，或确认身份后重新生成。")
        return analysis

    if transcript.strip():
        return analyze_with_memory(transcript)

    if audio:
        return analyze_with_memory(await _transcribe_upload(audio))

    raise HTTPException(status_code=422, detail="请上传录音，或粘贴文字转写。")
