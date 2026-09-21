from typing import Any

from pydantic import BaseModel, Field


class MeetingHistoryPayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    transcript: str = Field(min_length=1)
    analysis: dict[str, Any]
    audio_name: str = ""

