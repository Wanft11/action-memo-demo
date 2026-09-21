import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.history import MeetingHistoryPayload
from app.models.meeting import MeetingAnalysis, MeetingFocusAnalysis, MeetingMarker
from app.services.personal_memory import (
    build_personal_profile,
    get_meeting,
    list_meetings,
    personal_context,
    save_meeting,
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
def meeting_history(current_user: str = "") -> list[dict]:
    if not current_user.strip():
        return []
    return list_meetings(current_user)


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


@router.get("/meetings/profile")
def meeting_profile(current_user: str = "") -> dict:
    if not current_user.strip():
        return {
            "current_user": "",
            "saved_meeting_count": 0,
            "confirmed_tasks": [],
            "excluded_tasks": [],
            "collaborators": [],
        }
    return build_personal_profile(current_user)


@router.post("/meetings/focus", response_model=MeetingFocusAnalysis)
def analyze_focus(
    transcript: str = Form(default=""),
    current_user: str = Form(default=""),
    focus_query: str = Form(default=""),
) -> MeetingFocusAnalysis:
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="请先提供会议转写内容")
    if not focus_query.strip():
        raise HTTPException(status_code=422, detail="请输入想关注的重点")

    return analyze_personal_focus(
        transcript=transcript,
        current_user=current_user,
        focus_query=focus_query,
    )


@router.post("/meetings/analyze", response_model=MeetingAnalysis)
async def analyze_meeting(
    audio: UploadFile | None = File(default=None),
    transcript: str = Form(default=""),
    current_user: str = Form(default=""),
    markers: str = Form(default="[]"),
) -> MeetingAnalysis:
    parsed_markers = [
        MeetingMarker.model_validate(marker) for marker in json.loads(markers or "[]")
    ]

    if transcript.strip():
        return analyze_transcript_with_llm(
            transcript=transcript,
            current_user=current_user,
            markers=parsed_markers,
            personal_context=personal_context(current_user),
        )

    if audio and has_openai_key():
        audio_bytes = await audio.read()
        try:
            transcribed_text = transcribe_audio_bytes(
                audio_bytes=audio_bytes,
                filename=audio.filename or "meeting.mp3",
                content_type=audio.content_type,
            )
        except Exception as exc:
            return build_local_transcript_analysis(
                transcript=f"录音文件：{audio.filename or 'meeting'}",
                current_user=current_user,
                markers=parsed_markers,
                warning=f"OpenAI 语音转写失败，已自动切回本地解析：{exc.__class__.__name__}",
            )
        return analyze_transcript_with_llm(
            transcript=transcribed_text,
            current_user=current_user,
            markers=parsed_markers,
            personal_context=personal_context(current_user),
        )

    return build_demo_analysis(parsed_markers)
