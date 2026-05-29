"""
llm.py — Cohere-only and Local Llama.cpp LLM services.
"""
import asyncio
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.logger import clm_logger


class CohereService:
    def __init__(self):
        self.cohere_api_key = settings.cohere_api_key or ""
        self.cohere_model = settings.cohere_model
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
        Extraction completion using the single configured Cohere model.
        """
        return await self._execute_cohere_chat(
            model=self.cohere_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=None,
            temperature=0.0,
            max_tokens=800,
        )


class LocalLLMService:
    """
    LocalLLMService — Remote high-speed inference tier using Groq API for narrow
    grounding, validation, and OCR noise repair tasks.
    Falls back to CohereService if GROQ_API_KEY is not configured.
    """
    def __init__(self):
        self.groq_api_key = settings.groq_api_key or ""
        self.groq_model = settings.groq_model
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=45.0)
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def get_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        """
        Queries the Groq API via HTTPX Chat Completions endpoint, with CohereService fallback.
        """
        if not self.groq_api_key:
            clm_logger.info("[LocalLLM/Groq] No GROQ_API_KEY configured. Delegating task to Cohere.")
            return await cohere_llm.get_chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        clm_logger.info(f"[LocalLLM/Groq] Request -> Model: {self.groq_model} | Temp: {temperature} | MaxTokens: {max_tokens}")
        client = self._get_client()
        backoff = 1.0

        for attempt in range(4):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    if content:
                        clm_logger.info(f"[LocalLLM/Groq] Response -> Success (chars={len(content)})")
                        return content
                return ""
            except httpx.HTTPStatusError as error:
                clm_logger.warning(
                    f"[LocalLLM/Groq] HTTP {error.response.status_code} on attempt {attempt+1}: {error.response.text[:200]}"
                )
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                break
            except Exception as error:
                clm_logger.warning(f"[LocalLLM/Groq] Connection Error on attempt {attempt+1}: {error}")
                if attempt < 3:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                break

        clm_logger.error("[LocalLLM/Groq] Request failed after retries. Delegating fallback to Cohere.")
        return await cohere_llm.get_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )


cohere_llm = CohereService()
local_llm = LocalLLMService()