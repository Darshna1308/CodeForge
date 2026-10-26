import enum


class Difficulty(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class SubmissionMode(str, enum.Enum):
    SUBMIT = "SUBMIT"  # judged against hidden tests, counts toward stats
    RUN = "RUN"  # sample tests or custom input, never touches hidden tests


class SubmissionStatus(str, enum.Enum):
    """Lifecycle state. Orthogonal to the verdict (see docs/EXECUTION_ENGINE.md)."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPILING = "COMPILING"
    RUNNING = "RUNNING"
    JUDGING = "JUDGING"
    COMPLETED = "COMPLETED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CANCELLED = "CANCELLED"


class Verdict(str, enum.Enum):
    """Outcome of judging a submission. Only set once status is COMPLETED."""

    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    # RUN mode with custom input has no expected output to compare against.
    EXECUTED = "EXECUTED"


class TestVerdict(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class AttemptOutcome(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"  # infrastructure failure inside the attempt (sandbox start, etc.)
    ABANDONED = "ABANDONED"  # lease expired; worker presumed dead
    LOST_LEASE = "LOST_LEASE"  # worker noticed it was fenced out and stopped


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"
