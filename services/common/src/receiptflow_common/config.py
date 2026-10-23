import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every service reads the same RF_* environment variables (see services/.env.example)."""

    model_config = SettingsConfigDict(
        env_prefix="RF_", env_file=os.environ.get("RF_ENV_FILE", ".env"), extra="ignore"
    )

    region: str = "ap-northeast-2"
    # Local runs only; in EKS credentials come from Pod Identity.
    aws_profile: str | None = Field(default=None, validation_alias="AWS_PROFILE")
    table: str = "receipt-flow-dev"
    bucket: str = ""
    queue_url: str = ""

    auth_mode: Literal["cognito", "dev"] = "cognito"
    # Local only: also accept dev tokens next to Cognito (the hidden developer login). Never in deploy.
    dev_login: bool = False
    cognito_pool_id: str = ""
    cognito_client_id: str = ""

    ai_mode: Literal["bedrock", "mock"] = "bedrock"
    # Receipt images need the stronger reader; chat answers are short text (docs/model-eval.md).
    extract_model: str = "global.anthropic.claude-sonnet-5-5"
    chat_model: str = "global.anthropic.claude-haiku-5-5"

    cors_origins: str = "http://localhost:5173"
    upload_url_ttl: int = 600
    image_url_ttl: int = 300

    # landing-page usage card: which AWS Budgets budget, and what to call the team
    usage_budget: str = "aws-team4-receipt-flow"
    usage_label: str = "AWS 클라우드 4조"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
