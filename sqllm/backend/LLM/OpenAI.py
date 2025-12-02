from .base import LLMProvider, JSONSchema, TokenUsage
from typing import Optional, Any, Literal
import os
import json
import logging
from .context import accumulate_usage
from openai import AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI, OpenAI
from openai.types.responses import Response
import tiktoken
import rxconfig
import threading

ProviderType = Literal["openai", "azure"]


class OpenAIProvider(LLMProvider):
    """
    OpenAI/AzureOpenAI implementation with lazy-initialized sync and async clients.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider_type: Optional[ProviderType] = None,
        token_limit: int = 190000,
        azure_endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: API key (auto-detects from env if not provided)
            model: Model name (auto-selects based on environment if not provided)
            provider_type: "openai" or "azure" (auto-detects from rxconfig if not provided)
            token_limit: Maximum tokens for prompt
            azure_endpoint: Azure endpoint (only needed for Azure)
            api_version: Azure API version (only needed for Azure)
        """
        # Determine provider type
        if provider_type is None:
            self._provider_type: ProviderType = (
                "azure" if rxconfig.isProd() else "openai"
            )
        else:
            self._provider_type = provider_type

        # Set API key based on provider type
        if api_key is None:
            if self._provider_type == "azure":
                self._api_key = os.getenv("AZURE_OPENAI_API_KEY")
            else:
                self._api_key = os.getenv("OPENAI_API_KEY")
        else:
            self._api_key = api_key

        # Set model based on provider type
        if model is None:
            if self._provider_type == "azure":
                self._model = "gpt-4.1-nano"
            else:
                self._model = "gpt-4.1-2025-04-14"
        else:
            self._model = model

        # Azure-specific settings
        self._azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self._api_version = api_version

        # Lazy-initialized clients
        self._async_client: Optional[AsyncAzureOpenAI | AsyncOpenAI] = None
        self._sync_client: Optional[AzureOpenAI | OpenAI] = None
        self._client_lock = threading.Lock()  # thread safe lazy initialization

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
    def async_client(self) -> AsyncAzureOpenAI | AsyncOpenAI:
        """Lazy-initialize and return async client."""
        if self._async_client is None:
            with self._client_lock:
                if self._async_client is None:  # check again after getting lock
                    self._async_client = self._create_async_client()
        return self._async_client

    @property
    def sync_client(self) -> AzureOpenAI | OpenAI:
        """Lazy-initialize and return sync client."""
        if self._sync_client is None:
            with self._client_lock:
                if self._sync_client is None:  # check again after getting lock
                    self._sync_client = self._create_sync_client()
        return self._sync_client

    def _create_async_client(self) -> AsyncAzureOpenAI | AsyncOpenAI:
        """Create the appropriate async client based on provider type."""
        if self._provider_type == "azure":
            if not self._azure_endpoint:
                raise ValueError("azure_endpoint required for Azure provider")
            logging.info("Initializing AsyncAzureOpenAI client")
            return AsyncAzureOpenAI(
                api_key=self._api_key,
                azure_endpoint=self._azure_endpoint,
                api_version=self._api_version,
            )
        else:
            logging.info("Initializing AsyncOpenAI client")
            return AsyncOpenAI(api_key=self._api_key)

    def _create_sync_client(self) -> AzureOpenAI | OpenAI:
        """Create the appropriate sync client based on provider type."""
        if self._provider_type == "azure":
            if not self._azure_endpoint:
                raise ValueError("azure_endpoint required for Azure provider")
            logging.info("Initializing AzureOpenAI sync client")
            return AzureOpenAI(
                api_key=self._api_key,
                azure_endpoint=self._azure_endpoint,
                api_version=self._api_version,
            )
        else:
            logging.info("Initializing OpenAI sync client")
            return OpenAI(api_key=self._api_key)

    async def generate_text_response(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        try:
            user_content: list[dict] = []
            user_content.append(
                {
                    "type": "input_text",
                    "text": self._truncate_to_token_limit_if_necessary(prompt),
                }
            )
            # Add input_image objects if present
            if b64_png_strings:
                for b64_png_string in b64_png_strings:
                    user_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64_png_string}",
                        }
                    )
            # Compose input message array
            input_messages = [
                self._system_prompt_msg,
                {
                    "role": "user",
                    "content": user_content,
                },
            ]

            response = await self.async_client.responses.create(
                model=self._model,
                input=input_messages,
                temperature=self._temperature,
            )
            self._get_token_usage(response)
            return response.output_text
        except Exception as e:
            logging.error(f"Error generating text response: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    async def generate_structured_response(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            user_content: list[dict] = []
            user_content.append(
                {
                    "type": "input_text",
                    "text": self._truncate_to_token_limit_if_necessary(prompt),
                }
            )
            # Add input_image objects if present
            if b64_png_strings:
                for b64_png_string in b64_png_strings:
                    user_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64_png_string}",
                        }
                    )
            # Compose input message array
            input_messages = [
                self._system_prompt_msg,
                {
                    "role": "user",
                    "content": user_content,
                },
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
                temperature=self._temperature,
            )
            self._get_token_usage(response)
            return json.loads(response.output_text)
        except Exception as e:
            logging.error(f"Error generating structured response: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def generate_text_response_sync(
        self, prompt: str, b64_png_strings: list[str] | None = None
    ) -> str:
        try:
            user_content: list[dict] = []
            user_content.append(
                {
                    "type": "input_text",
                    "text": self._truncate_to_token_limit_if_necessary(prompt),
                }
            )
            # Add input_image objects if present
            if b64_png_strings:
                for b64_png_string in b64_png_strings:
                    user_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64_png_string}",
                        }
                    )
            # Compose input message array
            input_messages = [
                self._system_prompt_msg,
                {
                    "role": "user",
                    "content": user_content,
                },
            ]
            response = self.sync_client.responses.create(
                model=self._model,
                input=input_messages,
                temperature=self._temperature,
            )
            self._get_token_usage(response)
            return response.output_text
        except Exception as e:
            logging.error(f"Error generating text response (sync): {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def generate_structured_response_sync(
        self,
        prompt: str,
        output_schema: JSONSchema,
        b64_png_strings: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate structured response using sync client, supporting image input."""
        try:
            user_content: list[dict] = []
            user_content.append(
                {
                    "type": "input_text",
                    "text": self._truncate_to_token_limit_if_necessary(prompt),
                }
            )
            # Add input_image objects if present
            if b64_png_strings:
                for b64_png_string in b64_png_strings:
                    user_content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64_png_string}",
                        }
                    )
            # Compose input message array
            input_messages = [
                self._system_prompt_msg,  # unchanged system prompt
                {
                    "role": "user",
                    "content": user_content,
                },
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
                temperature=self._temperature,
            )
            self._get_token_usage(response)
            return json.loads(response.output_text)
        except Exception as e:
            logging.error(f"Error generating structured response (sync): {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

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
