"""Relational model. See docs/DATABASE.md for the rationale behind each index."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import AttemptOutcome, Difficulty, SubmissionMode, SubmissionStatus, TestVerdict, UserRole, Verdict


def pg_enum(enum_cls, name: str):
    # values_callable keeps the DB labels identical to the Python values.
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], create_type=False)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.USER)

    __table_args__ = (
        # Case-insensitive uniqueness without the citext extension.
        Index("uq_users_username_lower", func.lower(text("username")), unique=True),
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
        CheckConstraint("username ~ '^[A-Za-z0-9_]{3,32}$'", name="ck_users_username_format"),
    )


class Language(Base):
    __tablename__ = "languages"

    key: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(48), nullable=False)


class ProblemTag(Base):
    __tablename__ = "problem_tags"

    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (Index("ix_problem_tags_tag_id", "tag_id"),)


class Problem(TimestampMixin, Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(pg_enum(Difficulty, "difficulty"), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    input_spec: Mapped[str] = mapped_column(Text, nullable=False)
    output_spec: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[str] = mapped_column(Text, nullable=False)
    time_limit_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tags: Mapped[list[Tag]] = relationship(secondary="problem_tags", order_by=Tag.name, lazy="selectin")
    test_cases: Mapped[list["TestCase"]] = relationship(
        back_populates="problem", order_by="TestCase.ordinal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("time_limit_ms BETWEEN 100 AND 10000", name="ck_problems_time_limit"),
        CheckConstraint("memory_limit_mb BETWEEN 16 AND 1024", name="ck_problems_memory_limit"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_problems_slug_format"),
        Index("ix_problems_difficulty", "difficulty"),
    )


class TestCase(Base):
    __test__ = False  # not a pytest class
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)

    problem: Mapped[Problem] = relationship(back_populates="test_cases")

    __table_args__ = (
        UniqueConstraint("problem_id", "ordinal", name="uq_test_cases_problem_ordinal"),
        Index("ix_test_cases_problem_sample", "problem_id", "is_sample"),
    )


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[str] = mapped_column(ForeignKey("languages.key"), nullable=False)
    mode: Mapped[SubmissionMode] = mapped_column(pg_enum(SubmissionMode, "submission_mode"), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    custom_input: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[SubmissionStatus] = mapped_column(
        pg_enum(SubmissionStatus, "submission_status"), nullable=False, default=SubmissionStatus.CREATED
    )
    verdict: Mapped[Verdict | None] = mapped_column(pg_enum(Verdict, "verdict"))

    # Lease + fencing token. ``attempt`` increments on every claim; a worker may
    # only write while (worker_id, attempt) still match what it claimed.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    runtime_ms: Mapped[int | None] = mapped_column(Integer)  # max CPU ms over tests
    memory_kb: Mapped[int | None] = mapped_column(Integer)  # max peak RSS over tests
    compile_ms: Mapped[int | None] = mapped_column(Integer)
    tests_passed: Mapped[int | None] = mapped_column(Integer)
    tests_total: Mapped[int | None] = mapped_column(Integer)
    compile_output: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    results: Mapped[list["SubmissionResult"]] = relationship(
        back_populates="submission", order_by="SubmissionResult.ordinal", cascade="all, delete-orphan"
    )
    problem: Mapped[Problem] = relationship()
    user: Mapped[User] = relationship()

    __table_args__ = (
        CheckConstraint("octet_length(source_code) <= 65536", name="ck_submissions_source_size"),
        CheckConstraint("custom_input IS NULL OR octet_length(custom_input) <= 65536", name="ck_submissions_input_size"),
        CheckConstraint("attempt >= 0", name="ck_submissions_attempt_nonneg"),
        CheckConstraint(
            "(status = 'COMPLETED') = (verdict IS NOT NULL)", name="ck_submissions_verdict_iff_completed"
        ),
        # History pages: "my submissions, newest first".
        Index("ix_submissions_user_created", "user_id", text("created_at DESC")),
        # Per-problem acceptance stats and per-user solved status.
        Index("ix_submissions_problem_mode_verdict", "problem_id", "mode", "verdict"),
        Index("ix_submissions_user_problem_verdict", "user_id", "problem_id", "verdict"),
        # Dashboard time series.
        Index("ix_submissions_created_at", "created_at"),
        # Sweeper scans only live rows; partial index stays tiny as history grows.
        Index(
            "ix_submissions_live",
            "status",
            "lease_expires_at",
            postgresql_where=text("status IN ('CREATED','QUEUED','PROCESSING','COMPILING','RUNNING','JUDGING')"),
        ),
        # Idempotent submission creation: one row per (user, client key).
        Index(
            "uq_submissions_user_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class SubmissionResult(Base):
    __tablename__ = "submission_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id", ondelete="SET NULL"))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[TestVerdict] = mapped_column(pg_enum(TestVerdict, "test_verdict"), nullable=False)
    cpu_ms: Mapped[int | None] = mapped_column(Integer)
    wall_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    signal: Mapped[int | None] = mapped_column(Integer)
    # Only populated for RUN mode (samples/custom input). Never for hidden tests.
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)

    submission: Mapped[Submission] = relationship(back_populates="results")

    __table_args__ = (UniqueConstraint("submission_id", "ordinal", name="uq_submission_results_ordinal"),)


class ExecutionAttempt(Base):
    """One row per worker claim. Makes retries and crashes visible after the fact."""

    __tablename__ = "execution_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[AttemptOutcome] = mapped_column(pg_enum(AttemptOutcome, "attempt_outcome"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_wait_ms: Mapped[int | None] = mapped_column(Integer)
    sandbox_start_ms: Mapped[int | None] = mapped_column(Integer)
    compile_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("submission_id", "attempt_no", name="uq_execution_attempts_no"),
        Index("ix_execution_attempts_started", "started_at"),
    )


class SubmissionTransition(Base):
    """Append-only audit log of state machine transitions."""

    __tablename__ = "submission_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[SubmissionStatus | None] = mapped_column(pg_enum(SubmissionStatus, "submission_status"))
    to_status: Mapped[SubmissionStatus] = mapped_column(pg_enum(SubmissionStatus, "submission_status"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_submission_transitions_submission", "submission_id", "id"),)
