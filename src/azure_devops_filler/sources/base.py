"""Interface base para coletores de atividades."""

from abc import ABC, abstractmethod
from datetime import date

from ..models import Activity, SourceType


class BaseSource(ABC):
    """Interface abstrata para coletores de atividades."""

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Retorna o tipo da fonte."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Retorna o nome da fonte."""
        pass

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Retorna se a fonte está habilitada."""
        pass

    @abstractmethod
    async def collect(self, target_date: date) -> list[Activity]:
        """Coleta atividades para uma data específica.

        Args:
            target_date: Data para coletar atividades

        Returns:
            Lista de atividades coletadas
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Testa a conexão com a fonte.

        Returns:
            True se a conexão foi bem sucedida
        """
        pass
