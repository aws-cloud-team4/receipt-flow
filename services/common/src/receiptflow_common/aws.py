from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from .config import get_settings


@lru_cache
def session() -> boto3.Session:
    s = get_settings()
    return boto3.Session(profile_name=s.aws_profile, region_name=s.region)


@lru_cache
def client(name: str) -> Any:
    extra: dict[str, Any] = {}
    if name == "s3":
        extra["config"] = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
    elif name == "budgets":
        extra["region_name"] = "us-east-1"  # AWS Budgets is a global service answered in us-east-1
    elif name == "bedrock-runtime":
        extra["config"] = Config(read_timeout=60, retries={"max_attempts": 3, "mode": "adaptive"})
    return session().client(name, **extra)


@lru_cache
def table() -> Any:
    return session().resource("dynamodb").Table(get_settings().table)


def reset() -> None:
    """Drop cached clients (tests switch settings and moto contexts)."""
    session.cache_clear()
    client.cache_clear()
    table.cache_clear()
    get_settings.cache_clear()
