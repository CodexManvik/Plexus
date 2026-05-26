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

        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=45.0)
        return self._client

    async def aclose(self):
        """Closes the persistent HTTP client pool when the application shuts down."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _provider_sequence(self) -> List[str]:
        if self.provider == "azure":
            return ["azure", "google"]
        if self.provider == "google":
            return ["google", "azure"]
        return ["google", "azure"]

    def _azure_available(self) -> bool:
        return bool(
            self.azure_api_key
            and self.azure_endpoint
            and self.azure_deployment_name
            and self.azure_api_version
        )

    def _google_available(self) -> bool:
        return bool(self.google_api_key and self.google_model)

    async def _azure_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        clean_endpoint = self.azure_endpoint.rstrip("/") if self.azure_endpoint else ""
        url = (
            f"{clean_endpoint}/openai/deployments/{self.azure_deployment_name}"
            f"/chat/completions?api-version={self.azure_api_version}"
        )
        headers = {"api-key": self.azure_api_key, "Content-Type": "application/json"}
        payload = {
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
                        f"[Azure OpenAI] Transient error {error.response.status_code}. Retrying in {backoff}s...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(
                    f"[Azure OpenAI] HTTP Error: {error.response.status_code} - {error.response.text}",
                    file=sys.stderr,
                )
                break
            except Exception as error:
                if attempt < 4:
                    print(
                        f"[Azure OpenAI] Connection error: {error}. Retrying in {backoff}s...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(f"[Azure OpenAI] Request Failed: {error}. Returning empty completion.", file=sys.stderr)
                break

        return ""

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
                candidates = data.get("candidates") or []
                for candidate in candidates:
                    parts = candidate.get("content", {}).get("parts", [])
                    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
                    answer = "".join(texts).strip()
                    if answer:
                        return answer
                return ""
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    print(
                        f"[Google AI Studio] Transient error {error.response.status_code}. Retrying in {backoff}s...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(
                    f"[Google AI Studio] HTTP Error: {error.response.status_code} - {error.response.text}",
                    file=sys.stderr,
                )
                break
            except Exception as error:
                if attempt < 4:
                    print(
                        f"[Google AI Studio] Connection error: {error}. Retrying in {backoff}s...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                print(f"[Google AI Studio] Request Failed: {error}. Returning empty completion.", file=sys.stderr)
                break

        return ""

    async def get_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> str:
        """
        Sends a chat completion request to the configured LLM provider.

        Provider order:
        - `LLM_PROVIDER=google` or `LLM_PROVIDER=azure` pins the primary provider.
        - `LLM_PROVIDER=auto` prefers Google AI Studio when configured, then Azure.
        """
        for provider in self._provider_sequence():
            if provider == "google":
                if not self._google_available():
                    print("[Google AI Studio] Credentials missing. Skipping provider.", file=sys.stderr)
                    continue
                answer = await self._google_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if answer.strip():
                    return answer

            if provider == "azure":
                if not self._azure_available():
                    print("[Azure OpenAI] Credentials missing. Skipping provider.", file=sys.stderr)
                    continue
                answer = await self._azure_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if answer.strip():
                    return answer

        return ""


azure_llm = MultiProviderLLMService()