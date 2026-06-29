from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import Category, Confidence, TicketIn, TriageResult

OPERATOR_FALLBACK_REPLY = "Ваше обращение передано оператору."
DRAFT_REPLY_MIN_SENTENCES = 1
DRAFT_REPLY_MAX_SENTENCES = 6

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous\s+instructions",
    r"forget\s+(all\s+)?previous\s+instructions",
    r"return\s+json",
    r"confidence\s*[:=]\s*high",
    r"escalate\s*[:=]\s*false",
    r"system\s*prompt",
    r"developer\s+message",
]

UNSAFE_PHRASES = [
    "i checked",
    "we checked",
    "payment confirmed",
    "payment went through",
    "refund has been issued",
    "discount approved",
    "compensation will be credited",
    "100% discount",
    "проверил ваш",
    "возврат оформлен",
    "скидка одобрена",
]

LEGAL_OR_MONEY_PATTERNS = [
    r"\brefund\b",
    r"\bcompensation\b",
    r"\bdiscount\b",
    r"\bchargeback\b",
    r"\bвозврат\b",
    r"\bкомпенсац",
    r"\bскидк",
]

DATE_PATTERN = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")
MONEY_PATTERN = re.compile(
    r"(?:[$]|\brub\.?\b|\busd\b|\beur\b|\bруб\.?\b)\s*\d+|\d+\s*(?:[$]|rub\.?|usd|eur|руб\.?)",
    re.I,
)
ORDER_PATTERN = re.compile(r"(?:order|ticket|number|заказ|номер)\s*#?\s*[A-Za-z0-9-]{4,}", re.I)


def _contains_any(patterns: Iterable[str], text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I) for pattern in patterns)


def detect_prompt_injection(text: str) -> bool:
    return _contains_any(PROMPT_INJECTION_PATTERNS, text)


def operator_fallback(*, error: str | None = None) -> TriageResult:
    return TriageResult(
        category=Category.other,
        draft_reply=OPERATOR_FALLBACK_REPLY,
        confidence=Confidence.low,
        escalate=True,
    )


def prompt_injection_result() -> TriageResult:
    return operator_fallback()


def count_sentences(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    if not re.search(r"[.!?…]", stripped):
        return 1
    parts = re.split(r"[.!?…]+", stripped)
    return len([part.strip() for part in parts if part.strip()])


def is_valid_draft_reply_length(text: str) -> bool:
    count = count_sentences(text)
    return DRAFT_REPLY_MIN_SENTENCES <= count <= DRAFT_REPLY_MAX_SENTENCES


def _new_facts_present(source_text: str, reply: str) -> bool:
    for pattern in (DATE_PATTERN, MONEY_PATTERN, ORDER_PATTERN):
        for match in pattern.findall(reply):
            match_text = match if isinstance(match, str) else " ".join(match)
            if match_text and match_text.lower() not in source_text.lower():
                return True
    return False


def validate_llm_result(ticket: TicketIn, result: TriageResult) -> TriageResult:
    reply = result.draft_reply.lower()

    if not is_valid_draft_reply_length(result.draft_reply):
        return operator_fallback()
    if any(phrase in reply for phrase in UNSAFE_PHRASES):
        return operator_fallback()
    if _contains_any(LEGAL_OR_MONEY_PATTERNS, result.draft_reply) and result.escalate is False:
        return operator_fallback()
    if _new_facts_present(ticket.text, result.draft_reply):
        return operator_fallback()
    if result.confidence == Confidence.low and not result.escalate:
        return result.model_copy(update={"escalate": True})

    return result
