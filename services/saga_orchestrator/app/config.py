from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    order_service_url: str = Field(default="http://localhost:8001")
    inventory_service_url: str = Field(default="http://localhost:8002")
    payment_service_url: str = Field(default="http://localhost:8003")
    downstream_timeout_seconds: float = Field(default=5.0, gt=0)
