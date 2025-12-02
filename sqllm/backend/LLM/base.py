from abc import ABC, abstractmethod
from typing import Any, Mapping
from ...models.token_usage import TokenUsage

JSONSchema = Mapping[str, Any]


class LLMProvider(ABC):
    """Abstract base class for LLM providers with both async and sync interfaces."""

    @abstractmethod
    async def generate_text_response(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        """
        Async method to generate a simple text response from the LLM.

        Args:
            prompt: The full prompt including context
            b64_png_strings: Optional list of base64-encoded PNG strings

        Returns:
            str: The text response from the LLM
        """
        ...

    @abstractmethod
    async def generate_structured_response(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Async method to generate a structured response from the LLM using JSON Schema.

        Args:
            prompt: The full prompt including context
            output_schema: JSON schema (Mapping[str, Any]) defining the response structure
            b64_png_strings: Optional list of base64-encoded PNG strings

        Returns:
            dict: Response data that adheres to the specified schema
        """
        ...

    @abstractmethod
    def generate_text_response_sync(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        """
        Sync method to generate a simple text response from the LLM (for UDF functions).

        Args:
            prompt: The full prompt including context
            b64_png_strings: Optional list of base64-encoded PNG strings

        Returns:
            str: The text response from the LLM
        """
        ...

    @abstractmethod
    def generate_structured_response_sync(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Sync method to generate a structured response from the LLM using JSON Schema.

        Args:
            prompt: The full prompt including context
            output_schema: JSON schema (Mapping[str, Any]) defining the response structure
            b64_png_strings: Optional list of base64-encoded PNG strings

        Returns:
            dict: Response data that adheres to the specified schema
        """
        ...

    @abstractmethod
    def count_tokens(self, prompt: str) -> int:
        """
        Count the number of tokens in the prompt.

        Args:
            prompt: The prompt to count tokens for

        Returns:
            int: The number of tokens in the prompt
        """
        ...
