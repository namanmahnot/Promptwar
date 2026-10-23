"""Pre-filter: cheap, deterministic screening before any LLM call.

Catches obvious destructive requests, prompt-override attempts, requests for personal data
and clearly off-topic asks. It is a first line only; the SQL validator is the real boundary,
so the patterns here favour precision ("price drop" must not be blocked) over recall.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.config import QUESTION_MAX_CHARS, QUESTION_MIN_CHARS

_FLAGS = re.IGNORECASE

_DESTRUCTIVE = re.compile(
    r"\b(drop|truncate|alter|create|replace)\s+(table|view|schema|dataset|database|function|procedure)\b"
    r"|\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+\S+\s+set\b|\bmerge\s+into\b"
    r"|\b(grant|revoke)\s+\S+.*\b(to|from)\b|\bexecute\s+immediate\b|\bexport\s+data\b"
    r"|\b(delete|remove|wipe|erase|destroy)\s+(all|every|the)\s+(data|rows|records|tables?|orders|users)\b",
    _FLAGS,
)

_PROMPT_OVERRIDE = re.compile(
    r"\b(ignore|disregard|forget|override|bypass)\b[^.?!]{0,40}\b(instructions?|rules?|guardrails?|prompts?|restrictions?)\b"
    r"|\bsystem\s+prompt\b|\byour\s+(instructions|prompt|rules)\b"
    r"|\byou\s+are\s+now\b|\bdeveloper\s+mode\b|\bjailbreak\b|\bact\s+as\s+(an?\s+)?(admin|dba|root)\b",
    _FLAGS,
)

_PERSONAL_DATA = re.compile(
    # "Email" alone is also a traffic-source value, so only personal-data phrasings are matched.
    r"\be-?mails\b|\be-?mail\s+(address(es)?|ids?)\b|\b(customer|user|their|his|her)'?s?\s+e-?mail\b"
    r"|\b(street|home|postal|mailing)\s+address(es)?\b|\baddress(es)?\s+of\b"
    r"|\bpostal\s*codes?\b|\bzip\s*codes?\b|\bip\s*address(es)?\b"
    r"|\b(first|last|full|customer|user)\s*names?\b|\bsurnames?\b"
    r"|\b(customer|user)s?'?\s+(latitude|longitude|location|coordinates|addresses)\b"
    r"|\bphone\s*numbers?\b|\bpasswords?\b|\bcredit\s*cards?\b|\bssn\b",
    _FLAGS,
)

_OFF_TOPIC = re.compile(
    r"\b(write|compose|tell)\s+(me\s+)?(an?\s+)?(poem|story|joke|song|essay|haiku|limerick|lyrics)\b"
    r"|\binformation_schema\b|\bbigquery-public-data\.(?!thelook_ecommerce\b)",
    _FLAGS,
)

_RULES = (
    (_DESTRUCTIVE, "UNSAFE_REQUEST", "Requests to change or delete data are not allowed."),
    (_PROMPT_OVERRIDE, "UNSAFE_REQUEST", "Attempts to override the assistant's rules are blocked."),
    (_PERSONAL_DATA, "UNSAFE_REQUEST", "Personal customer data (names, emails, addresses, locations) is restricted."),
    (_OFF_TOPIC, "OUT_OF_SCOPE", "I can only answer questions about the store's data."),
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class PrefilterResult:
    ok: bool
    question: str
    code: str | None = None
    reason: str | None = None


def normalize_question(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = _CONTROL_CHARS.sub(" ", text)
    return " ".join(text.split())


def prefilter(raw_question: str) -> PrefilterResult:
    question = normalize_question(raw_question)

    if not QUESTION_MIN_CHARS <= len(question) <= QUESTION_MAX_CHARS:
        return PrefilterResult(
            False,
            question,
            "VALIDATION_ERROR",
            f"Questions must be {QUESTION_MIN_CHARS}-{QUESTION_MAX_CHARS} characters.",
        )
    for pattern, code, reason in _RULES:
        if pattern.search(question):
            return PrefilterResult(False, question, code, reason)
    return PrefilterResult(True, question)
