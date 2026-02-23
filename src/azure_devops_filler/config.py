"""Carregamento e validação de configuração."""

import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Padrão para variáveis de ambiente: ${VAR_NAME} ou ${VAR_NAME:-default}
ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*))?\}")


def expand_env_vars(data: Any) -> Any:
    """Expande variáveis de ambiente recursivamente em dicionários e listas."""
    if isinstance(data, str):

        def replace_var(match):
            var_name, default_value = match.groups()
            return os.getenv(var_name, default_value or "")

        return ENV_VAR_PATTERN.sub(replace_var, data)
    elif isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(i) for i in data]
    return data


class AzureDevOpsConfig(BaseModel):
    """Configuração do Azure DevOps."""

    base_url: str = "https://dev.azure.com"
    organization: str
    default_project: str
    default_area: str
    default_iteration: str = "@CurrentIteration"
    author_email: str
    assigned_to: Optional[str] = None
    default_state: Optional[str] = None
    create_monthly_user_stories: bool = False
    user_story_name: Optional[str] = None
    enhance_descriptions: bool = False
    llm_system_prompt: Optional[str] = None


class OutlookMappingConfig(BaseModel):
    """Mapeamento de eventos do Outlook para Tasks."""

    area_path: str
    tags: list[str] = Field(default_factory=list)


class OutlookConfig(BaseModel):
    """Configuração da fonte Outlook."""

    enabled: bool = True
    type: Literal["csv", "ics", "graph_api"] = "csv"
    csv_path: Optional[str] = None
    ics_path: Optional[str] = None
    user_email: Optional[str] = None
    mapping: OutlookMappingConfig


class RecurringTemplateConfig(BaseModel):
    """Template de atividade recorrente."""

    name: str
    weekdays: list[int]
    hours: float
    area_path: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: list[int]) -> list[int]:
        """Valida que os dias da semana estão entre 0 e 6."""
        for day in v:
            if not 0 <= day <= 6:
                raise ValueError(f"Dia da semana inválido: {day}. Use 0-6 (seg-dom)")
        return v


class RecurringConfig(BaseModel):
    """Configuração de atividades recorrentes."""

    enabled: bool = True
    templates: list[RecurringTemplateConfig] = Field(default_factory=list)


class GitRepositoryConfig(BaseModel):
    """Configuração de um repositório Git."""

    name: str
    project: Optional[str] = None
    area_path: str
    tags: list[str] = Field(default_factory=list)


class GitConfig(BaseModel):
    """Configuração da fonte Git."""

    enabled: bool = True
    repositories: list[GitRepositoryConfig] = Field(default_factory=list)


class SourcesConfig(BaseModel):
    """Configuração de todas as fontes."""

    outlook: Optional[OutlookConfig] = None
    recurring: Optional[RecurringConfig] = None
    git: Optional[GitConfig] = None


class LLMConfig(BaseModel):
    """Configuração do cliente LLM (OpenAI-compatible)."""

    base_url: str
    model: str = "llama3.1"


class AppConfig(BaseModel):
    """Configuração principal da aplicação."""

    azure_devops: AzureDevOpsConfig
    sources: SourcesConfig
    non_working_days: list[str] = Field(default_factory=list)
    llm: Optional[LLMConfig] = None


class Settings:
    """Gerenciador de configurações e variáveis de ambiente."""

    def __init__(self, config_path: Optional[Path] = None, env_path: Optional[Path] = None):
        """Inicializa as configurações.

        Args:
            config_path: Caminho para o arquivo config.yaml
            env_path: Caminho para o arquivo .env
        """
        self._config_path = config_path or Path("config.yaml")
        self._env_path = env_path or Path(".env")
        self._config: Optional[AppConfig] = None

        # Carregar variáveis de ambiente
        if self._env_path.exists():
            load_dotenv(self._env_path)

    @property
    def azure_devops_pat(self) -> str:
        """Retorna o PAT do Azure DevOps."""
        pat = os.getenv("AZURE_DEVOPS_PAT")
        if not pat:
            raise ValueError("AZURE_DEVOPS_PAT não configurado no .env")
        return pat

    @property
    def graph_tenant_id(self) -> Optional[str]:
        """Retorna o tenant ID do Microsoft Graph."""
        return os.getenv("GRAPH_TENANT_ID")

    @property
    def graph_client_id(self) -> Optional[str]:
        """Retorna o client ID do Microsoft Graph."""
        return os.getenv("GRAPH_CLIENT_ID")

    @property
    def graph_client_secret(self) -> Optional[str]:
        """Retorna o client secret do Microsoft Graph."""
        return os.getenv("GRAPH_CLIENT_SECRET")

    @property
    def llm_api_key(self) -> str:
        """Retorna a API key do LLM (padrão 'ollama' para instâncias locais)."""
        return os.getenv("LLM_API_KEY", "ollama")

    @property
    def config(self) -> AppConfig:
        """Retorna a configuração carregada do YAML."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> AppConfig:
        """Carrega e valida o arquivo config.yaml."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Arquivo de configuração não encontrado: {self._config_path}")

        with open(self._config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Expande variáveis de ambiente antes da validação pelo Pydantic
        data = expand_env_vars(data)

        return AppConfig.model_validate(data)

    def reload(self) -> None:
        """Recarrega as configurações."""
        self._config = None
        if self._env_path.exists():
            load_dotenv(self._env_path, override=True)


# Instância global de configurações
_settings: Optional[Settings] = None


def get_settings(config_path: Optional[Path] = None, env_path: Optional[Path] = None) -> Settings:
    """Retorna a instância de configurações.

    Args:
        config_path: Caminho para o arquivo config.yaml
        env_path: Caminho para o arquivo .env

    Returns:
        Instância de Settings
    """
    global _settings
    if _settings is None or config_path is not None or env_path is not None:
        _settings = Settings(config_path, env_path)
    return _settings
