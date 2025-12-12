from .base import LLMProvider, JSONSchema
from typing import Optional, Any
import os
import json
import logging
from .context import accumulate_usage
from openai import AsyncAzureOpenAI, AzureOpenAI
import tiktoken
import threading
from ...models.token_usage import TokenUsage


class AzureProvider(LLMProvider):
    """
    Azure OpenAI implementation using chat completions endpoint.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        token_limit: int = 190000,
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: API key (auto-detects from env if not provided)
            model: Model name (defaults to gpt-4.1-nano)
            azure_endpoint: Azure endpoint (required, auto-detects from env)
            api_version: Azure API version
            token_limit: Maximum tokens for prompt
        """
        self._api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self._model = model or "gpt-4.1-04-14"
        self._azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self._api_version = api_version or "2024-12-01-preview"

        # Lazy-initialized clients
        self._async_client: Optional[AsyncAzureOpenAI] = None
        self._sync_client: Optional[AzureOpenAI] = None
        self._client_lock = threading.Lock()

        # Configuration
        self._token_limit = token_limit
        self._temperature = 0.1
        self._system_prompt = (
            "You are an assistant to a data analyst. "
            "Your responsibility is to assist in extracting, standardizing, and enriching data. "
            "Be concise and accurate in your responses. "
            "Your responses are fed directly into an SQL environment; "
            "therefore, ensure that your outputs are structured as succinct data points, not as prose.\n"
        )
        self._system_prompt_msg = {"role": "system", "content": self._system_prompt}

        # Pricing (GPT-4.1-nano)
        self._input_token_price: float = 0.0000001  # $0.10/1M tokens
        self._output_token_price: float = 0.000004  # $0.40/1M tokens

    @property
    def async_client(self) -> AsyncAzureOpenAI:
        """Lazy-initialize and return async client."""
        if self._async_client is None:
            with self._client_lock:
                if self._async_client is None:
                    self._async_client = self._create_async_client()
        return self._async_client

    @property
    def sync_client(self) -> AzureOpenAI:
        """Lazy-initialize and return sync client."""
        if self._sync_client is None:
            with self._client_lock:
                if self._sync_client is None:
                    self._sync_client = self._create_sync_client()
        return self._sync_client

    def _create_async_client(self) -> AsyncAzureOpenAI:
        logging.info("Initializing AsyncAzureOpenAI client")
        return AsyncAzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=self._azure_endpoint,
            api_version=self._api_version,
        )

    def _create_sync_client(self) -> AzureOpenAI:
        logging.info("Initializing AzureOpenAI sync client")
        return AzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=self._azure_endpoint,
            api_version=self._api_version,
        )

    async def generate_text_response(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_png_string}"
                        },
                    }
                )

        messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = await self.async_client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
        )
        self._get_token_usage(response)
        return response.choices[0].message.content or ""

    async def generate_structured_response(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_png_string}"
                        },
                    }
                )

        messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = await self.async_client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "schema": output_schema["schema"],
                    "strict": True,
                },
            },
            temperature=self._temperature,
        )
        self._get_token_usage(response)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from Azure OpenAI")
        return json.loads(content)

    def generate_text_response_sync(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_png_string}"
                        },
                    }
                )

        messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = self.sync_client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
        )
        self._get_token_usage(response)
        return response.choices[0].message.content or ""

    def generate_structured_response_sync(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_png_string}"
                        },
                    }
                )

        messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = self.sync_client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "schema": output_schema["schema"],
                    "strict": True,
                },
            },
            temperature=self._temperature,
        )
        self._get_token_usage(response)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from Azure OpenAI")
        return json.loads(content)

    def _encode_as_tokens(self, prompt: str) -> list[int]:
        try:
            return tiktoken.encoding_for_model(self._model).encode(prompt)
        except KeyError:
            return tiktoken.get_encoding("o200k_base").encode(prompt)

    def _decode_from_tokens(self, tokens: list[int]) -> str:
        try:
            return tiktoken.encoding_for_model(self._model).decode(tokens)
        except KeyError:
            return tiktoken.get_encoding("o200k_base").decode(tokens)

    def count_tokens(self, prompt: str) -> int:
        return len(self._encode_as_tokens(prompt))

    def _truncate_to_token_limit_if_necessary(self, prompt: str) -> str:
        if self.count_tokens(prompt) > self._token_limit:
            logging.warning(
                f"User message prompt exceeds {self._token_limit} tokens; truncating. "
                "(System prompt tokens not counted-- truncation may be under true API limit.)"
            )
            return self._decode_from_tokens(
                self._encode_as_tokens(prompt)[: self._token_limit]
            )
        return prompt

    def _get_token_usage(self, response) -> TokenUsage:
        # Chat completions usage format
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        total_tokens = input_tokens + output_tokens
        cost = (input_tokens * self._input_token_price) + (
            output_tokens * self._output_token_price
        )

        print(
            f"input_tokens: {input_tokens:<7} | "
            f"output_tokens: {output_tokens:<7} | "
            f"total_tokens: {total_tokens:<7} | "
            f"cost: {cost:<10.6f}"
        )

        usage_snapshot = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
        )

        accumulate_usage(usage_snapshot)

        return usage_snapshot
