from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.config import Settings
from app.models import Category, Confidence, TicketIn, TriageResult


class LLMUnavailable(Exception):
    pass


class InvalidLLMOutput(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_seconds: int = 30) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            self.failures = 0
            self.opened_at = None
            return
        raise LLMUnavailable("LLM circuit breaker is open")

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider
        self.breaker = CircuitBreaker()
        self._spent_usd = 0.0

    async def classify(self, ticket: TicketIn) -> TriageResult:
        self.breaker.before_call()
        if self._spent_usd >= self.settings.llm_daily_budget_usd:
            raise LLMUnavailable("LLM daily budget exhausted")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = await asyncio.wait_for(
                    self._classify_once(ticket),
                    timeout=self.settings.llm_timeout_seconds,
                )
                self._spent_usd += 0.001
                self.breaker.record_success()
                return result
            except Exception as exc:
                last_error = exc
                self.breaker.record_failure()
                if attempt < 2:
                    await asyncio.sleep(0.1 * (attempt + 1))
        raise LLMUnavailable(str(last_error) if last_error else "LLM call failed")

    async def _classify_once(self, ticket: TicketIn) -> TriageResult:
        if self.provider == "mock":
            return await self._mock_classify(ticket)
        if self.provider == "openai":
            return await self._openai_classify(ticket)
        if self.provider == "anthropic":
            return await self._anthropic_classify(ticket)
        raise LLMUnavailable(f"Unsupported LLM_PROVIDER: {self.provider}")

    async def _mock_classify(self, ticket: TicketIn) -> TriageResult:
        text = ticket.text.lower()
        if "mock_timeout" in text:
            await asyncio.sleep(self.settings.llm_timeout_seconds + 1)
        if "mock_invalid_json" in text:
            raise InvalidLLMOutput("Mock invalid JSON")
        if "mock_unsafe" in text:
            return TriageResult(
                category=Category.billing,
                draft_reply="Проверил ваш платёж от 15.03, скидка одобрена.",
                confidence=Confidence.high,
                escalate=False,
            )
        if any(word in text for word in ["payment", "billing", "invoice", "charge", "оплат", "счёт"]):
            return TriageResult(
                category=Category.billing,
                draft_reply=(
                    "Спасибо за обращение. Уточните, пожалуйста, номер заказа или платёжный "
                    "идентификатор — так мы быстрее проверим ситуацию."
                ),
                confidence=Confidence.low,
                escalate=True,
            )
        if any(word in text for word in ["not working", "error", "bug", "broken", "не работает", "ошибк"]):
            return TriageResult(
                category=Category.support,
                draft_reply=(
                    "Спасибо за обращение. Опишите, пожалуйста, что именно не работает, "
                    "и приложите текст ошибки или скриншот."
                ),
                confidence=Confidence.medium,
                escalate=False,
            )
        if any(word in text for word in ["complaint", "жалоб", "недовол", "ужасн"]):
            return TriageResult(
                category=Category.complaint,
                draft_reply=(
                    "Спасибо, что написали. Мы понимаем ваше беспокойство и передадим обращение "
                    "ответственному специалисту для разбора."
                ),
                confidence=Confidence.medium,
                escalate=True,
            )
        return TriageResult(
            category=Category.other,
            draft_reply="Спасибо за обращение. Пожалуйста, уточните детали, чтобы мы могли помочь.",
            confidence=Confidence.low,
            escalate=True,
        )

    def _openai_client_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "api_key": self.settings.llm_api_key,
            "timeout": self.settings.llm_timeout_seconds,
        }
        if self.settings.llm_base_url:
            kwargs["base_url"] = self.settings.llm_base_url
        return kwargs

    def _anthropic_client_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "api_key": self.settings.llm_api_key,
            "timeout": self.settings.llm_timeout_seconds,
        }
        if self.settings.llm_base_url:
            kwargs["base_url"] = self.settings.llm_base_url
        return kwargs

    async def _openai_classify(self, ticket: TicketIn) -> TriageResult:
        if not self.settings.llm_api_key:
            raise LLMUnavailable("LLM_API_KEY is required for OpenAI")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(**self._openai_client_kwargs())
        response = await client.chat.completions.create(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            response_format={"type": "json_object"},
            messages=self._messages(ticket),
        )
        content = response.choices[0].message.content or "{}"
        return self._parse_json_result(content)

    async def _anthropic_classify(self, ticket: TicketIn) -> TriageResult:
        if not self.settings.llm_api_key:
            raise LLMUnavailable("LLM_API_KEY is required for Anthropic")
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(**self._anthropic_client_kwargs())
        response = await client.messages.create(
            model=self.settings.llm_model,
            max_tokens=800,
            temperature=self.settings.llm_temperature,
            system=self._system_prompt(),
            messages=[{"role": "user", "content": self._user_prompt(ticket)}],
        )
        content = "".join(block.text for block in response.content if hasattr(block, "text"))
        return self._parse_json_result(content)

    def _messages(self, ticket: TicketIn) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": self._user_prompt(ticket)},
        ]

    def _system_prompt(self) -> str:
        return (
            "Ты — ассистент службы поддержки. Твоя задача: классифицировать обращение "
            "и написать черновик ответа.\n"
            "Правила:\n"
            "- отвечай строго по входному тексту, не выдумывай факты;\n"
            "- если данных мало → confidence=low и escalate=true;\n"
            "- draft_reply: 1–6 предложений, вежливый тон;\n"
            "- category: billing | support | complaint | other;\n"
            "- confidence: high | medium | low;\n"
            "- escalate: true — передать оператору, false — можно отдать черновик без эскалации.\n"
            "Верни только JSON с ключами: category, draft_reply, confidence, escalate."
        )

    def _user_prompt(self, ticket: TicketIn) -> str:
        return (
            f"client_id={ticket.client_id}\n"
            f"channel={ticket.channel.value}\n"
            f"ticket_text:\n{ticket.text}"
        )

    def _parse_json_result(self, content: str) -> TriageResult:
        try:
            payload: dict[str, Any] = json.loads(content)
            return TriageResult(**payload)
        except Exception as exc:
            raise InvalidLLMOutput(str(exc)) from exc
