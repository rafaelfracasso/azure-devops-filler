"""Coletor de atividades recorrentes (templates)."""

from datetime import date, datetime, timezone, timedelta

from ..config import RecurringConfig
from ..models import Activity, RecurringTemplate, SourceType
from .base import BaseSource


class RecurringSource(BaseSource):
    """Coletor de atividades recorrentes baseado em templates."""

    def __init__(self, config: RecurringConfig, non_working_days: list[str] | None = None):
        """Inicializa o coletor.

        Args:
            config: Configuração de atividades recorrentes
            non_working_days: Lista de datas (YYYY-MM-DD) sem expediente
        """
        self._config = config
        self._non_working_days = set(non_working_days or [])
        self._templates = [
            RecurringTemplate(
                name=t.name,
                weekdays=t.weekdays,
                hours=t.hours,
                area_path=t.area_path,
                tags=list(t.tags),
            )
            for t in config.templates
        ]

    @property
    def source_type(self) -> SourceType:
        """Retorna o tipo da fonte."""
        return SourceType.RECURRING

    @property
    def name(self) -> str:
        """Retorna o nome da fonte."""
        return "Recorrentes"

    @property
    def enabled(self) -> bool:
        """Retorna se a fonte está habilitada."""
        return self._config.enabled

    async def collect(self, target_date: date) -> list[Activity]:
        """Coleta atividades recorrentes para uma data específica.

        Gera atividades baseadas nos templates configurados para
        dias úteis especificados.

        Args:
            target_date: Data para coletar atividades

        Returns:
            Lista de atividades coletadas
        """
        if target_date.isoformat() in self._non_working_days:
            return []

        tz_offset = timezone(timedelta(hours=-4))
        activity_datetime = datetime(target_date.year, target_date.month, target_date.day, 13, 0, 0, tzinfo=tz_offset)

        activities = []

        for template in self._templates:
            if template.applies_to_date(target_date):
                activities.append(
                    Activity(
                        title=template.name,
                        source=SourceType.RECURRING,
                        date=target_date,
                        hours=template.hours,
                        description=f"Atividade recorrente: {template.name}",
                        area_path=template.area_path,
                        tags=list(template.tags),
                        activity_datetime=activity_datetime,
                    )
                )

        return activities

    async def test_connection(self) -> bool:
        """Testa a conexão com a fonte.

        Retorna True se houver templates configurados.

        Returns:
            True se houver templates configurados
        """
        return len(self._templates) > 0

    def get_templates(self) -> list[RecurringTemplate]:
        """Retorna os templates configurados.

        Returns:
            Lista de templates
        """
        return self._templates.copy()
