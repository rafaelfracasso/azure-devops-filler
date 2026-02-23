"""Coletor de atividades do Azure Git."""

from collections import defaultdict
from datetime import date
from typing import Optional

from ..clients.azure_devops import AzureDevOpsClient
from ..config import GitConfig
from ..models import Activity, Commit, SourceType
from .base import BaseSource


class GitSource(BaseSource):
    """Coletor de atividades do Azure Git."""

    def __init__(
        self,
        config: GitConfig,
        azure_client: AzureDevOpsClient,
        author_email: str,
    ):
        """Inicializa o coletor.

        Args:
            config: Configuração do Git
            azure_client: Cliente do Azure DevOps
            author_email: Email do autor para filtrar commits
        """
        self._config = config
        self._azure_client = azure_client
        self._author_email = author_email

    @property
    def source_type(self) -> SourceType:
        """Retorna o tipo da fonte."""
        return SourceType.GIT

    @property
    def name(self) -> str:
        """Retorna o nome da fonte."""
        return "Azure Git"

    @property
    def enabled(self) -> bool:
        """Retorna se a fonte está habilitada."""
        return self._config.enabled

    async def collect(self, target_date: date) -> list[Activity]:
        """Coleta atividades do Git para uma data específica.

        Busca commits do autor configurado e agrupa por repositório,
        criando uma atividade por repositório com commits naquele dia.

        Args:
            target_date: Data para coletar atividades

        Returns:
            Lista de atividades coletadas
        """
        activities = []

        for repo_config in self._config.repositories:
            commits = await self._azure_client.get_commits(
                repository=repo_config.name,
                project=repo_config.project,
                author=self._author_email,
                from_date=target_date,
                to_date=target_date,
            )

            for commit in commits:
                activities.append(
                    self._create_activity_from_commit(
                        commit=commit,
                        target_date=target_date,
                        repo_name=repo_config.name,
                        area_path=repo_config.area_path,
                        tags=list(repo_config.tags),
                    )
                )

        return activities

    def _create_activity_from_commit(
        self,
        commit: Commit,
        target_date: date,
        repo_name: str,
        area_path: str,
        tags: list[str],
    ) -> Activity:
        """Cria uma atividade a partir de um commit.

        Args:
            commit: Commit do Git
            target_date: Data da atividade
            repo_name: Nome do repositório
            area_path: Area Path para a Task
            tags: Tags para a Task

        Returns:
            Atividade criada
        """
        message = commit.message.split("\n")[0].strip()
        title = f"[{repo_name}] {message}"
        description = (
            f"Commit realizado no repositório {repo_name}.\n"
            f"Hash: {commit.commit_id}\n"
            f"Mensagem: {message}"
        )

        return Activity(
            title=title,
            source=SourceType.GIT,
            date=target_date,
            hours=0.5,
            description=description,
            area_path=area_path,
            tags=tags,
            activity_datetime=commit.date,
        )

    async def test_connection(self) -> bool:
        """Testa a conexão com o Azure Git.

        Returns:
            True se a conexão foi bem sucedida
        """
        if not self._config.repositories:
            return False

        return await self._azure_client.test_connection()

    async def get_commits_in_range(
        self,
        from_date: date,
        to_date: date,
        repository: Optional[str] = None,
    ) -> dict[str, list[Commit]]:
        """Busca commits em um período agrupados por repositório.

        Args:
            from_date: Data inicial
            to_date: Data final
            repository: Nome do repositório (opcional, todos se não especificado)

        Returns:
            Dicionário com repositórios e suas listas de commits
        """
        result: dict[str, list[Commit]] = defaultdict(list)

        repos_to_check = self._config.repositories
        if repository:
            repos_to_check = [r for r in repos_to_check if r.name == repository]

        for repo_config in repos_to_check:
            commits = await self._azure_client.get_commits(
                repository=repo_config.name,
                project=repo_config.project,
                author=self._author_email,
                from_date=from_date,
                to_date=to_date,
            )
            if commits:
                result[repo_config.name].extend(commits)

        return dict(result)
