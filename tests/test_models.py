"""Testes para os modelos de dados."""

from datetime import date, datetime, timedelta, timezone

import pytest

from azure_devops_filler.models import (
    Activity,
    CalendarEvent,
    Commit,
    RecurringTemplate,
    SourceType,
    TaskConfig,
    UserStoryConfig,
)


class TestActivityToDict:
    def test_required_fields(self):
        activity = Activity(
            title="Reunião",
            source=SourceType.OUTLOOK,
            date=date(2026, 2, 19),
            hours=1.0,
        )
        d = activity.to_dict()
        assert d["title"] == "Reunião"
        assert d["source"] == "outlook"
        assert d["date"] == "2026-02-19"
        assert d["hours"] == 1.0

    def test_optional_fields_default_to_none(self):
        activity = Activity(
            title="Reunião",
            source=SourceType.OUTLOOK,
            date=date(2026, 2, 19),
            hours=1.0,
        )
        d = activity.to_dict()
        assert d["description"] is None
        assert d["area_path"] is None
        assert d["iteration_path"] is None
        assert d["tags"] == []
        assert d["activity_datetime"] is None

    def test_source_serialized_as_string(self):
        for source, expected in [
            (SourceType.OUTLOOK, "outlook"),
            (SourceType.GIT, "git"),
            (SourceType.RECURRING, "recurring"),
        ]:
            activity = Activity(title="X", source=source, date=date(2026, 2, 19), hours=1.0)
            assert activity.to_dict()["source"] == expected

    def test_activity_datetime_serialized_as_isoformat(self):
        dt = datetime(2026, 2, 19, 13, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
        activity = Activity(
            title="Reunião",
            source=SourceType.OUTLOOK,
            date=date(2026, 2, 19),
            hours=1.0,
            activity_datetime=dt,
        )
        d = activity.to_dict()
        assert d["activity_datetime"] == dt.isoformat()

    def test_tags_list_preserved(self):
        activity = Activity(
            title="Reunião",
            source=SourceType.OUTLOOK,
            date=date(2026, 2, 19),
            hours=1.0,
            tags=["outlook", "reunião"],
        )
        assert activity.to_dict()["tags"] == ["outlook", "reunião"]


class TestTaskConfigToJsonPatch:
    def _make_task(self, **kwargs):
        defaults = dict(
            title="Minha Task",
            project="AI",
            area_path="AI",
            iteration_path="AI\\Iteration 3",
            completed_work=1.0,
        )
        defaults.update(kwargs)
        return TaskConfig(**defaults)

    def _get_value(self, ops, path):
        op = next((o for o in ops if o["path"] == path), None)
        return op["value"] if op else None

    def test_required_fields_always_present(self):
        task = self._make_task()
        ops = task.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/System.Title" in paths
        assert "/fields/System.AreaPath" in paths
        assert "/fields/System.IterationPath" in paths
        assert "/fields/Microsoft.VSTS.Scheduling.CompletedWork" in paths

    def test_correct_values_for_required_fields(self):
        task = self._make_task(title="Verificação Hive", completed_work=0.5)
        ops = task.to_json_patch()
        assert self._get_value(ops, "/fields/System.Title") == "Verificação Hive"
        assert self._get_value(ops, "/fields/Microsoft.VSTS.Scheduling.CompletedWork") == 0.5

    def test_state_included_by_default(self):
        task = self._make_task(state="Fechado")
        ops = task.to_json_patch()
        assert self._get_value(ops, "/fields/System.State") == "Fechado"

    def test_state_excluded_when_include_state_false(self):
        task = self._make_task(state="Fechado")
        ops = task.to_json_patch(include_state=False)
        paths = [op["path"] for op in ops]
        assert "/fields/System.State" not in paths

    def test_no_state_op_when_state_is_none(self):
        task = self._make_task()
        ops = task.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/System.State" not in paths

    def test_tags_joined_with_semicolon(self):
        task = self._make_task(tags=["git", "desenvolvimento"])
        ops = task.to_json_patch()
        assert self._get_value(ops, "/fields/System.Tags") == "git;desenvolvimento"

    def test_description_wrapped_in_div(self):
        task = self._make_task(description="Texto descritivo")
        ops = task.to_json_patch()
        assert self._get_value(ops, "/fields/System.Description") == "<div>Texto descritivo</div>"

    def test_no_description_op_when_none(self):
        task = self._make_task()
        ops = task.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/System.Description" not in paths

    def test_activity_datetime_sets_start_and_finish(self):
        dt = datetime(2026, 2, 19, 13, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
        task = self._make_task(activity_datetime=dt)
        ops = task.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/Microsoft.VSTS.Scheduling.StartDate" in paths
        assert "/fields/Microsoft.VSTS.Scheduling.FinishDate" in paths
        assert self._get_value(ops, "/fields/Microsoft.VSTS.Scheduling.StartDate") == dt.isoformat()

    def test_parent_id_not_in_json_patch(self):
        """Relação de pai é adicionada via PATCH separado no cliente, não na criação."""
        task = self._make_task(parent_id=999)
        ops = task.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/System.Parent" not in paths
        assert not any("relations" in p.lower() for p in paths)

    def test_all_ops_have_add_operation(self):
        task = self._make_task(state="Fechado", tags=["tag"], description="desc")
        ops = task.to_json_patch()
        assert all(op["op"] == "add" for op in ops)


class TestUserStoryConfigToJsonPatch:
    def _make_us(self, **kwargs):
        defaults = dict(
            title="Atividades Fevereiro 2026",
            project="AI",
            area_path="AI",
            iteration_path="AI\\Iteration 3",
        )
        defaults.update(kwargs)
        return UserStoryConfig(**defaults)

    def test_required_fields_present(self):
        us = self._make_us()
        ops = us.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/System.Title" in paths
        assert "/fields/System.AreaPath" in paths
        assert "/fields/System.IterationPath" in paths

    def test_no_completed_work_field(self):
        """User Story não tem campo CompletedWork."""
        us = self._make_us()
        ops = us.to_json_patch()
        paths = [op["path"] for op in ops]
        assert "/fields/Microsoft.VSTS.Scheduling.CompletedWork" not in paths

    def test_state_excluded_when_include_state_false(self):
        us = self._make_us(state="Fechado")
        ops = us.to_json_patch(include_state=False)
        paths = [op["path"] for op in ops]
        assert "/fields/System.State" not in paths

    def test_state_included_when_include_state_true(self):
        us = self._make_us(state="Fechado")
        ops = us.to_json_patch(include_state=True)
        paths = [op["path"] for op in ops]
        assert "/fields/System.State" in paths


class TestCalendarEventDuration:
    def test_one_hour_event(self):
        start = datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 11, 0, tzinfo=timezone.utc)
        event = CalendarEvent(subject="Reunião", start=start, end=end)
        assert event.duration_hours == 1.0

    def test_half_hour_event(self):
        start = datetime(2026, 2, 19, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 10, 30, tzinfo=timezone.utc)
        event = CalendarEvent(subject="Stand-up", start=start, end=end)
        assert event.duration_hours == 0.5

    def test_ninety_minute_event(self):
        start = datetime(2026, 2, 19, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 10, 30, tzinfo=timezone.utc)
        event = CalendarEvent(subject="Workshop", start=start, end=end)
        assert event.duration_hours == 1.5

    def test_two_hour_event(self):
        start = datetime(2026, 2, 19, 14, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 16, 0, tzinfo=timezone.utc)
        event = CalendarEvent(subject="Planejamento", start=start, end=end)
        assert event.duration_hours == 2.0


class TestCommitShortId:
    def test_short_id_is_7_characters(self):
        commit = Commit(
            commit_id="abc1234567890abcdef",
            message="fix: corrige bug",
            author="user@example.com",
            date=datetime(2026, 2, 19, tzinfo=timezone.utc),
            repository="arrecadacao-ai",
        )
        assert commit.short_id == "abc1234"
        assert len(commit.short_id) == 7

    def test_short_id_is_prefix_of_full_id(self):
        commit = Commit(
            commit_id="deadbeef1234567",
            message="feat: nova feature",
            author="user@example.com",
            date=datetime(2026, 2, 19, tzinfo=timezone.utc),
            repository="repo",
        )
        assert commit.commit_id.startswith(commit.short_id)


class TestRecurringTemplateAppliesToDate:
    def test_applies_on_configured_weekday(self):
        # 2026-02-19 é quinta-feira (weekday=3)
        template = RecurringTemplate(
            name="Verificação", weekdays=[0, 1, 2, 3, 4], hours=0.5, area_path="AI"
        )
        assert template.applies_to_date(date(2026, 2, 19)) is True

    def test_does_not_apply_on_saturday(self):
        template = RecurringTemplate(
            name="Verificação", weekdays=[0, 1, 2, 3, 4], hours=0.5, area_path="AI"
        )
        # 2026-02-21 é sábado (weekday=5)
        assert template.applies_to_date(date(2026, 2, 21)) is False

    def test_does_not_apply_on_sunday(self):
        template = RecurringTemplate(
            name="Verificação", weekdays=[0, 1, 2, 3, 4], hours=0.5, area_path="AI"
        )
        # 2026-02-22 é domingo (weekday=6)
        assert template.applies_to_date(date(2026, 2, 22)) is False

    def test_applies_only_on_specified_day(self):
        # Template apenas para segunda-feira (weekday=0)
        template = RecurringTemplate(
            name="Stand-up semanal", weekdays=[0], hours=1.0, area_path="AI"
        )
        monday = date(2026, 2, 23)   # segunda
        tuesday = date(2026, 2, 24)  # terça
        assert template.applies_to_date(monday) is True
        assert template.applies_to_date(tuesday) is False

    def test_applies_to_multiple_days(self):
        # Template para segunda (0) e quarta (2)
        template = RecurringTemplate(
            name="Reunião", weekdays=[0, 2], hours=1.0, area_path="AI"
        )
        monday = date(2026, 2, 23)     # segunda
        wednesday = date(2026, 2, 25)  # quarta
        tuesday = date(2026, 2, 24)    # terça
        assert template.applies_to_date(monday) is True
        assert template.applies_to_date(wednesday) is True
        assert template.applies_to_date(tuesday) is False
