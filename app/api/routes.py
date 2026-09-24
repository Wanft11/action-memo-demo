import json
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.history import FolderSuggestionPayload, MeetingHistoryPayload, RecordingFolderPayload, RecordingFolderUpdatePayload
from app.models.meeting import MeetingAnalysis, MeetingFocusAnalysis, MeetingMarker
from app.services.personal_memory import (
    build_personal_profile,
    create_folder,
    delete_folder,
    delete_meeting,
    get_folder,
    get_meeting,
    list_folders,
    update_folder,
    list_meetings,
    personal_context,
    personalization,
    save_meeting,
    suggest_folder,
)
from app.services.meeting_analyzer import (
    analyze_personal_focus,
    analyze_transcript_with_llm,
    build_local_transcript_analysis,
    build_demo_analysis,
    has_openai_key,
    transcribe_audio_bytes,
)


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meetings/history")
def meeting_history(current_user: str = "", folder_id: str = "") -> list[dict]:
    if not current_user.strip():
        return []
    return list_meetings(current_user, folder_id)


@router.get("/meetings/folders")
def meeting_folders(current_user: str = "") -> list[dict]:
    return list_folders(current_user)


@router.post("/meetings/folders")
def create_meeting_folder(payload: RecordingFolderPayload) -> dict:
    return create_folder(payload.model_dump())


@router.post("/meetings/folders/suggest")
def suggest_meeting_folder(payload: FolderSuggestionPayload) -> dict:
    return {"suggestion": suggest_folder(payload.current_user, payload.transcript, payload.meeting_title, payload.summary)}


@router.put("/meetings/folders/{folder_id}")
def update_meeting_folder(folder_id: str, payload: RecordingFolderUpdatePayload) -> dict:
    folder = update_folder(folder_id, payload.current_user, payload.keywords, payload.aliases)
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
) -> MeetingFocusAnalysis:
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="请先提供转写内容")
    if not focus_query.strip():
        raise HTTPException(status_code=422, detail="请输入想关注的重点")

    return analyze_personal_focus(
        transcript=transcript,
        current_user=current_user,
        focus_query=focus_query,
        personal_context=personal_context(current_user, transcript, folder_id),
    )


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

    if audio and has_openai_key():
        audio_bytes = await audio.read()
        try:
            transcribed_text = transcribe_audio_bytes(
                audio_bytes=audio_bytes,
                filename=audio.filename or "meeting.mp3",
                content_type=audio.content_type,
            )
        except Exception as exc:
            analysis = build_local_transcript_analysis(
                transcript=f"录音文件：{audio.filename or 'meeting'}",
                current_user="",
                markers=parsed_markers,
                warning=f"OpenAI 语音转写失败，已自动切回本地解析：{exc.__class__.__name__}",
            )
            analysis.identity_confirmed = False
            return analysis
        return analyze_with_memory(transcribed_text)

    analysis = build_demo_analysis(parsed_markers)
    analysis.identity_confirmed = False
    analysis.my_tasks = []
    for task in analysis.all_tasks:
        if task.assignee == "我":
            task.assignee = "待确认"
    return analysis
