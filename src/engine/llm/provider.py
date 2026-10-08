"""LLM providers behind one small interface (M00_SEARCH D-SRCH-6).

`GeminiProvider` uses the google-genai SDK (`models.generate_content`) with a
system instruction, temperature from config and a JSON schema for the reply.
The key is read by the SDK from `GEMINI_API_KEY` (loaded from .env); this code
never reads or logs it. Tests use `FakeProvider` with recorded replies.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

CONFIG = Path(__file__).resolve().parents[3] / "config" / "llm.toml"


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    temperature: float

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.input_usd_per_million
            + Decimal(output_tokens) * self.output_usd_per_million
        ) / Decimal(10**6)


def load_settings(path: Path = CONFIG) -> Settings:
    with path.open("rb") as f:
        c = tomllib.load(f)
    return Settings(
        c["provider"],
        c["model"],
        Decimal(str(c["input_usd_per_million"])),
        Decimal(str(c["output_usd_per_million"])),
        float(c.get("temperature", 0.0)),
    )


def estimate_tokens(text: str) -> int:
    """Rough local estimate (~4 chars per token) for the pre-call cost prompt; no API call."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    thought_tokens: int | None


class Provider(Protocol):
    name: str

    def complete(
        self, model: str, system: str, user: str, schema: dict[str, Any], temperature: float
    ) -> Completion: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        from dotenv import load_dotenv
        from google import genai

        load_dotenv()
        self._client = genai.Client()  # reads GEMINI_API_KEY

    def complete(
        self, model: str, system: str, user: str, schema: dict[str, Any], temperature: float
    ) -> Completion:
        from google.genai import types

        response = self._client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        usage = response.usage_metadata
        return Completion(
            response.text or "",
            usage.prompt_token_count if usage else None,
            usage.candidates_token_count if usage else None,
            usage.thoughts_token_count if usage else None,
        )


class FakeProvider:
    """Returns recorded replies in order; records what it was sent (tests)."""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.sent: list[tuple[str, str, str]] = []

    def complete(
        self, model: str, system: str, user: str, schema: dict[str, Any], temperature: float
    ) -> Completion:
        self.sent.append((model, system, user))
        text = self.replies.pop(0)
        return Completion(text, len(user) // 4, len(text) // 4, 0)
