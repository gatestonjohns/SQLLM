from abc import ABC, abstractmethod
from typing import Any, Mapping

JSONSchema = Mapping[str, Any]


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_text_response(self, prompt: str) -> str:
        """
        Generate a simple text response from the LLM.

        Args:
            prompt: The full prompt including context

        Returns:
            str: The text response from the LLM
        """
        ...

    @abstractmethod
    def generate_structured_response(
        self, prompt: str, output_schema: JSONSchema
    ) -> dict[str, Any]:
        """
        Generate a structured response from the LLM using JSON Schema.

        Args:
            prompt: The full prompt including context
            output_schema: JSON schema (Mapping[str, Any]) defining the response structure

        Returns:
            dict: Response data that adheres to the specified schema
        """
        ...

    @abstractmethod
    def count_tokens(self, prompt: str) -> int:
        """
        Count the number of tokens in the prompt.
        """
        ...

    @abstractmethod
    def get_session_stats(self) -> dict[str, Any]:
        """
        Get cumulative session statistics including total input tokens, total output tokens,
        total cost, and number of queries executed.

        Returns:
            dict: Dictionary containing 'total_input_tokens', 'total_output_tokens',
                  'total_tokens', 'total_cost', and 'query_count'.
        """
        ...

    @abstractmethod
    def get_current_query_stats(self) -> dict[str, Any]:
        """
        Get accumulated statistics for the current query (which may include multiple LLM calls).

        Returns:
            dict: Dictionary containing 'input_tokens', 'output_tokens', 'total_tokens', and 'cost'.
        """
        ...

    @abstractmethod
    def reset_current_query_stats(self) -> None:
        """
        Reset the per-query statistics accumulator at the start of a new query execution.
        """
        ...
