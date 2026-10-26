"""Initial schema: users, problems, tests, submissions, results, attempts, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-26

Enum types are created explicitly (once) and referenced with create_type=False,
because submission_status is used by two tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

ENUMS = {
    "difficulty": ("EASY", "MEDIUM", "HARD"),
    "user_role": ("USER", "ADMIN"),
    "submission_mode": ("SUBMIT", "RUN"),
    "submission_status": ("CREATED", "QUEUED", "PROCESSING", "COMPILING", "RUNNING", "JUDGING", "COMPLETED", "INTERNAL_ERROR", "CANCELLED"),
    "verdict": ("ACCEPTED", "WRONG_ANSWER", "COMPILATION_ERROR", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED", "EXECUTED"),
    "test_verdict": ("ACCEPTED", "WRONG_ANSWER", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED", "EXECUTED", "SKIPPED"),
    "attempt_outcome": ("RUNNING", "SUCCEEDED", "FAILED", "ABANDONED", "LOST_LEASE"),
}


def enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table('languages',
    sa.Column('key', sa.String(length=16), nullable=False),
    sa.Column('display_name', sa.String(length=32), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('problems',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('difficulty', enum('difficulty'), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('input_spec', sa.Text(), nullable=False),
    sa.Column('output_spec', sa.Text(), nullable=False),
    sa.Column('constraints', sa.Text(), nullable=False),
    sa.Column('time_limit_ms', sa.Integer(), nullable=False),
    sa.Column('memory_limit_mb', sa.Integer(), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name='ck_problems_slug_format'),
    sa.CheckConstraint('memory_limit_mb BETWEEN 16 AND 1024', name='ck_problems_memory_limit'),
    sa.CheckConstraint('time_limit_ms BETWEEN 100 AND 10000', name='ck_problems_time_limit'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_problems_difficulty', 'problems', ['difficulty'], unique=False)
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=48), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', enum('user_role'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("username ~ '^[A-Za-z0-9_]{3,32}$'", name='ck_users_username_format'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_index('uq_users_username_lower', 'users', [sa.literal_column('lower(username)')], unique=True)
    op.create_table('problem_tags',
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('problem_id', 'tag_id')
    )
    op.create_index('ix_problem_tags_tag_id', 'problem_tags', ['tag_id'], unique=False)
    op.create_table('submissions',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('mode', enum('submission_mode'), nullable=False),
    sa.Column('source_code', sa.Text(), nullable=False),
    sa.Column('custom_input', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('status', enum('submission_status'), nullable=False),
    sa.Column('verdict', enum('verdict'), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.String(length=64), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('runtime_ms', sa.Integer(), nullable=True),
    sa.Column('memory_kb', sa.Integer(), nullable=True),
    sa.Column('compile_ms', sa.Integer(), nullable=True),
    sa.Column('tests_passed', sa.Integer(), nullable=True),
    sa.Column('tests_total', sa.Integer(), nullable=True),
    sa.Column('compile_output', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'COMPLETED') = (verdict IS NOT NULL)", name='ck_submissions_verdict_iff_completed'),
    sa.CheckConstraint('attempt >= 0', name='ck_submissions_attempt_nonneg'),
    sa.CheckConstraint('custom_input IS NULL OR octet_length(custom_input) <= 65536', name='ck_submissions_input_size'),
    sa.CheckConstraint('octet_length(source_code) <= 65536', name='ck_submissions_source_size'),
    sa.ForeignKeyConstraint(['language'], ['languages.key'], ),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_submissions_created_at', 'submissions', ['created_at'], unique=False)
    op.create_index('ix_submissions_live', 'submissions', ['status', 'lease_expires_at'], unique=False, postgresql_where=sa.text("status IN ('CREATED','QUEUED','PROCESSING','COMPILING','RUNNING','JUDGING')"))
    op.create_index('ix_submissions_problem_mode_verdict', 'submissions', ['problem_id', 'mode', 'verdict'], unique=False)
    op.create_index('ix_submissions_user_created', 'submissions', ['user_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_index('ix_submissions_user_problem_verdict', 'submissions', ['user_id', 'problem_id', 'verdict'], unique=False)
    op.create_index('uq_submissions_user_idempotency', 'submissions', ['user_id', 'idempotency_key'], unique=True, postgresql_where=sa.text('idempotency_key IS NOT NULL'))
    op.create_table('test_cases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('is_sample', sa.Boolean(), nullable=False),
    sa.Column('input', sa.Text(), nullable=False),
    sa.Column('expected_output', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('problem_id', 'ordinal', name='uq_test_cases_problem_ordinal')
    )
    op.create_index('ix_test_cases_problem_sample', 'test_cases', ['problem_id', 'is_sample'], unique=False)
    op.create_table('execution_attempts',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('submission_id', sa.BigInteger(), nullable=False),
    sa.Column('attempt_no', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.String(length=64), nullable=False),
    sa.Column('outcome', enum('attempt_outcome'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('queue_wait_ms', sa.Integer(), nullable=True),
    sa.Column('sandbox_start_ms', sa.Integer(), nullable=True),
    sa.Column('compile_ms', sa.Integer(), nullable=True),
    sa.Column('total_ms', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submission_id', 'attempt_no', name='uq_execution_attempts_no')
    )
    op.create_index('ix_execution_attempts_started', 'execution_attempts', ['started_at'], unique=False)
    op.create_table('submission_results',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('submission_id', sa.BigInteger(), nullable=False),
    sa.Column('test_case_id', sa.Integer(), nullable=True),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('verdict', enum('test_verdict'), nullable=False),
    sa.Column('cpu_ms', sa.Integer(), nullable=True),
    sa.Column('wall_ms', sa.Integer(), nullable=True),
    sa.Column('memory_kb', sa.Integer(), nullable=True),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('signal', sa.Integer(), nullable=True),
    sa.Column('stdout', sa.Text(), nullable=True),
    sa.Column('stderr', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['test_case_id'], ['test_cases.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submission_id', 'ordinal', name='uq_submission_results_ordinal')
    )
    op.create_table('submission_transitions',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('submission_id', sa.BigInteger(), nullable=False),
    sa.Column('from_status', enum('submission_status'), nullable=True),
    sa.Column('to_status', enum('submission_status'), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('actor', sa.String(length=64), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_submission_transitions_submission', 'submission_transitions', ['submission_id', 'id'], unique=False)

    # Reference data: languages must exist before any submission can reference them.
    languages = sa.table('languages', sa.column('key'), sa.column('display_name'), sa.column('version'), sa.column('enabled'))
    op.bulk_insert(languages, [
        {'key': 'python', 'display_name': 'Python', 'version': '3.12', 'enabled': True},
        {'key': 'cpp', 'display_name': 'C++17', 'version': 'GCC 14', 'enabled': True},
    ])


def downgrade() -> None:
    op.drop_index('ix_submission_transitions_submission', table_name='submission_transitions')
    op.drop_table('submission_transitions')
    op.drop_table('submission_results')
    op.drop_index('ix_execution_attempts_started', table_name='execution_attempts')
    op.drop_table('execution_attempts')
    op.drop_index('ix_test_cases_problem_sample', table_name='test_cases')
    op.drop_table('test_cases')
    op.drop_index('uq_submissions_user_idempotency', table_name='submissions', postgresql_where=sa.text('idempotency_key IS NOT NULL'))
    op.drop_index('ix_submissions_user_problem_verdict', table_name='submissions')
    op.drop_index('ix_submissions_user_created', table_name='submissions')
    op.drop_index('ix_submissions_problem_mode_verdict', table_name='submissions')
    op.drop_index('ix_submissions_live', table_name='submissions', postgresql_where=sa.text("status IN ('CREATED','QUEUED','PROCESSING','COMPILING','RUNNING','JUDGING')"))
    op.drop_index('ix_submissions_created_at', table_name='submissions')
    op.drop_table('submissions')
    op.drop_index('ix_problem_tags_tag_id', table_name='problem_tags')
    op.drop_table('problem_tags')
    op.drop_index('uq_users_username_lower', table_name='users')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('tags')
    op.drop_index('ix_problems_difficulty', table_name='problems')
    op.drop_table('problems')
    op.drop_table('languages')
    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
