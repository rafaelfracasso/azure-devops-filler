"""Coletor de atividades do Outlook."""

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from ..clients.microsoft_graph import MicrosoftGraphClient
from ..config import OutlookConfig
from ..models import Activity, CalendarEvent, SourceType
from .base import BaseSource


class OutlookSource(BaseSource):
    """Coletor de atividades do Outlook (CSV ou Graph API)."""

    def __init__(
        self,
        config: OutlookConfig,
        graph_client: Optional[MicrosoftGraphClient] = None,
    ):
        """Inicializa o coletor.

        Args:
            config: Configuração do Outlook
            graph_client: Cliente do Microsoft Graph (para API)
        """
        self._config = config
        self._graph_client = graph_client

    @property
    def source_type(self) -> SourceType:
        """Retorna o tipo da fonte."""
        return SourceType.OUTLOOK

    @property
    def name(self) -> str:
        """Retorna o nome da fonte."""
        return "Outlook"

    @property
    def enabled(self) -> bool:
        """Retorna se a fonte está habilitada."""
        return self._config.enabled

    async def collect(self, target_date: date) -> list[Activity]:
        """Coleta atividades do Outlook para uma data específica.

        Args:
            target_date: Data para coletar atividades

        Returns:
            Lista de atividades coletadas
        """
        if self._config.type == "csv":
            return await self._collect_from_csv(target_date)
        elif self._config.type == "ics":
            return await self._collect_from_ics(target_date)
        elif self._config.type == "graph_api":
            return await self._collect_from_graph(target_date)
        else:
            raise ValueError(f"Tipo de fonte Outlook não suportado: {self._config.type}")

    async def _collect_from_csv(self, target_date: date) -> list[Activity]:
        """Coleta atividades de um arquivo CSV.

        Args:
            target_date: Data para filtrar eventos

        Returns:
            Lista de atividades
        """
        if not self._config.csv_path:
            raise ValueError("Caminho do CSV não configurado")

        csv_path = Path(self._config.csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

        activities = []
        events = self._parse_csv(csv_path)

        for event in events:
            event_date = event.start.date()
            if event_date == target_date:
                activities.append(
                    Activity(
                        title=event.subject,
                        source=SourceType.OUTLOOK,
                        date=event_date,
                        hours=event.duration_hours,
                        description=event.body,
                        area_path=self._config.mapping.area_path,
                        tags=list(self._config.mapping.tags),
                        activity_datetime=event.start,
                    )
                )

        return activities

    def _parse_csv(self, csv_path: Path) -> list[CalendarEvent]:
        """Parseia um arquivo CSV exportado do Outlook.

        Args:
            csv_path: Caminho do arquivo CSV

        Returns:
            Lista de eventos do calendário
        """
        events = []

        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Tenta diferentes formatos de colunas do Outlook
                subject = row.get("Subject") or row.get("Assunto") or ""
                start_str = row.get("Start Date") or row.get("Data de Início") or ""
                start_time = row.get("Start Time") or row.get("Hora de Início") or "00:00:00"
                end_str = row.get("End Date") or row.get("Data de Término") or ""
                end_time = row.get("End Time") or row.get("Hora de Término") or "00:00:00"
                categories = row.get("Categories") or row.get("Categorias") or ""

                if not subject or not start_str:
                    continue

                try:
                    start = self._parse_datetime(start_str, start_time)
                    end = self._parse_datetime(end_str or start_str, end_time)

                    events.append(
                        CalendarEvent(
                            subject=subject,
                            start=start,
                            end=end,
                            categories=[c.strip() for c in categories.split(";") if c.strip()],
                        )
                    )
                except ValueError:
                    continue

        return events

    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """Parseia data e hora separados.

        Args:
            date_str: String de data
            time_str: String de hora

        Returns:
            Objeto datetime
        """
        # Tenta diferentes formatos de data
        date_formats = [
            "%m/%d/%Y",  # US format
            "%d/%m/%Y",  # BR format
            "%Y-%m-%d",  # ISO format
        ]

        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue

        if parsed_date is None:
            raise ValueError(f"Formato de data não reconhecido: {date_str}")

        # Tenta diferentes formatos de hora
        time_formats = [
            "%H:%M:%S",
            "%H:%M",
            "%I:%M:%S %p",
            "%I:%M %p",
        ]

        parsed_time = None
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_str, fmt).time()
                break
            except ValueError:
                continue

        if parsed_time is None:
            from datetime import time as time_class

            parsed_time = time_class(0, 0, 0)

        return datetime.combine(parsed_date, parsed_time)

    async def _collect_from_ics(self, target_date: date) -> list[Activity]:
        """Coleta atividades de um arquivo ICS (iCalendar).

        Args:
            target_date: Data para filtrar eventos

        Returns:
            Lista de atividades
        """
        from icalendar import Calendar

        if not self._config.ics_path:
            raise ValueError("Caminho do ICS não configurado")

        ics_path = Path(self._config.ics_path)
        if not ics_path.exists():
            raise FileNotFoundError(f"Arquivo ICS não encontrado: {ics_path}")

        with open(ics_path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        activities = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            dtstart = component.get("DTSTART")
            dtend = component.get("DTEND")
            summary = str(component.get("SUMMARY", ""))

            if not dtstart or not summary:
                continue

            start_val = dtstart.dt
            end_val = dtend.dt if dtend else start_val

            # Normaliza para datetime (eventos all-day chegam como date)
            if isinstance(start_val, date) and not isinstance(start_val, datetime):
                if start_val != target_date:
                    continue
                start_dt = datetime.combine(start_val, datetime.min.time())
                end_dt = datetime.combine(end_val if isinstance(end_val, date) else end_val.date(), datetime.min.time())
            else:
                # Remove timezone para comparar com date
                start_naive = start_val.replace(tzinfo=None) if start_val.tzinfo else start_val
                if start_naive.date() != target_date:
                    continue
                start_dt = start_naive
                end_naive = end_val.replace(tzinfo=None) if end_val.tzinfo else end_val
                end_dt = end_naive

            duration = (end_dt - start_dt).total_seconds() / 3600
            hours = round(max(0.25, duration), 2)

            description = str(component.get("DESCRIPTION", "") or "").strip() or None

            activities.append(
                Activity(
                    title=summary,
                    source=SourceType.OUTLOOK,
                    date=target_date,
                    hours=hours,
                    description=description,
                    area_path=self._config.mapping.area_path,
                    tags=list(self._config.mapping.tags),
                )
            )

        return activities

    async def _collect_from_graph(self, target_date: date) -> list[Activity]:
        """Coleta atividades da Microsoft Graph API.

        Args:
            target_date: Data para filtrar eventos

        Returns:
            Lista de atividades
        """
        if not self._graph_client:
            raise ValueError("Cliente Microsoft Graph não configurado")

        if not self._config.user_email:
            raise ValueError("Email do usuário não configurado para Graph API")

        events = await self._graph_client.get_calendar_events(
            user_email=self._config.user_email,
            from_date=target_date,
            to_date=target_date,
        )

        activities = []
        for event in events:
            activities.append(
                Activity(
                    title=event.subject,
                    source=SourceType.OUTLOOK,
                    date=target_date,
                    hours=event.duration_hours,
                    description=event.body,
                    area_path=self._config.mapping.area_path,
                    tags=list(self._config.mapping.tags),
                    activity_datetime=event.start,
                )
            )

        return activities

    async def test_connection(self) -> bool:
        """Testa a conexão com a fonte.

        Returns:
            True se a conexão foi bem sucedida
        """
        if self._config.type == "csv":
            if not self._config.csv_path:
                return False
            return Path(self._config.csv_path).exists()
        elif self._config.type == "ics":
            if not self._config.ics_path:
                return False
            return Path(self._config.ics_path).exists()
        elif self._config.type == "graph_api":
            if not self._graph_client:
                return False
            return await self._graph_client.test_connection()
        return False
