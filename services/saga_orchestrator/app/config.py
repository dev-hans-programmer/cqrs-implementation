from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    order_service_url: str = Field(default="http://localhost:8001")
    inventory_service_url: str = Field(default="http://localhost:8002")
    payment_service_url: str = Field(default="http://localhost:8003")
    downstream_timeout_seconds: float = Field(default=5.0, gt=0)
    downstream_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=0.1, gt=0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_seconds: float = Field(default=15.0, gt=0)
    saga_recovery_poll_seconds: float = Field(default=5.0, gt=0)
    saga_stale_after_seconds: float = Field(default=10.0, gt=0)
