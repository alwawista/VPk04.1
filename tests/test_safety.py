from __future__ import annotations

from app.models import Category, Confidence, TicketIn, TriageResult
from app.safety import (
    OPERATOR_FALLBACK_REPLY,
    count_sentences,
    is_valid_draft_reply_length,
    validate_llm_result,
)


def _ticket() -> TicketIn:
    return TicketIn(text="test", channel="form", client_id="client-1")


def _result(draft_reply: str, **kwargs) -> TriageResult:
    return TriageResult(
        category=Category.support,
        draft_reply=draft_reply,
        confidence=Confidence.medium,
        escalate=False,
        **kwargs,
    )


def test_count_sentences_handles_common_cases():
    assert count_sentences("") == 0
    assert count_sentences("   ") == 0
    assert count_sentences("Одно предложение") == 1
    assert count_sentences("Первое. Второе.") == 2
    assert count_sentences("Первое! Второе? Третье…") == 3


def test_is_valid_draft_reply_length_accepts_one_to_six_sentences():
    assert is_valid_draft_reply_length("Одно.")
    assert is_valid_draft_reply_length("1. 2. 3. 4. 5. 6.")


def test_is_valid_draft_reply_length_rejects_invalid_counts():
    assert not is_valid_draft_reply_length("")
    assert not is_valid_draft_reply_length("1. 2. 3. 4. 5. 6. 7.")


def test_validate_llm_result_rejects_too_many_sentences():
    reply = " ".join(f"Предложение {index}." for index in range(1, 8))
    validated = validate_llm_result(_ticket(), _result(reply))

    assert validated.escalate is True
    assert validated.draft_reply == OPERATOR_FALLBACK_REPLY


def test_validate_llm_result_accepts_valid_reply():
    reply = "Спасибо за обращение. Мы уже смотрим ситуацию."
    validated = validate_llm_result(_ticket(), _result(reply))

    assert validated.draft_reply == reply
    assert validated.escalate is False
