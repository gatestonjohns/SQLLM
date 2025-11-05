from .base import LLMProvider, JSONSchema
from typing import Optional, Any
import os
import json
import logging
from openai import AzureOpenAI, OpenAI
import tiktoken
import rxconfig


class OpenAIProvider(LLMProvider):
    """OpenAI implementation of LLM provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4.1-nano-04-14" if rxconfig.isProd() else "gpt-4.1-2025-04-14",
        token_limit: int = 190000,
        azure_endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: Azure OpenAI API key (defaults to AZURE_OPENAI_API_KEY env var)
            model: Model deployment name in Azure
            azure_endpoint: Azure OpenAI endpoint (defaults to AZURE_OPENAI_ENDPOINT env var)
            api_version: Azure API version
        """
        self._api_key = api_key or (
            os.getenv("AZURE_OPENAI_API_KEY")
            if rxconfig.isProd()
            else os.getenv("OPENAI_API_KEY")
        )
        self._azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self._api_version = api_version
        self._model = model
        self._client = self._get_client()
        self._token_limit = token_limit
        self._temperature = 0.3
        self._system_prompt = (
            "You are an assistant to a data analyst. "
            "Your responsibility is to assist in standardizing, enriching, and improving data. "
            "Be concise and accurate in your responses. "
            "Your responses are fed directly into an SQL environment; "
            "therefore, ensure that your outputs are structured as succinct data points, not as prose.\n"
        )
        self._system_prompt_msg = {"role": "system", "content": self._system_prompt}

        # Token counting and cost tracking
        self._cumulative_input_tokens: int = 0
        self._cumulative_output_tokens: int = 0
        self._cumulative_cost: float = 0.0
        self._query_count: int = 0
        self._current_query_input_tokens: int = 0
        self._current_query_output_tokens: int = 0
        self._current_query_cost: float = 0.0
        self._input_token_price: float = (
            0.0000001  # GPT-4.1-nano input pricing ($0.10/1M tokens)
        )
        self._output_token_price: float = (
            0.000004  # GPT-4.1-nano output pricing ($0.40/1M tokens)
        )

    def _get_client(self) -> AzureOpenAI | OpenAI:
        if rxconfig.isProd():
            return AzureOpenAI(
                api_key=self._api_key,
                azure_endpoint=self._azure_endpoint,
                api_version=self._api_version,
            )
        else:
            return OpenAI(
                api_key=self._api_key,
            )

    def _update_usage_stats(self, response):
        """Update token usage and cost statistics from API response."""
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        call_cost = (input_tokens * self._input_token_price) + (
            output_tokens * self._output_token_price
        )

        # Update cumulative stats
        self._cumulative_input_tokens += input_tokens
        self._cumulative_output_tokens += output_tokens
        self._cumulative_cost += call_cost

        # Update current query stats
        self._current_query_input_tokens += input_tokens
        self._current_query_output_tokens += output_tokens
        self._current_query_cost += call_cost

        logging.info(
            f"LLM call: {input_tokens} in, {output_tokens} out, ${call_cost:.6f}"
        )

    def generate_text_response(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    self._system_prompt_msg,
                    {
                        "role": "user",
                        "content": self._truncate_to_token_limit_if_necessary(prompt),
                    },
                ],
                temperature=self._temperature,
            )
            self._update_usage_stats(response)
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error generating text response: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def generate_structured_response(
        self, prompt: str, output_schema: JSONSchema
    ) -> dict[str, Any]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    self._system_prompt_msg,
                    {
                        "role": "user",
                        "content": self._truncate_to_token_limit_if_necessary(prompt),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": output_schema,
                },
                temperature=self._temperature,
            )
            self._update_usage_stats(response)
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logging.error(f"Error generating structured response: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def _encode_as_tokens(self, prompt: str) -> list[int]:
        return tiktoken.encoding_for_model(self._model).encode(prompt)

    def _decode_from_tokens(self, tokens: list[int]) -> str:
        return tiktoken.encoding_for_model(self._model).decode(tokens)

    def count_tokens(self, prompt: str) -> int:
        return len(self._encode_as_tokens(prompt))

    def _truncate_to_token_limit_if_necessary(self, prompt: str) -> str:
        if self.count_tokens(prompt) > self._token_limit:
            logging.warning(
                f"User message prompt exceeds {self._token_limit} tokens; truncating. (System prompt tokens not counted-- truncation may be under true API limit.)"
            )
            return self._decode_from_tokens(
                self._encode_as_tokens(prompt)[: self._token_limit]
            )

        return prompt

    def get_session_stats(self) -> dict[str, Any]:
        """Get cumulative session statistics."""
        return {
            "total_input_tokens": self._cumulative_input_tokens,
            "total_output_tokens": self._cumulative_output_tokens,
            "total_tokens": self._cumulative_input_tokens
            + self._cumulative_output_tokens,
            "total_cost": round(self._cumulative_cost, 6),
            "query_count": self._query_count,
        }

    def get_current_query_stats(self) -> dict[str, Any]:
        """Get accumulated statistics for the current query."""
        return {
            "input_tokens": self._current_query_input_tokens,
            "output_tokens": self._current_query_output_tokens,
            "total_tokens": self._current_query_input_tokens
            + self._current_query_output_tokens,
            "cost": round(self._current_query_cost, 6),
        }

    def reset_current_query_stats(self) -> None:
        """Reset per-query statistics at the start of a new query."""
        self._current_query_input_tokens = 0
        self._current_query_output_tokens = 0
        self._current_query_cost = 0.0
        self._query_count += 1
