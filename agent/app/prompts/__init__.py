from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@cache
def load_prompt(name: str, version: str) -> str:
    return (_DIR / f"{name}.{version}.txt").read_text(encoding="utf-8")
