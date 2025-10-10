from .base import LLMProvider, JSONSchema
from typing import Optional, Any
import os
import json
import logging
from openai import OpenAI
import tiktoken


class OpenAIProvider(LLMProvider):
    """OpenAI implementation of LLM provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4.1-2025-04-14", token_limit: int = 190000):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use (default: gpt-4.1-2025-04-14 for cost efficiency with high token limit)
        """
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._token_limit = token_limit
        self._client = OpenAI(api_key=self._api_key)
        self._temperature = 0.3
        self._system_prompt = (
            "You are an assistant to a data analyst. "
            "Your responsibility is to assist in standardizing, enriching, and improving data. "
            "Be concise and accurate in your responses. "
            "Your responses are fed directly into an SQL environment; "
            "therefore, ensure that your outputs are structured as data points, not as prose.\n"
        )
        self._system_prompt_msg = {"role": "system", "content": self._system_prompt}

    def generate_text_response(
        self, 
        prompt: str
    ) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[self._system_prompt_msg, {"role": "user", "content": self._truncate_to_token_limit_if_necessary(prompt)}],
                temperature=self._temperature,
            )
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
                messages=[self._system_prompt_msg, {"role": "user", "content": self._truncate_to_token_limit_if_necessary(prompt)}],
                response_format={
                    "type": "json_schema",
                    "json_schema": output_schema,
                },
                temperature=self._temperature,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logging.error(f"Error generating structured response: {str(e)}")
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def _encode_as_tokens(
        self,
        prompt: str
    ) -> list[int]:
        return tiktoken.encoding_for_model(self._model).encode(prompt)

    def _decode_from_tokens(
        self,
        tokens: list[int]
    ) -> str:
        return tiktoken.encoding_for_model(self._model).decode(tokens)
    
    def count_tokens(
        self,
        prompt: str
    ) -> int:
        return len(self._encode_as_tokens(prompt))

    def _truncate_to_token_limit_if_necessary(
        self,
        prompt: str
    ) -> str:
        if self.count_tokens(prompt) > self._token_limit:
            logging.warning(f"User message prompt exceeds {self._token_limit} tokens; truncating. (System prompt tokens not counted-- truncation may be under true API limit.)")
            return self._decode_from_tokens(self._encode_as_tokens(prompt)[:self._token_limit])
        
        return prompt
