from typing import Annotated, Any
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MeetingHistoryPayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    transcript: str = Field(min_length=1)
    analysis: dict[str, Any]
    audio_name: str = ""
    folder_id: str = ""


class RecordingFolderPayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    keywords: list[str] = []
    aliases: list[str] = []
    image_keywords: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=8)


class RecordingFolderImagePayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    image_keywords: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=8)


class RecordingFolderUpdatePayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    keywords: list[str] = []
    aliases: list[str] = []


class FolderSuggestionPayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    transcript: str = Field(min_length=1)
    meeting_title: str = ""
    summary: str = ""


class PersonalTodoPayload(BaseModel):
    current_user: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    deadline: str = Field(default="", max_length=80)
    due_at: str = Field(default="", max_length=32)
    completed: bool = False

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: str) -> str:
        if value:
            datetime.fromisoformat(value)
        return value
