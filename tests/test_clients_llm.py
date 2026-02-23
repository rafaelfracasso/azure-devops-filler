"""Testes para o cliente LLM (enriquecimento de descrições)."""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from azure_devops_filler.clients.llm import DEFAULT_SYSTEM_PROMPT, LLMEnhancer
from azure_devops_filler.models import Activity, SourceType

BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "llama-3.3-70b-versatile"
COMPLETIONS_URL = f"{BASE_URL}/chat/completions"

LLM_SUCCESS_RESPONSE = {
    "choices": [{"message": {"content": "  Descrição técnica gerada pelo LLM.  "}}]
}


@pytest.fixture
def enhancer():
    return LLMEnhancer(base_url=BASE_URL, model=MODEL, api_key="test-key")


@pytest.fixture
def activity():
    return Activity(
        title="Reunião de planejamento",
        source=SourceType.OUTLOOK,
        date=date(2026, 2, 19),
        hours=1.5,
        description="Reunião de equipe",
    )


class TestLLMEnhancerSuccess:
    async def test_returns_stripped_llm_content(self, enhancer, activity):
        with respx.mock:
            respx.post(COMPLETIONS_URL).mock(
                return_value=httpx.Response(200, json=LLM_SUCCESS_RESPONSE)
            )
            result = await enhancer.enhance_description(activity)

        assert result == "Descrição técnica gerada pelo LLM."

    async def test_sends_activity_data_in_user_message(self, enhancer, activity):
        with respx.mock:
            route = respx.post(COMPLETIONS_URL).mock(
                return_value=httpx.Response(200, json=LLM_SUCCESS_RESPONSE)
            )
            await enhancer.enhance_description(activity)

        body = json.loads(route.calls[0].request.content)
        user_msg = body["messages"][1]["content"]
        assert "Reunião de planejamento" in user_msg
        assert "outlook" in user_msg
        assert "2026-02-19" in user_msg
        assert "1.5h" in user_msg

    async def test_uses_default_system_prompt_when_none(self, enhancer, activity):
        with respx.mock:
            route = respx.post(COMPLETIONS_URL).mock(
                return_value=httpx.Response(200, json=LLM_SUCCESS_RESPONSE)
            )
            await enhancer.enhance_description(activity, system_prompt=None)

        body = json.loads(route.calls[0].request.content)
        assert body["messages"][0]["content"] == DEFAULT_SYSTEM_PROMPT

    async def test_uses_custom_system_prompt_when_provided(self, enhancer, activity):
        custom_prompt = "Meu prompt customizado"
        with respx.mock:
            route = respx.post(COMPLETIONS_URL).mock(
                return_value=httpx.Response(200, json=LLM_SUCCESS_RESPONSE)
            )
            await enhancer.enhance_description(activity, system_prompt=custom_prompt)

        body = json.loads(route.calls[0].request.content)
        assert body["messages"][0]["content"] == custom_prompt

    async def test_sends_authorization_header(self, enhancer, activity):
        with respx.mock:
            route = respx.post(COMPLETIONS_URL).mock(
                return_value=httpx.Response(200, json=LLM_SUCCESS_RESPONSE)
            )
            await enhancer.enhance_description(activity)

        assert route.calls[0].request.headers["authorization"] == "Bearer test-key"


class TestLLMEnhancerFallback:
    async def test_fallback_on_server_error(self, enhancer, activity):
        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock):
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(return_value=httpx.Response(500))
                result = await enhancer.enhance_description(activity)

        assert result == activity.description

    async def test_fallback_on_network_error(self, enhancer, activity):
        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock):
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(
                    side_effect=httpx.ConnectError("Connection refused")
                )
                result = await enhancer.enhance_description(activity)

        assert result == activity.description

    async def test_fallback_returns_empty_string_when_description_is_none(self, enhancer):
        activity_no_desc = Activity(
            title="Atividade sem descrição",
            source=SourceType.RECURRING,
            date=date(2026, 2, 19),
            hours=0.5,
            description=None,
        )
        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock):
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(return_value=httpx.Response(500))
                result = await enhancer.enhance_description(activity_no_desc)

        assert result == ""


class TestLLMEnhancerRateLimiting:
    async def test_retries_on_429_and_returns_success(self, enhancer, activity):
        call_count = 0

        def rate_limit_then_success(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"retry-after": "2"})
            return httpx.Response(200, json=LLM_SUCCESS_RESPONSE)

        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(side_effect=rate_limit_then_success)
                result = await enhancer.enhance_description(activity)

        assert result == "Descrição técnica gerada pelo LLM."
        assert call_count == 2
        mock_sleep.assert_called_once_with(2.0)

    async def test_uses_retry_after_header_value(self, enhancer, activity):
        call_count = 0

        def rate_limit_then_success(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"retry-after": "5"})
            return httpx.Response(200, json=LLM_SUCCESS_RESPONSE)

        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(side_effect=rate_limit_then_success)
                await enhancer.enhance_description(activity)

        mock_sleep.assert_called_once_with(5.0)

    async def test_uses_exponential_backoff_when_no_retry_after(self, enhancer, activity):
        """Sem header Retry-After, usa 2^attempt como fallback."""
        call_count = 0

        def rate_limit_then_success(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429)  # sem retry-after
            return httpx.Response(200, json=LLM_SUCCESS_RESPONSE)

        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(side_effect=rate_limit_then_success)
                result = await enhancer.enhance_description(activity)

        assert result == "Descrição técnica gerada pelo LLM."
        # attempt=0 → 2^0 = 1
        mock_sleep.assert_called_once_with(1.0)

    async def test_returns_fallback_after_max_retries_all_429(self, enhancer, activity):
        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(
                    return_value=httpx.Response(429, headers={"retry-after": "1"})
                )
                result = await enhancer.enhance_description(activity)

        # Após esgotar tentativas, retorna fallback
        assert result == activity.description
        # 5 tentativas → 5 sleeps
        assert mock_sleep.call_count == 5

    async def test_multiple_429_then_success(self, enhancer, activity):
        """Deve funcionar mesmo com múltiplos 429 consecutivos antes do sucesso."""
        call_count = 0

        def rate_limit_x2_then_success(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return httpx.Response(429, headers={"retry-after": "1"})
            return httpx.Response(200, json=LLM_SUCCESS_RESPONSE)

        with patch("azure_devops_filler.clients.llm.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with respx.mock:
                respx.post(COMPLETIONS_URL).mock(side_effect=rate_limit_x2_then_success)
                result = await enhancer.enhance_description(activity)

        assert result == "Descrição técnica gerada pelo LLM."
        assert call_count == 3
        assert mock_sleep.call_count == 2
