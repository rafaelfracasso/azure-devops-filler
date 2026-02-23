"""Testes para a fonte de atividades recorrentes."""

from datetime import date, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from azure_devops_filler.models import SourceType
from azure_devops_filler.sources.recurring import RecurringSource


def _make_template_config(name, weekdays, hours, area_path="AI", tags=None):
    t = MagicMock()
    t.name = name
    t.weekdays = weekdays
    t.hours = hours
    t.area_path = area_path
    t.tags = tags or []
    return t


def _make_config(templates=None, enabled=True):
    config = MagicMock()
    config.enabled = enabled
    config.templates = templates or []
    return config


@pytest.fixture
def weekday_template():
    return _make_template_config(
        name="Verificação de carga - Hive",
        weekdays=[0, 1, 2, 3, 4],
        hours=0.5,
        area_path="AI",
        tags=["qlik", "monitoramento"],
    )


@pytest.fixture
def source(weekday_template):
    config = _make_config(templates=[weekday_template])
    # 2026-02-16 é segunda-feira mas feriado (carnaval)
    return RecurringSource(config, non_working_days=["2026-02-16"])


class TestRecurringSourceCollect:
    async def test_collects_on_weekday(self, source):
        thursday = date(2026, 2, 19)  # quinta-feira
        activities = await source.collect(thursday)

        assert len(activities) == 1
        assert activities[0].title == "Verificação de carga - Hive"
        assert activities[0].source == SourceType.RECURRING
        assert activities[0].hours == 0.5
        assert activities[0].date == thursday

    async def test_empty_on_saturday(self, source):
        saturday = date(2026, 2, 21)
        assert await source.collect(saturday) == []

    async def test_empty_on_sunday(self, source):
        sunday = date(2026, 2, 22)
        assert await source.collect(sunday) == []

    async def test_empty_on_non_working_day(self, source):
        """Segunda-feira feriado deve retornar vazio."""
        non_working_monday = date(2026, 2, 16)
        assert await source.collect(non_working_monday) == []

    async def test_collects_on_non_holiday_monday(self):
        template = _make_template_config("Stand-up", [0, 1, 2, 3, 4], 0.5)
        config = _make_config(templates=[template])
        source = RecurringSource(config, non_working_days=[])

        monday = date(2026, 2, 23)  # segunda normal
        activities = await source.collect(monday)
        assert len(activities) == 1

    async def test_activity_datetime_is_13h_gmt_minus_4(self, source):
        thursday = date(2026, 2, 19)
        activities = await source.collect(thursday)

        dt = activities[0].activity_datetime
        assert dt is not None
        assert dt.hour == 13
        assert dt.minute == 0
        assert dt.utcoffset() == timedelta(hours=-4)

    async def test_activity_has_correct_area_path_and_tags(self, source):
        thursday = date(2026, 2, 19)
        activities = await source.collect(thursday)

        assert activities[0].area_path == "AI"
        assert activities[0].tags == ["qlik", "monitoramento"]

    async def test_activity_description_contains_template_name(self, source):
        thursday = date(2026, 2, 19)
        activities = await source.collect(thursday)

        assert "Verificação de carga - Hive" in activities[0].description

    async def test_multiple_templates_all_collected(self):
        t1 = _make_template_config("Template A", [0, 1, 2, 3, 4], 0.5)
        t2 = _make_template_config("Template B", [0, 1, 2, 3, 4], 1.0)
        config = _make_config(templates=[t1, t2])
        source = RecurringSource(config)

        thursday = date(2026, 2, 19)
        activities = await source.collect(thursday)

        assert len(activities) == 2
        titles = {a.title for a in activities}
        assert titles == {"Template A", "Template B"}

    async def test_template_not_applied_outside_its_weekdays(self):
        monday_only = _make_template_config("Reunião semanal", [0], 1.0)
        config = _make_config(templates=[monday_only])
        source = RecurringSource(config)

        thursday = date(2026, 2, 19)  # quinta
        assert await source.collect(thursday) == []

    async def test_partial_weekday_match(self):
        """Só alguns templates se aplicam em um dia específico."""
        every_day = _make_template_config("Diário", [0, 1, 2, 3, 4], 0.5)
        mondays_only = _make_template_config("Semanal", [0], 1.0)
        config = _make_config(templates=[every_day, mondays_only])
        source = RecurringSource(config)

        thursday = date(2026, 2, 19)  # quinta — só "Diário" se aplica
        activities = await source.collect(thursday)
        assert len(activities) == 1
        assert activities[0].title == "Diário"

        monday = date(2026, 2, 23)  # segunda — ambos se aplicam
        activities = await source.collect(monday)
        assert len(activities) == 2


class TestRecurringSourceTestConnection:
    async def test_returns_true_when_templates_configured(self, source):
        assert await source.test_connection() is True

    async def test_returns_false_when_no_templates(self):
        config = _make_config(templates=[])
        s = RecurringSource(config)
        assert await s.test_connection() is False


class TestRecurringSourceProperties:
    def test_source_type_is_recurring(self, source):
        assert source.source_type == SourceType.RECURRING

    def test_name_is_recurring(self, source):
        assert source.name == "Recurring"

    def test_enabled_reflects_config(self, weekday_template):
        enabled_config = _make_config(templates=[weekday_template], enabled=True)
        disabled_config = _make_config(templates=[weekday_template], enabled=False)

        assert RecurringSource(enabled_config).enabled is True
        assert RecurringSource(disabled_config).enabled is False

    def test_get_templates_returns_copy(self, source):
        templates = source.get_templates()
        assert len(templates) == 1
        # Modificar a lista retornada não afeta o source
        templates.clear()
        assert len(source.get_templates()) == 1
