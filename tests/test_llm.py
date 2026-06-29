from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.llm import LLMClient
from app.models import Channel, TicketIn


def _settings(**overrides: object) -> Settings:
    defaults = {
        "api_keys": ["demo-key"],
        "require_api_auth": False,
        "database_url": "sqlite:///./data/triage.db",
        "redis_url": None,
        "llm_provider": "openai",
        "llm_api_key": "proxy-test-key",
        "llm_base_url": None,
        "llm_model": "gpt-4o-mini",
        "llm_temperature": 0.2,
        "llm_timeout_seconds": 8.0,
        "llm_daily_budget_usd": 5.0,
        "max_request_body_bytes": 8192,
        "rate_limit_api_key_per_minute": 60,
        "rate_limit_ip_per_minute": 30,
        "rate_limit_client_per_minute": 10,
        "rate_limit_global_per_minute": 300,
        "spool_path": Path("./spool/emergency.jsonl"),
        "environment": "test",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _ticket() -> TicketIn:
    return TicketIn(text="Форма не работает", channel=Channel.form, client_id="client-1")


def _mock_openai_response() -> MagicMock:
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"category":"support","draft_reply":"Спасибо за обращение.",'
                    '"confidence":"medium","escalate":false}'
                )
            )
        )
    ]
    return response


@pytest.mark.asyncio
async def test_openai_client_uses_configured_base_url():
    settings = _settings(
        llm_base_url="https://openai.api.proxyapi.ru/v1",
        llm_model="openai/gpt-4o-mini",
    )
    client = LLMClient(settings)

    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(return_value=_mock_openai_response())
        mock_openai.return_value = mock_instance

        result = await client.classify(_ticket())

    mock_openai.assert_called_once_with(
        api_key="proxy-test-key",
        timeout=8.0,
        base_url="https://openai.api.proxyapi.ru/v1",
    )
    assert result.category.value == "support"


@pytest.mark.asyncio
async def test_openai_client_omits_base_url_when_not_configured():
    settings = _settings()
    client = LLMClient(settings)

    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(return_value=_mock_openai_response())
        mock_openai.return_value = mock_instance

        await client.classify(_ticket())

    mock_openai.assert_called_once_with(api_key="proxy-test-key", timeout=8.0)


@pytest.mark.asyncio
async def test_anthropic_client_uses_configured_base_url():
    settings = _settings(
        llm_provider="anthropic",
        llm_base_url="https://api.proxyapi.ru/anthropic",
        llm_model="claude-sonnet-4-20250514",
    )
    client = LLMClient(settings)

    response = MagicMock()
    response.content = [MagicMock(text='{"category":"other","draft_reply":"Спасибо.","confidence":"low","escalate":true}')]

    with patch("anthropic.AsyncAnthropic") as mock_anthropic:
        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(return_value=response)
        mock_anthropic.return_value = mock_instance

        await client.classify(_ticket())

    mock_anthropic.assert_called_once_with(
        api_key="proxy-test-key",
        timeout=8.0,
        base_url="https://api.proxyapi.ru/anthropic",
    )
