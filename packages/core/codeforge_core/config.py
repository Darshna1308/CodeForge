from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://codeforge:codeforge@localhost:5432/codeforge"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = Field(default="dev-only-insecure-secret-change-me", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 720
    auth_cookie_name: str = "cf_session"
    auth_cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"

    # Rate limits: "capacity/refill_seconds" token buckets
    rate_limit_submit: str = "10/60"
    rate_limit_run: str = "20/60"
    rate_limit_auth: str = "10/60"
    rate_limit_enabled: bool = True

    # Cache
    cache_ttl_problem_list: int = 120
    cache_ttl_problem: int = 300
    cache_ttl_stats: int = 10

    # Submission input limits
    max_source_bytes: int = 64 * 1024
    max_custom_input_bytes: int = 64 * 1024

    # Queue / worker
    lease_seconds: int = 90
    max_attempts: int = 3
    visibility_timeout_seconds: int = 180
    max_deliveries: int = 5
    worker_concurrency: int = 2
    worker_id: str | None = None
    worker_metrics_port: int = 9100
    sweeper_interval_seconds: float = 5.0
    created_grace_seconds: int = 10
    queued_stale_seconds: int = 600

    # Sandbox
    sandbox_image: str = "codeforge-sandbox:latest"
    sandbox_docker_binary: str = "docker"
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 64
    sandbox_tmpfs_mb: int = 64
    sandbox_container_memory_floor_mb: int = 512
    sandbox_stdout_limit_bytes: int = 1024 * 1024
    sandbox_stderr_limit_bytes: int = 8 * 1024
    sandbox_compile_timeout_s: float = 15.0
    sandbox_job_timeout_s: float = 150.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
