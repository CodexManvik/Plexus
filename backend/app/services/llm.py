import httpx
import sys
from app.config import settings

class AzureOpenAIService:
    def __init__(self):
        self.api_key = settings.azure_openai_api_key
        self.endpoint = settings.azure_openai_endpoint
        self.deployment_name = settings.azure_openai_deployment_name
        self.api_version = settings.azure_openai_api_version
        
        # Build completion URL
        # Format: {endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}
        clean_endpoint = self.endpoint.rstrip('/') if self.endpoint else ""
        self.url = f"{clean_endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
        
        self.headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }

    async def get_chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        """
        Sends an asynchronous POST request to the Azure OpenAI completion API.
        If credentials are empty, returns an empty completion.
        """
        if not self.api_key or not self.endpoint or not self.deployment_name or not self.api_version:
            print("[Azure OpenAI] Credentials missing. Returning empty completion.", file=sys.stderr)
            return ""

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1500
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"[Azure OpenAI] Request Failed: {e}. Returning empty completion.", file=sys.stderr)
                return ""

azure_llm = AzureOpenAIService()
