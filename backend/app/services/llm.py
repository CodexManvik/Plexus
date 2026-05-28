"""
llm.py — Cohere-only LLM service.
"""
import asyncio
import sys
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.logger import clm_logger


class CohereService:
    def __init__(self):
        self.cohere_api_key = settings.cohere_api_key or ""
        self.cohere_model = settings.cohere_model
        self.cohere_extraction_model = settings.cohere_extraction_model
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _execute_cohere_chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = "https://api.cohere.com/v2/chat"
        headers = {
            "Authorization": f"Bearer {self.cohere_api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        # Handle reasoning model token budget issue
        _is_reasoning_model = "a-plus" in model or "thinking" in model
        effective_max_tokens = max(max_tokens, 4000) if _is_reasoning_model else max_tokens
        if effective_max_tokens > 0:
            payload["max_tokens"] = effective_max_tokens

        if response_format:
            payload["response_format"] = response_format

        clm_logger.info(f"LLM Request -> Model: {model} | Temp: {temperature} | MaxTokens: {max_tokens}")
        clm_logger.info(f"System Prompt: {system_prompt[:300]}...")
        clm_logger.info(f"User Prompt: {user_prompt[:500]}...")

        client = self._get_client()
        backoff = 1.0

        for attempt in range(5):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                finish_reason = data.get("finish_reason", "")
                if finish_reason == "MAX_TOKENS":
                    clm_logger.warning(
                        f"finish_reason=MAX_TOKENS on model '{model}'. "
                        "Consider raising max_tokens or switching to a non-reasoning model."
                    )

                message = data.get("message") or {}
                content = message.get("content") or []
                if isinstance(content, list):
                    # Extract only the text blocks
                    text_parts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    result = "".join(text_parts).strip()
                    if result:
                        clm_logger.info(f"LLM Response -> Success (chars={len(result)}): {result}")
                        return result

                    # Fallback: if only thinking blocks arrived (MAX_TOKENS edge case)
                    thinking_parts = [
                        block.get("thinking", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "thinking"
                    ]
                    if thinking_parts:
                        clm_logger.warning(
                            f"Got only thinking blocks, no text block on model '{model}'. "
                            f"finish_reason={finish_reason!r}. Model likely hit token limit during reasoning."
                        )
                    return ""
                return ""
            except httpx.HTTPStatusError as error:
                clm_logger.warning(f"Cohere HTTP {error.response.status_code} on attempt {attempt+1}: {error.response.text[:200]}")
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                break
            except Exception as error:
                clm_logger.warning(f"Cohere Connection Error on attempt {attempt+1}: {error}")
                if attempt < 4:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                break

        clm_logger.error(f"LLM Request -> FAILED after retries.")
        return ""

    async def get_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> str:
        """
        Public chat completion method using the primary Cohere model.
        """
        return await self._execute_cohere_chat(
            model=self.cohere_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def get_extraction_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Faster, optimized extraction completion using the specialized extraction model.
        """
        return await self._execute_cohere_chat(
            model=self.cohere_extraction_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=None,
            temperature=0.0,
            max_tokens=800,
        )


azure_llm = CohereService()