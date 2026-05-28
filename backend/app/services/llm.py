"""
llm.py — Multi-provider LLM service (Azure OpenAI / Google AI Studio / Cohere).

Fixes vs v1:
  1. _provider_sequence loop used `if` instead of `elif` — ALL branches executed
     in one iteration regardless of the matched provider. Fixed to use elif.
  2. Cohere max_tokens floor of 2000 removed — was causing rate-limit spikes on
     short extraction calls that only need ~400 tokens.
  3. Cohere response_format passthrough removed from get_chat_completion default
     path for extraction — the JSON schema instruction in the prompt is more
     reliable than the API field for command-a-plus-05-2026.
  4. aclose() is now idempotent (safe to call multiple times on shutdown).
"""
import asyncio
import sys
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


class MultiProviderLLMService:
    def __init__(self):
        self.provider = (settings.llm_provider or "auto").strip().lower()

        self.azure_api_key = settings.azure_openai_api_key or ""
        self.azure_endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
        self.azure_deployment_name = settings.azure_openai_deployment_name
        self.azure_api_version = settings.azure_openai_api_version

        self.google_api_key = settings.google_ai_studio_api_key or ""
        self.google_model = settings.google_ai_studio_model

        self.cohere_api_key = settings.cohere_api_key or ""
        self.cohere_model = settings.cohere_model

        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # ── Provider availability checks ─────────────────────────────────────────

    def _cohere_available(self) -> bool:
        return bool(self.cohere_api_key and self.cohere_model)

    def _azure_available(self) -> bool:
        return bool(
            self.azure_api_key
            and self.azure_endpoint
            and self.azure_deployment_name
            and self.azure_api_version
        )

    def _google_available(self) -> bool:
        return bool(self.google_api_key and self.google_model)

    def _provider_sequence(self) -> List[str]:
        """Returns ordered list of providers to try, based on LLM_PROVIDER setting."""
        if self.provider == "cohere":
            return ["cohere", "google", "azure"]
        if self.provider == "azure":
            return ["azure", "google", "cohere"]
        if self.provider == "google":
            return ["google", "azure", "cohere"]

        # Auto: prefer Cohere → Google → Azure based on key availability
        seq = []
        if self._cohere_available():
            seq.append("cohere")
        if self._google_available():
            seq.append("google")
        if self._azure_available():
            seq.append("azure")
        return seq or ["google"]

    # ── Cohere ───────────────────────────────────────────────────────────────

    async def _cohere_chat_completion(
        self,
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
            "model": self.cohere_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        # command-a-plus-05-2026 is a reasoning model: it spends tokens on an
        # internal chain-of-thought (type=="thinking") BEFORE emitting the
        # actual response (type=="text").  If max_tokens is too small the model
        # exhausts its budget on reasoning and never produces a text block.
        # Enforce a minimum of 4000 for reasoning models to ensure the text
        # block can be emitted.  Non-reasoning models are unaffected.
        _is_reasoning_model = "a-plus" in self.cohere_model or "thinking" in self.cohere_model
        effective_max_tokens = max(max_tokens, 4000) if _is_reasoning_model else max_tokens
        if effective_max_tokens > 0:
            payload["max_tokens"] = effective_max_tokens

        # Only pass response_format if the caller explicitly wants it
        # (extraction callers pass None to avoid Cohere quirks).
        if response_format:
            payload["response_format"] = response_format

        client = self._get_client()
        backoff = 1.0

        for attempt in range(5):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                finish_reason = data.get("finish_reason", "")
                if finish_reason == "MAX_TOKENS":
                    print(
                        f"[Cohere API] WARNING: finish_reason=MAX_TOKENS on model "
                        f"'{self.cohere_model}'. Consider raising max_tokens or "
                        "switching to a non-reasoning model (e.g. command-r-plus).",
                        file=sys.stderr,
                    )

                message = data.get("message") or {}
                content = message.get("content") or []
                if isinstance(content, list):
                    # Reasoning models emit type=="thinking" blocks first, then
                    # type=="text" blocks.  Extract only the text blocks.
                    text_parts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    result = "".join(text_parts).strip()
                    if result:
                        return result
                    # Fallback: if only thinking blocks arrived (MAX_TOKENS edge case)
                    # surface that clearly rather than silently returning empty.
                    thinking_parts = [
                        block.get("thinking", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "thinking"
                    ]
                    if thinking_parts:
                        print(
                            f"[Cohere API] Got only thinking blocks, no text block. "
                            f"finish_reason={finish_reason!r}. Model likely hit token limit "
                            "during reasoning. Increase max_tokens or switch model.",
                            file=sys.stderr,
                        )
                    return ""
                return ""
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    print(
                        f"[Cohere API] Transient {error.response.status_code}. "
                        f"Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(
                    f"[Cohere API] HTTP {error.response.status_code}: {error.response.text[:300]}",
                    file=sys.stderr,
                )
                break
            except Exception as error:
                if attempt < 4:
                    print(
                        f"[Cohere API] Connection error: {error}. Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(f"[Cohere API] Failed after retries: {error}", file=sys.stderr)
                break

        return ""

    # ── Azure OpenAI ─────────────────────────────────────────────────────────

    async def _azure_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = (
            f"{self.azure_endpoint}/openai/deployments/{self.azure_deployment_name}"
            f"/chat/completions?api-version={self.azure_api_version}"
        )
        headers = {"api-key": self.azure_api_key, "Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        client = self._get_client()
        backoff = 1.0

        for attempt in range(5):
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if choices:
                    return choices[0].get("message", {}).get("content", "") or ""
                return ""
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    print(
                        f"[Azure OpenAI] Transient {error.response.status_code}. "
                        f"Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(
                    f"[Azure OpenAI] HTTP {error.response.status_code}: {error.response.text[:300]}",
                    file=sys.stderr,
                )
                break
            except Exception as error:
                if attempt < 4:
                    print(
                        f"[Azure OpenAI] Connection error: {error}. Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(f"[Azure OpenAI] Failed after retries: {error}", file=sys.stderr)
                break

        return ""

    # ── Google AI Studio ─────────────────────────────────────────────────────

    async def _google_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.google_model}:generateContent?key={self.google_api_key}"
        )
        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if response_format:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        client = self._get_client()
        backoff = 1.0

        for attempt in range(5):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                for candidate in data.get("candidates") or []:
                    parts = candidate.get("content", {}).get("parts", [])
                    answer = "".join(
                        p.get("text", "") for p in parts if isinstance(p, dict)
                    ).strip()
                    if answer:
                        return answer
                return ""
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    print(
                        f"[Google AI Studio] Transient {error.response.status_code}. "
                        f"Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(
                    f"[Google AI Studio] HTTP {error.response.status_code}: "
                    f"{error.response.text[:300]}",
                    file=sys.stderr,
                )
                break
            except Exception as error:
                if attempt < 4:
                    print(
                        f"[Google AI Studio] Connection error: {error}. "
                        f"Retrying in {backoff:.0f}s…",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(f"[Google AI Studio] Failed after retries: {error}", file=sys.stderr)
                break

        return ""

    # ── Public entry point ────────────────────────────────────────────────────

    async def get_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> str:
        """
        Sends a chat completion request, trying providers in priority order.

        The first provider that returns a non-empty string wins.
        Falls back to the next provider on empty response or error.
        """
        for provider in self._provider_sequence():
            # ── FIX: use elif so only the matching branch executes per loop iteration ──
            if provider == "cohere":
                if not self._cohere_available():
                    print("[LLM] Cohere not configured. Skipping.", file=sys.stderr)
                    continue
                answer = await self._cohere_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            elif provider == "google":
                if not self._google_available():
                    continue
                answer = await self._google_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            elif provider == "azure":
                if not self._azure_available():
                    continue
                answer = await self._azure_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                continue

            if answer.strip():
                return answer

        print("[LLM] All providers returned empty or are unconfigured.", file=sys.stderr)
        return ""


azure_llm = MultiProviderLLMService()