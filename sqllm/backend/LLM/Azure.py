from .base import LLMProvider, JSONSchema
from typing import Optional, Any
import os
import json
import logging
from .context import accumulate_usage
from openai import AsyncAzureOpenAI, AzureOpenAI
from openai.types.responses import Response
import tiktoken
import threading
from ...models.token_usage import TokenUsage

class AzureProvider(LLMProvider):
    """
    Azure OpenAI implementation using responses endpoint.
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        azure_endpoint: str = None,
        api_version: str = None,
        token_limit: int = None,
        input_token_price: float = None,
        output_token_price: float = None,
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: API key (auto-detects from env if not provided)
            model: Model name (auto-selects based on environment if not provided)
            azure_endpoint: Azure endpoint (auto-detects from env if not provided)
            api_version: Azure API version (auto-detects from env if not provided)
            token_limit: Maximum tokens for context window
            input_token_price: Input token price for single token
            output_token_price: Output token price for single token
        """
        self._api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self._model = model or os.getenv("AZURE_OPENAI_MODEL_DEPLOYMENT_NAME")
        self._azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self._api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION")
        
        token_limit_env = os.getenv("AZURE_OPENAI_TOKEN_LIMIT")
        self._token_limit = token_limit or (int(token_limit_env) if token_limit_env else None)
        
        input_price_env = os.getenv("AZURE_OPENAI_INPUT_TOKEN_PRICE")
        self._input_token_price = input_token_price or (float(input_price_env) if input_price_env else None)
        
        output_price_env = os.getenv("AZURE_OPENAI_OUTPUT_TOKEN_PRICE")
        self._output_token_price = output_token_price or (float(output_price_env) if output_price_env else None)
        
        # Lazy-initialized clients
        self._async_client: Optional[AsyncAzureOpenAI] = None
        self._sync_client: Optional[AzureOpenAI] = None
        self._client_lock = threading.Lock()  # thread safe lazy initialization

        self._system_prompt_msg = {
            "role": "system",
            "content": (
                "You are an assistant to a data analyst. "
                "Your responsibility is to assist in extracting, standardizing, and enriching data. "
                "Be concise and accurate in your responses. "
                "Your responses are fed directly into an SQL environment; "
                "therefore, ensure that your outputs are structured as succinct data points, not as prose.\n"
            ),
        }

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
                "type": "input_text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64_png_string}",
                    }
                )

        input_messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = await self.async_client.responses.create(
            model=self._model,
            input=input_messages,
        )
        self._get_token_usage(response)
        return response.output_text

    async def generate_structured_response(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "input_text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64_png_string}",
                    }
                )

        input_messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = await self.async_client.responses.create(
            model=self._model,
            input=input_messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "structured_response",
                    "schema": output_schema["schema"],
                    "strict": True,
                }
            },
        )
        self._get_token_usage(response)
        return json.loads(response.output_text)

    def generate_text_response_sync(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "input_text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64_png_string}",
                    }
                )

        input_messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = self.sync_client.responses.create(
            model=self._model,
            input=input_messages,
        )
        self._get_token_usage(response)
        return response.output_text

    def generate_structured_response_sync(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        user_content: list[dict] = []
        user_content.append(
            {
                "type": "input_text",
                "text": self._truncate_to_token_limit_if_necessary(prompt),
            }
        )
        if b64_png_strings:
            for b64_png_string in b64_png_strings:
                user_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64_png_string}",
                    }
                )

        input_messages = [
            self._system_prompt_msg,
            {"role": "user", "content": user_content},
        ]

        response = self.sync_client.responses.create(
            model=self._model,
            input=input_messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "structured_response",
                    "schema": output_schema["schema"],
                    "strict": True,
                }
            },
        )
        self._get_token_usage(response)
        return json.loads(response.output_text)

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

    def _get_token_usage(self, response: Response) -> TokenUsage:
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
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
