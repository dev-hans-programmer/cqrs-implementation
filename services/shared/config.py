from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    """Operational settings shared by every service.

    Memory mode is the default so unit tests need no external infrastructure. Docker Compose
    explicitly selects PostgreSQL, RabbitMQ, Redis, and OpenTelemetry.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    persistence_backend: str = "memory"
    database_url: str | None = None
    rabbitmq_url: str | None = None
    outbox_poll_seconds: float = Field(default=0.25, gt=0)

    rate_limit_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_capacity: int = Field(default=100, gt=0)
    rate_limit_refill_per_second: float = Field(default=20.0, gt=0)

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"

    @property
    def uses_postgres(self) -> bool:
        return self.persistence_backend.lower() == "postgres"
