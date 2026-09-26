from pydantic import BaseModel, Field


class MeetingMarker(BaseModel):
    label: str = "录音豆重点"
    time: str = Field(..., examples=["14:32"])
    note: str | None = None
    source: str = "recording_bean"


class MeetingTask(BaseModel):
    task: str
    assignee: str
    deadline: str
    source: str
    evidence: str
    status: str = "待确认"
    confidence: float = Field(default=0.88, ge=0, le=1)
    self_committed: bool = False


class MeetingInsight(BaseModel):
    title: str
    source: str = "交流内容"
    evidence: str


class MeetingFocusSource(BaseModel):
    source: str
    evidence: str
    reason: str = ""


class MeetingMarkerInsight(BaseModel):
    marker_time: str
    window_start: str
    window_end: str
    summary: str
    personal_action: str = ""
    deadline: str = "待确认"
    conditions: list[str] = []
    risks: list[str] = []
    evidence: list[MeetingFocusSource] = []
    saved: bool = False


class MeetingFocusAnalysis(BaseModel):
    marker_insights: list[MeetingMarkerInsight] = []
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
    marker_insights: list[MeetingMarkerInsight] = []
    transcript: list[str]
    personalization_notes: list[str] = []
    demo_mode: bool = True
    identity_confirmed: bool = True
