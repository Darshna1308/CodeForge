from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from codeforge_core.enums import Difficulty, SubmissionMode, SubmissionStatus, TestVerdict, Verdict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- auth / users
class RegisterIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254, description="Username or email")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str | None = None
    role: str
    created_at: datetime


class AuthOut(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"
    expires_at: int


class SolvedByDifficulty(BaseModel):
    EASY: int = 0
    MEDIUM: int = 0
    HARD: int = 0


class ProfileOut(BaseModel):
    username: str
    joined_at: datetime
    solved: int
    solved_by_difficulty: SolvedByDifficulty
    submissions: int
    accepted_submissions: int
    recent_accepted: list[dict]


# ------------------------------------------------------------------- problems
class TagOut(BaseModel):
    slug: str
    name: str
    count: int | None = None


class ProblemSummary(BaseModel):
    id: int
    slug: str
    title: str
    difficulty: Difficulty
    tags: list[TagOut]
    accepted: int
    submissions: int
    acceptance_rate: float | None
    status: str | None = None  # "solved" | "attempted" | None (per user, never cached)


class Example(BaseModel):
    input: str
    output: str
    explanation: str | None = None


class LanguageOut(BaseModel):
    key: str
    display_name: str
    version: str
    monaco_language: str
    template: str


class ProblemDetail(BaseModel):
    id: int
    slug: str
    title: str
    difficulty: Difficulty
    statement: str
    input_spec: str
    output_spec: str
    constraints: str
    time_limit_ms: int
    memory_limit_mb: int
    tags: list[TagOut]
    examples: list[Example]
    hidden_test_count: int
    accepted: int
    submissions: int
    acceptance_rate: float | None
    languages: list[LanguageOut]
    status: str | None = None


# ---------------------------------------------------------------- submissions
class SubmissionCreate(BaseModel):
    problem_slug: str = Field(min_length=1, max_length=80)
    language: str = Field(min_length=1, max_length=16)
    source_code: str = Field(min_length=1)

    @field_validator("source_code")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source code is empty")
        if "\x00" in v:
            raise ValueError("source code contains NUL bytes")
        return v


class ExecutionCreate(SubmissionCreate):
    custom_input: str | None = Field(default=None, description="Run against this input instead of the sample tests")

    @field_validator("custom_input")
    @classmethod
    def _no_nul(cls, v: str | None) -> str | None:
        if v is not None and "\x00" in v:
            raise ValueError("input contains NUL bytes")
        return v


class TestResultOut(BaseModel):
    ordinal: int
    verdict: TestVerdict
    is_sample: bool
    cpu_ms: int | None
    wall_ms: int | None
    memory_kb: int | None
    exit_code: int | None
    signal: int | None
    # The following are only present when the test data is public.
    input: str | None = None
    expected_output: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class SubmissionOut(BaseModel):
    id: int
    display_id: str
    problem_slug: str
    problem_title: str
    language: str
    mode: SubmissionMode
    status: SubmissionStatus
    verdict: Verdict | None
    runtime_ms: int | None
    memory_kb: int | None
    tests_passed: int | None
    tests_total: int | None
    attempt: int
    created_at: datetime
    finished_at: datetime | None


class AttemptOut(BaseModel):
    attempt_no: int
    worker_id: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None
    queue_wait_ms: int | None
    sandbox_start_ms: int | None
    compile_ms: int | None
    total_ms: int | None
    error: str | None


class TransitionOut(BaseModel):
    from_status: SubmissionStatus | None
    to_status: SubmissionStatus
    attempt: int
    actor: str
    at: datetime


class SubmissionDetail(SubmissionOut):
    source_code: str
    custom_input: str | None
    compile_output: str | None
    compile_ms: int | None
    error_message: str | None
    worker_id: str | None
    queued_at: datetime | None
    started_at: datetime | None
    results: list[TestResultOut]
    attempts: list[AttemptOut]
    transitions: list[TransitionOut]


class SubmissionAccepted(BaseModel):
    id: int
    display_id: str
    status: SubmissionStatus
    mode: SubmissionMode
    events_url: str
    detail_url: str
    idempotent_replay: bool = False
