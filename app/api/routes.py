import json

from fastapi import APIRouter, File, Form, UploadFile

from app.models.meeting import MeetingAnalysis, MeetingMarker
from app.services.meeting_analyzer import (
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
        )

    return build_demo_analysis(parsed_markers)
