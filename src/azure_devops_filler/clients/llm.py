"""Cliente LLM para enriquecimento de descrições (OpenAI-compatible API)."""

import asyncio
import httpx

from ..models import Activity

DEFAULT_SYSTEM_PROMPT = (
    "Você é um assistente que escreve descrições de tasks de desenvolvimento de software "
    "em português brasileiro, de forma concisa e técnica. "
    "Escreva um parágrafo curto (2-4 frases) descrevendo a atividade realizada. "
    "Use linguagem formal e mencione o impacto ou objetivo da atividade quando possível. "
    "Não repita o título. Não use marcadores ou listas."
)


class LLMEnhancer:
    """Enriquece descrições de atividades usando um LLM via API OpenAI-compatible."""

    def __init__(self, base_url: str, model: str, api_key: str = "ollama"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def enhance_description(self, activity: Activity, system_prompt: str | None = None) -> str:
        """Gera uma descrição enriquecida para a atividade.

        Retorna a descrição original em caso de falha.

        Args:
            activity: Atividade a descrever
            system_prompt: System prompt customizado (usa padrão se None)

        Returns:
            Descrição gerada pelo LLM ou descrição original como fallback
        """
        prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        user_message = (
            f"Fonte: {activity.source.value}\n"
            f"Título: {activity.title}\n"
            f"Data: {activity.date.isoformat()}\n"
            f"Horas: {activity.hours}h\n"
            f"Descrição bruta: {activity.description or '(sem descrição)'}\n\n"
            "Escreva a descrição da task."
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 300,
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_retries = 5
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 429:
                        retry_after = float(response.headers.get("retry-after", 2 ** attempt))
                        await asyncio.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()

            except httpx.HTTPStatusError:
                return activity.description or ""
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return activity.description or ""

        return activity.description or ""
