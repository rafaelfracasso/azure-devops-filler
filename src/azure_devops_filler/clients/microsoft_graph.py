"""Cliente para Microsoft Graph API."""

from datetime import date, datetime
from typing import Optional

import httpx

from ..models import CalendarEvent


class MicrosoftGraphClient:
    """Cliente para interagir com a API do Microsoft Graph."""

    AUTH_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        """Inicializa o cliente.

        Args:
            tenant_id: ID do tenant Azure AD
            client_id: ID da aplicação registrada
            client_secret: Secret da aplicação
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando-o se necessário."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "MicrosoftGraphClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()

    async def _authenticate(self) -> str:
        """Autentica com o Azure AD e obtém o access token.

        Returns:
            Access token

        Raises:
            httpx.HTTPStatusError: Se a autenticação falhar
        """
        if self._access_token:
            return self._access_token

        client = await self._get_client()
        url = self.AUTH_URL.format(tenant_id=self.tenant_id)

        response = await client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        return self._access_token

    async def test_connection(self) -> bool:
        """Testa a conexão com o Microsoft Graph.

        Returns:
            True se a conexão foi bem sucedida
        """
        try:
            await self._authenticate()
            return True
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    async def get_calendar_events(
        self,
        user_email: str,
        from_date: date,
        to_date: date,
    ) -> list[CalendarEvent]:
        """Busca eventos do calendário de um usuário.

        Args:
            user_email: Email do usuário
            from_date: Data inicial
            to_date: Data final

        Returns:
            Lista de eventos do calendário

        Raises:
            httpx.HTTPStatusError: Se a requisição falhar
        """
        token = await self._authenticate()
        client = await self._get_client()

        url = f"{self.GRAPH_URL}/users/{user_email}/calendar/events"

        # Formatar datas para ISO 8601
        start_datetime = f"{from_date.isoformat()}T00:00:00Z"
        end_datetime = f"{to_date.isoformat()}T23:59:59Z"

        params = {
            "$filter": (
                f"start/dateTime ge '{start_datetime}' and "
                f"end/dateTime le '{end_datetime}'"
            ),
            "$select": "subject,start,end,body,categories",
            "$orderby": "start/dateTime",
        }

        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        data = response.json()
        events = []

        for item in data.get("value", []):
            start = datetime.fromisoformat(item["start"]["dateTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(item["end"]["dateTime"].replace("Z", "+00:00"))

            events.append(
                CalendarEvent(
                    subject=item["subject"],
                    start=start,
                    end=end,
                    body=item.get("body", {}).get("content"),
                    categories=item.get("categories", []),
                )
            )

        return events
