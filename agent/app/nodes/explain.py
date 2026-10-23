"""explain: Flash-Lite writes the narrative; the grounding checker decides whether it is shown."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.grounding import format_value, template_insight, ungrounded_numbers
from app.llm import Llm, LlmResult, LlmUnavailable
from app.prompts import load_prompt

MAX_INSIGHT_CHARS = 600


@dataclass
class ExplainOutcome:
    insight: str
    source: str  # "model" | "model_retry" | "template"
    calls: list[LlmResult] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def build_prompt(question: str, facts: list[dict], version: str, rejected: list[str] | None = None) -> str:
    feedback = ""
    if rejected:
        feedback = f"\nYour previous answer used numbers not in FACTS ({', '.join(rejected)}). Remove them.\n"
    fact_lines = "\n".join(f"- {f['label']}: {format_value(f['value'])}" for f in facts)
    return load_prompt("explain", version).format(feedback_block=feedback, question=question, facts=fact_lines)


def explain(llm: Llm, model: str, question: str, facts: list[dict], version: str) -> ExplainOutcome:
    outcome = ExplainOutcome(insight="", source="template")
    rejected: list[str] = []
    for attempt in range(2):  # first try + one regenerate
        try:
            result = llm.generate(build_prompt(question, facts, version, rejected), model=model)
        except LlmUnavailable:
            break
        outcome.calls.append(result)
        text = " ".join(result.text.split())[:MAX_INSIGHT_CHARS]
        rejected = ungrounded_numbers(text, facts, question)
        if text and not rejected:
            outcome.insight = text
            outcome.source = "model" if attempt == 0 else "model_retry"
            return outcome
        outcome.rejected.extend(rejected)

    outcome.insight = template_insight(facts)
    return outcome
