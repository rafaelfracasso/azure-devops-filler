"""Modelos de dados para o Azure DevOps Activity Filler."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    """Tipos de fontes de atividades."""

    OUTLOOK = "outlook"
    RECURRING = "recurring"
    GIT = "git"


@dataclass
class Activity:
    """Representa uma atividade coletada de uma fonte."""

    title: str
    source: SourceType
    date: date
    hours: float
    description: Optional[str] = None
    area_path: Optional[str] = None
    iteration_path: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    activity_datetime: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Converte a atividade para dicionário."""
        return {
            "title": self.title,
            "source": self.source.value,
            "date": self.date.isoformat(),
            "hours": self.hours,
            "description": self.description,
            "area_path": self.area_path,
            "iteration_path": self.iteration_path,
            "tags": self.tags,
            "activity_datetime": self.activity_datetime.isoformat() if self.activity_datetime else None,
        }


@dataclass
class UserStoryConfig:
    """Configuração para criação de uma User Story no Azure DevOps."""

    title: str
    project: str
    area_path: str
    iteration_path: str
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    state: Optional[str] = None

    def to_json_patch(self, include_state: bool = True) -> list[dict]:
        """Converte para formato JSON Patch do Azure DevOps API."""
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": self.title},
            {"op": "add", "path": "/fields/System.AreaPath", "value": self.area_path},
            {"op": "add", "path": "/fields/System.IterationPath", "value": self.iteration_path},
        ]

        if self.description:
            operations.append({"op": "add", "path": "/fields/System.Description", "value": f"<div>{self.description}</div>"})

        if self.tags:
            operations.append({"op": "add", "path": "/fields/System.Tags", "value": ";".join(self.tags)})

        if self.assigned_to:
            operations.append({"op": "add", "path": "/fields/System.AssignedTo", "value": self.assigned_to})

        if self.state and include_state:
            operations.append({"op": "add", "path": "/fields/System.State", "value": self.state})

        return operations


@dataclass
class TaskConfig:
    """Configuração para criação de uma Task no Azure DevOps."""

    title: str
    project: str
    area_path: str
    iteration_path: str
    completed_work: float
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    state: Optional[str] = None
    activity_datetime: Optional[datetime] = None
    parent_id: Optional[int] = None

    def to_json_patch(self, include_state: bool = True) -> list[dict]:
        """Converte para formato JSON Patch do Azure DevOps API."""
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": self.title},
            {"op": "add", "path": "/fields/System.AreaPath", "value": self.area_path},
            {
                "op": "add",
                "path": "/fields/System.IterationPath",
                "value": self.iteration_path,
            },
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
                "value": self.completed_work,
            },
        ]

        if self.description:
            operations.append(
                {
                    "op": "add",
                    "path": "/fields/System.Description",
                    "value": f"<div>{self.description}</div>",
                }
            )

        if self.tags:
            operations.append(
                {
                    "op": "add",
                    "path": "/fields/System.Tags",
                    "value": ";".join(self.tags),
                }
            )

        if self.assigned_to:
            operations.append(
                {
                    "op": "add",
                    "path": "/fields/System.AssignedTo",
                    "value": self.assigned_to,
                }
            )

        if self.state and include_state:
            operations.append(
                {
                    "op": "add",
                    "path": "/fields/System.State",
                    "value": self.state,
                }
            )

        if self.activity_datetime:
            dt_str = self.activity_datetime.isoformat()
            operations.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StartDate", "value": dt_str})
            operations.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.FinishDate", "value": dt_str})
            operations.append({"op": "add", "path": "/fields/Custom.6efe7342-7546-4011-b66d-6eb1dfab8e46", "value": dt_str})

        return operations


@dataclass
class Commit:
    """Representa um commit do Git."""

    commit_id: str
    message: str
    author: str
    date: datetime
    repository: str

    @property
    def short_id(self) -> str:
        """Retorna os primeiros 7 caracteres do commit ID."""
        return self.commit_id[:7]


@dataclass
class CalendarEvent:
    """Representa um evento do calendário."""

    subject: str
    start: datetime
    end: datetime
    body: Optional[str] = None
    categories: list[str] = field(default_factory=list)

    @property
    def duration_hours(self) -> float:
        """Calcula a duração do evento em horas."""
        delta = self.end - self.start
        return delta.total_seconds() / 3600


@dataclass
class RecurringTemplate:
    """Template para atividades recorrentes."""

    name: str
    weekdays: list[int]  # 0=segunda, 6=domingo
    hours: float
    area_path: str
    tags: list[str] = field(default_factory=list)

    def applies_to_date(self, target_date: date) -> bool:
        """Verifica se o template se aplica a uma data específica."""
        # weekday() retorna 0=segunda, 6=domingo
        return target_date.weekday() in self.weekdays


@dataclass
class CreatedTask:
    """Resultado da criação de uma Task no Azure DevOps."""

    id: int
    url: str
    title: str
    project: str


@dataclass
class CreatedUserStory:
    """Resultado da criação de uma User Story no Azure DevOps."""

    id: int
    url: str
    title: str
    project: str
