"""Cliente para Azure DevOps REST API."""

import base64
from datetime import date, datetime
from typing import Optional

import httpx

from ..models import Commit, CreatedTask, CreatedUserStory, TaskConfig, UserStoryConfig


class AzureDevOpsClient:
    """Cliente para interagir com a API do Azure DevOps."""

    API_VERSION = "7.1"

    def __init__(
        self,
        organization: str,
        pat: str,
        default_project: Optional[str] = None,
        base_url: str = "https://dev.azure.com",
    ):
        """Inicializa o cliente.

        Args:
            organization: Nome da organização no Azure DevOps
            pat: Personal Access Token
            default_project: Projeto padrão para operações
        """
        self.organization = organization
        self.default_project = default_project
        self._pat = pat
        self._base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def _auth_header(self) -> str:
        """Gera o header de autenticação Basic."""
        credentials = base64.b64encode(f":{self._pat}".encode()).decode()
        return f"Basic {credentials}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP, criando-o se necessário."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": self._auth_header,
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "AzureDevOpsClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()

    async def test_connection(self) -> bool:
        """Testa a conexão com o Azure DevOps.

        Returns:
            True se a conexão foi bem sucedida

        Raises:
            httpx.HTTPStatusError: Se a API retornar erro
            httpx.RequestError: Se houver erro de rede
        """
        client = await self._get_client()
        url = f"{self._base_url}/{self.organization}/_apis/projects?api-version={self.API_VERSION}"

        response = await client.get(url)
        response.raise_for_status()
        return True

    async def create_task(self, task: TaskConfig, project: Optional[str] = None) -> CreatedTask:
        """Cria uma Task no Azure DevOps.

        Args:
            task: Configuração da Task a ser criada
            project: Projeto onde criar a Task (usa default se não especificado)

        Returns:
            Dados da Task criada

        Raises:
            ValueError: Se o projeto não foi especificado
            httpx.HTTPStatusError: Se a requisição falhar
        """
        target_project = project or task.project or self.default_project
        if not target_project:
            raise ValueError("Projeto não especificado")

        client = await self._get_client()
        url = (
            f"{self._base_url}/{self.organization}/{target_project}"
            f"/_apis/wit/workitems/$Task?api-version={self.API_VERSION}"
        )

        # Cria sem o estado para respeitar o workflow do Azure DevOps
        response = await client.post(
            url,
            json=task.to_json_patch(include_state=False),
            headers={"Content-Type": "application/json-patch+json"},
        )
        response.raise_for_status()

        data = response.json()
        task_id = data["id"]

        patch_url = (
            f"{self._base_url}/{self.organization}/{target_project}"
            f"/_apis/wit/workitems/{task_id}?api-version={self.API_VERSION}"
        )

        # Atualiza o estado separadamente (transição de estado não é permitida na criação)
        if task.state:
            await client.patch(
                patch_url,
                json=[{"op": "add", "path": "/fields/System.State", "value": task.state}],
                headers={"Content-Type": "application/json-patch+json"},
            )

        # Vincula ao pai (User Story) via PATCH separado
        if task.parent_id:
            parent_url = f"{self._base_url}/{self.organization}/_apis/wit/workitems/{task.parent_id}"
            await client.patch(
                patch_url,
                json=[{
                    "op": "add",
                    "path": "/relations/-",
                    "value": {
                        "rel": "System.LinkTypes.Hierarchy-Reverse",
                        "url": parent_url,
                    },
                }],
                headers={"Content-Type": "application/json-patch+json"},
            )

        return CreatedTask(
            id=task_id,
            url=data["_links"]["html"]["href"],
            title=data["fields"]["System.Title"],
            project=target_project,
        )

    async def create_user_story(self, user_story: UserStoryConfig, project: Optional[str] = None) -> CreatedUserStory:
        """Cria uma User Story no Azure DevOps.

        Args:
            user_story: Configuração da User Story a ser criada
            project: Projeto onde criar (usa default se não especificado)

        Returns:
            Dados da User Story criada

        Raises:
            ValueError: Se o projeto não foi especificado
            httpx.HTTPStatusError: Se a requisição falhar
        """
        target_project = project or user_story.project or self.default_project
        if not target_project:
            raise ValueError("Projeto não especificado")

        client = await self._get_client()
        url = (
            f"{self._base_url}/{self.organization}/{target_project}"
            f"/_apis/wit/workitems/$User%20Story?api-version={self.API_VERSION}"
        )

        # Cria sem o estado para respeitar o workflow do Azure DevOps
        response = await client.post(
            url,
            json=user_story.to_json_patch(include_state=False),
            headers={"Content-Type": "application/json-patch+json"},
        )
        response.raise_for_status()

        data = response.json()
        us_id = data["id"]

        # Atualiza o estado separadamente
        if user_story.state:
            patch_url = (
                f"{self._base_url}/{self.organization}/{target_project}"
                f"/_apis/wit/workitems/{us_id}?api-version={self.API_VERSION}"
            )
            await client.patch(
                patch_url,
                json=[{"op": "add", "path": "/fields/System.State", "value": user_story.state}],
                headers={"Content-Type": "application/json-patch+json"},
            )

        return CreatedUserStory(
            id=us_id,
            url=data["_links"]["html"]["href"],
            title=data["fields"]["System.Title"],
            project=target_project,
        )

    async def get_commits(
        self,
        repository: str,
        project: Optional[str] = None,
        author: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[Commit]:
        """Busca commits de um repositório.

        Args:
            repository: Nome do repositório
            project: Projeto do repositório (usa default se não especificado)
            author: Filtrar por autor
            from_date: Data inicial
            to_date: Data final

        Returns:
            Lista de commits encontrados

        Raises:
            ValueError: Se o projeto não foi especificado
            httpx.HTTPStatusError: Se a requisição falhar
        """
        target_project = project or self.default_project
        if not target_project:
            raise ValueError("Projeto não especificado")

        client = await self._get_client()
        url = (
            f"{self._base_url}/{self.organization}/{target_project}"
            f"/_apis/git/repositories/{repository}/commits?api-version={self.API_VERSION}"
        )

        params = {}
        if author:
            params["searchCriteria.author"] = author
        if from_date:
            # Formato: MM/DD/YYYY HH:MM:SS AM/PM
            params["searchCriteria.fromDate"] = from_date.strftime("%m/%d/%Y 12:00:00 AM")
        if to_date:
            params["searchCriteria.toDate"] = to_date.strftime("%m/%d/%Y 11:59:59 PM")

        response = await client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        commits = []

        for item in data.get("value", []):
            commit_date = datetime.fromisoformat(item["author"]["date"].replace("Z", "+00:00"))
            commits.append(
                Commit(
                    commit_id=item["commitId"],
                    message=item["comment"],
                    author=item["author"]["email"],
                    date=commit_date,
                    repository=repository,
                )
            )

        return commits

    async def get_repositories(self, project: Optional[str] = None) -> list[dict]:
        """Lista repositórios de um projeto.

        Args:
            project: Projeto (usa default se não especificado)

        Returns:
            Lista de repositórios

        Raises:
            ValueError: Se o projeto não foi especificado
            httpx.HTTPStatusError: Se a requisição falhar
        """
        target_project = project or self.default_project
        if not target_project:
            raise ValueError("Projeto não especificado")

        client = await self._get_client()
        url = (
            f"{self._base_url}/{self.organization}/{target_project}"
            f"/_apis/git/repositories?api-version={self.API_VERSION}"
        )

        response = await client.get(url)
        response.raise_for_status()

        data = response.json()
        return data.get("value", [])
