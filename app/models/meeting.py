from pydantic import BaseModel, Field


class MeetingMarker(BaseModel):
    label: str = "重点标记"
    time: str = Field(..., examples=["14:32"])
    note: str | None = None


class MeetingTask(BaseModel):
    task: str
    assignee: str
    deadline: str
    source: str
    evidence: str
    status: str = "待确认"
    confidence: float = Field(default=0.88, ge=0, le=1)


class MeetingInsight(BaseModel):
    title: str
    source: str = "会议讨论"
    evidence: str


class MeetingFocusSource(BaseModel):
    source: str
    evidence: str
    reason: str = ""


class MeetingFocusAnalysis(BaseModel):
    query: str
    title: str
    answer: str
    sources: list[MeetingFocusSource]
    demo_mode: bool = True


class MeetingAnalysis(BaseModel):
    meeting_title: str
    summary: str
    decisions: list[str]
    my_tasks: list[MeetingTask]
    all_tasks: list[MeetingTask] = []
    risks: list[str]
    questions: list[MeetingInsight] = []
    evidence_notes: list[MeetingInsight] = []
    marked_moments: list[MeetingMarker]
    transcript: list[str]
    personalization_notes: list[str] = []
    demo_mode: bool = True
