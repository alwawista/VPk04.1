from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_keys: list[str]
    require_api_auth: bool
    database_url: str
    redis_url: str | None
    llm_provider: str
    llm_api_key: str | None
    llm_base_url: str | None
    llm_model: str
    llm_temperature: float
    llm_timeout_seconds: float
    llm_daily_budget_usd: float
    max_request_body_bytes: int
    rate_limit_api_key_per_minute: int
    rate_limit_ip_per_minute: int
    rate_limit_client_per_minute: int
    rate_limit_global_per_minute: int
    spool_path: Path
    environment: str

    @classmethod
    def from_env(cls) -> "Settings":
        redis_url = os.getenv("REDIS_URL") or None
        llm_api_key = os.getenv("LLM_API_KEY") or None
        llm_base_url = os.getenv("LLM_BASE_URL") or None
        return cls(
            api_keys=_split_csv(os.getenv("API_KEYS"), ["demo-key"]),
            require_api_auth=_bool_env("REQUIRE_API_AUTH", False),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/triage.db"),
            redis_url=redis_url,
            llm_provider=os.getenv("LLM_PROVIDER", "mock").lower(),
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_temperature=_float_env("LLM_TEMPERATURE", 0.2),
            llm_timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", 8.0),
            llm_daily_budget_usd=_float_env("LLM_DAILY_BUDGET_USD", 5.0),
            max_request_body_bytes=_int_env("MAX_REQUEST_BODY_BYTES", 8192),
            rate_limit_api_key_per_minute=_int_env("RATE_LIMIT_API_KEY_PER_MINUTE", 60),
            rate_limit_ip_per_minute=_int_env("RATE_LIMIT_IP_PER_MINUTE", 30),
            rate_limit_client_per_minute=_int_env("RATE_LIMIT_CLIENT_PER_MINUTE", 10),
            rate_limit_global_per_minute=_int_env("RATE_LIMIT_GLOBAL_PER_MINUTE", 300),
            spool_path=Path(os.getenv("SPOOL_PATH", "./spool/emergency.jsonl")),
            environment=os.getenv("ENVIRONMENT", "development"),
        )
