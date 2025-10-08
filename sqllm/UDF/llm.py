from __future__ import annotations
import duckdb
from duckdb.typing import VARCHAR
from .base import BaseUDF
from ..LLM.OpenAI import OpenAIProvider


class LLMUDF(BaseUDF):
    name = "llm"

    def __init__(self, provider: OpenAIProvider | None = None):
        self._provider = provider or OpenAIProvider()

    def _evaluate(self, prompt: str) -> str | None:
        full_prompt = (
            "Given the following prompt, produce a concise, text answer to be inserted directly into a table cell. Only include the text of the answer, no other formatting or anyting.\n"
            f"Prompt: {prompt}\n"
        )
        return self._provider.generate_text_response(full_prompt)

    def register(self, conn: duckdb.DuckDBPyConnection) -> None:
        conn.create_function(
            self.name,
            self._evaluate,
            [VARCHAR],
            VARCHAR,
            type="native",
            null_handling="special",
            exception_handling="return_null",
            side_effects=True,
        )
