"""Number grounding: every number in the insight text must trace to a computed fact.

Numbers are normalised (commas, %, currency, k/million/billion) and compared at the
precision they are written, so "$1.2 million" matches a fact of 1,234,567.89.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])[-−]?\$?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?:\s?(?P<scale>thousand|million|billion|k|m|bn|b)\b)?(?P<pct>\s?%|\s?percent\b)?",
    re.IGNORECASE,
)
_SCALES = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}


def extract_numbers(text: str) -> list[tuple[str, float, float, bool]]:
    """Return (written, value, tolerance, is_percent) for each number in ``text``."""
    found = []
    for match in _NUMBER.finditer(text):
        end = match.end()
        if end < len(text) and text[end].isalpha() and not match.group("scale") and not match.group("pct"):
            continue  # ordinals and codes such as "2nd" or "3D" are not quantities
        frac = match.group("frac") or ""
        scale = _SCALES.get((match.group("scale") or "").lower(), 1.0)
        value = float(f"{match.group('int').replace(',', '')}.{frac or '0'}") * scale
        tolerance = 0.5 * 10 ** -len(frac) * scale + 1e-9
        found.append((match.group(0).strip(), value, tolerance, bool(match.group("pct"))))
    return found


def allowed_numbers(facts: list[dict], question: str) -> list[float]:
    allowed: list[float] = []
    for fact in facts:
        value = fact.get("value")
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            allowed.append(abs(float(value)))
        elif value is not None:
            allowed.extend(n for _, n, _, _ in extract_numbers(str(value)))
        allowed.extend(n for _, n, _, _ in extract_numbers(str(fact.get("label", ""))))
    allowed.extend(n for _, n, _, _ in extract_numbers(question))
    return allowed


def ungrounded_numbers(text: str, facts: list[dict], question: str) -> list[str]:
    allowed = allowed_numbers(facts, question)
    bad = []
    for written, value, tolerance, is_percent in extract_numbers(text):
        candidates = allowed + ([a * 100 for a in allowed] if is_percent else [])
        if not any(abs(value - c) <= tolerance for c in candidates):
            bad.append(written)
    return bad


def format_value(value) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def template_insight(facts: list[dict]) -> str:
    """Fallback sentence built only from facts, grounded by construction."""
    rows = next((f["value"] for f in facts if f["label"] == "Rows returned"), 0)
    if not rows:
        return "The query ran successfully but returned no matching data."
    details = [f"{f['label']}: {format_value(f['value'])}" for f in facts if f["label"] != "Rows returned"]
    if not details:
        return f"The query returned {format_value(rows)} rows."
    return "Key results: " + "; ".join(details[:4]) + "."
