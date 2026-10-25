"""The PRD-specified GPT-4o-mini adapter; imported only when configured."""
from __future__ import annotations

import json
import os

from .service import RuleProposer


class OpenAIProposer:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required to learn hidden rules")

    async def propose(self, system: str, payload: dict) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install arc-solver-gohook[openai] to run learning") from exc
        client = AsyncOpenAI(api_key=self.api_key)
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
            ],
        )
        return completion.choices[0].message.content or '{"rules":[]}'
