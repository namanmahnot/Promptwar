from pydantic import BaseModel, Field

from app.config import QUESTION_MAX_CHARS, QUESTION_MIN_CHARS


class AskRequest(BaseModel):
    model_config = {"extra": "forbid"}

    question: str = Field(min_length=QUESTION_MIN_CHARS, max_length=QUESTION_MAX_CHARS)
    uid: str = Field(min_length=1, max_length=128)
    requestId: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")  # noqa: N815 — API contract
