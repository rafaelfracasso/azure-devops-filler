"""Testes para o controle de duplicatas (dedup)."""

import json
from datetime import date
from pathlib import Path

import pytest

from azure_devops_filler.dedup import (
    DedupManager,
    generate_hash,
    generate_user_story_hash,
    normalize_text,
)
from azure_devops_filler.models import Activity, SourceType


class TestNormalizeText:
    def test_removes_accents(self):
        assert normalize_text("verificação") == "verificacao"
        assert normalize_text("reunião") == "reuniao"
        assert normalize_text("atividade") == "atividade"

    def test_converts_to_lowercase(self):
        assert normalize_text("Reunião de PLANEJAMENTO") == "reuniao de planejamento"

    def test_trims_extra_spaces(self):
        assert normalize_text("  texto   com   espaços  ") == "texto com espacos"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_no_change_for_plain_ascii(self):
        assert normalize_text("hello world") == "hello world"

    def test_removes_cedilla(self):
        assert normalize_text("verificação de carga") == "verificacao de carga"

    def test_removes_tilde(self):
        assert normalize_text("manutenção") == "manutencao"


class TestGenerateHash:
    def test_deterministic(self):
        h1 = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        h2 = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        assert h1 == h2

    def test_different_sources_produce_different_hashes(self):
        h_outlook = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        h_git = generate_hash(SourceType.GIT, "Reunião", date(2026, 2, 19))
        h_recurring = generate_hash(SourceType.RECURRING, "Reunião", date(2026, 2, 19))
        assert h_outlook != h_git
        assert h_outlook != h_recurring
        assert h_git != h_recurring

    def test_different_dates_produce_different_hashes(self):
        h1 = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        h2 = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 20))
        assert h1 != h2

    def test_accent_insensitive(self):
        """Hash com e sem acento deve ser igual (normalização)."""
        h_with_accent = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        h_without_accent = generate_hash(SourceType.OUTLOOK, "Reuniao", date(2026, 2, 19))
        assert h_with_accent == h_without_accent

    def test_case_insensitive(self):
        h_lower = generate_hash(SourceType.OUTLOOK, "reunião", date(2026, 2, 19))
        h_upper = generate_hash(SourceType.OUTLOOK, "REUNIÃO", date(2026, 2, 19))
        assert h_lower == h_upper

    def test_returns_sha256_hex_string(self):
        h = generate_hash(SourceType.OUTLOOK, "Reunião", date(2026, 2, 19))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_titles_produce_different_hashes(self):
        h1 = generate_hash(SourceType.RECURRING, "Verificação - Hive", date(2026, 2, 19))
        h2 = generate_hash(SourceType.RECURRING, "Verificação - DW", date(2026, 2, 19))
        assert h1 != h2


class TestGenerateUserStoryHash:
    def test_deterministic(self):
        h1 = generate_user_story_hash(2026, 2)
        h2 = generate_user_story_hash(2026, 2)
        assert h1 == h2

    def test_different_months_produce_different_hashes(self):
        h_jan = generate_user_story_hash(2026, 1)
        h_feb = generate_user_story_hash(2026, 2)
        assert h_jan != h_feb

    def test_different_years_produce_different_hashes(self):
        h_2025 = generate_user_story_hash(2025, 12)
        h_2026 = generate_user_story_hash(2026, 12)
        assert h_2025 != h_2026

    def test_month_zero_padded(self):
        """Mês 1 e mês 10 não devem colidir."""
        h1 = generate_user_story_hash(2026, 1)
        h10 = generate_user_story_hash(2026, 10)
        assert h1 != h10

    def test_returns_sha256_hex_string(self):
        h = generate_user_story_hash(2026, 2)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestDedupManager:
    @pytest.fixture
    def dedup(self, tmp_path):
        return DedupManager(storage_path=tmp_path / "processed.json")

    @pytest.fixture
    def activity(self):
        return Activity(
            title="Reunião de planejamento",
            source=SourceType.OUTLOOK,
            date=date(2026, 2, 19),
            hours=1.5,
        )

    # --- is_processed / mark_processed ---

    def test_new_activity_not_processed(self, dedup, activity):
        assert dedup.is_processed(activity) is False

    def test_mark_processed_makes_activity_processed(self, dedup, activity):
        dedup.mark_processed(activity, task_id=1001, task_url="https://example.com/1001")
        assert dedup.is_processed(activity) is True

    def test_mark_processed_returns_hash(self, dedup, activity):
        h = dedup.mark_processed(activity)
        assert len(h) == 64

    def test_mark_processed_persists_to_file(self, dedup, activity, tmp_path):
        dedup.mark_processed(activity)
        dedup2 = DedupManager(storage_path=tmp_path / "processed.json")
        assert dedup2.is_processed(activity) is True

    def test_same_title_different_date_not_duplicate(self, dedup):
        a1 = Activity(title="Reunião", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=1.0)
        a2 = Activity(title="Reunião", source=SourceType.OUTLOOK, date=date(2026, 2, 20), hours=1.0)
        dedup.mark_processed(a1)
        assert dedup.is_processed(a2) is False

    def test_same_title_different_source_not_duplicate(self, dedup):
        a1 = Activity(title="Stand-up", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=0.5)
        a2 = Activity(title="Stand-up", source=SourceType.RECURRING, date=date(2026, 2, 19), hours=0.5)
        dedup.mark_processed(a1)
        assert dedup.is_processed(a2) is False

    def test_accent_insensitive_dedup(self, dedup):
        """Mesma atividade com e sem acento deve ser considerada duplicata."""
        a1 = Activity(title="Verificação", source=SourceType.RECURRING, date=date(2026, 2, 19), hours=0.5)
        a2 = Activity(title="Verificacao", source=SourceType.RECURRING, date=date(2026, 2, 19), hours=0.5)
        dedup.mark_processed(a1)
        assert dedup.is_processed(a2) is True

    # --- Arquivo vazio / inexistente ---

    def test_nonexistent_file_loads_empty_state(self, tmp_path):
        dedup = DedupManager(storage_path=tmp_path / "nonexistent.json")
        assert dedup.is_processed(
            Activity(title="X", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=1.0)
        ) is False

    def test_empty_file_loads_empty_state(self, tmp_path):
        empty = tmp_path / "processed.json"
        empty.write_text("")
        dedup = DedupManager(storage_path=empty)
        assert dedup.get_stats()["total"] == 0

    def test_migration_adds_user_stories_to_old_format(self, tmp_path):
        """Arquivo sem seção user_stories deve ser migrado sem erro."""
        old_file = tmp_path / "processed.json"
        old_file.write_text(json.dumps({"processed": {}}))
        dedup = DedupManager(storage_path=old_file)
        assert dedup.is_user_story_processed(2026, 2) is False

    # --- User Stories ---

    def test_user_story_not_processed_initially(self, dedup):
        assert dedup.is_user_story_processed(2026, 2) is False

    def test_mark_user_story_processed(self, dedup):
        dedup.mark_user_story_processed(2026, 2, user_story_id=500, user_story_url="https://example.com/500")
        assert dedup.is_user_story_processed(2026, 2) is True

    def test_get_user_story_id_returns_correct_id(self, dedup):
        dedup.mark_user_story_processed(2026, 2, user_story_id=500, user_story_url="https://example.com/500")
        assert dedup.get_user_story_id(2026, 2) == 500

    def test_get_user_story_id_returns_none_when_not_found(self, dedup):
        assert dedup.get_user_story_id(2026, 2) is None

    def test_user_story_months_are_independent(self, dedup):
        dedup.mark_user_story_processed(2026, 1, user_story_id=100, user_story_url="https://example.com/100")
        assert dedup.is_user_story_processed(2026, 2) is False

    def test_user_story_persists_to_file(self, dedup, tmp_path):
        dedup.mark_user_story_processed(2026, 2, user_story_id=500, user_story_url="https://example.com/500")
        dedup2 = DedupManager(storage_path=tmp_path / "processed.json")
        assert dedup2.get_user_story_id(2026, 2) == 500

    # --- get_stats ---

    def test_get_stats_empty(self, dedup):
        stats = dedup.get_stats()
        assert stats["total"] == 0
        assert stats["by_source"] == {}

    def test_get_stats_counts_by_source(self, dedup):
        dedup.mark_processed(Activity(title="A", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=1.0))
        dedup.mark_processed(Activity(title="B", source=SourceType.OUTLOOK, date=date(2026, 2, 20), hours=1.0))
        dedup.mark_processed(Activity(title="C", source=SourceType.GIT, date=date(2026, 2, 19), hours=0.5))
        dedup.mark_processed(Activity(title="D", source=SourceType.RECURRING, date=date(2026, 2, 19), hours=0.5))

        stats = dedup.get_stats()
        assert stats["total"] == 4
        assert stats["by_source"]["outlook"] == 2
        assert stats["by_source"]["git"] == 1
        assert stats["by_source"]["recurring"] == 1

    # --- clear / remove ---

    def test_clear_removes_all_processed(self, dedup):
        dedup.mark_processed(Activity(title="A", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=1.0))
        dedup.mark_processed(Activity(title="B", source=SourceType.GIT, date=date(2026, 2, 19), hours=0.5))
        count = dedup.clear()
        assert count == 2
        assert dedup.get_stats()["total"] == 0

    def test_clear_returns_zero_when_empty(self, dedup):
        assert dedup.clear() == 0

    def test_remove_specific_record(self, dedup, activity):
        h = dedup.mark_processed(activity)
        assert dedup.remove(h) is True
        assert dedup.is_processed(activity) is False

    def test_remove_nonexistent_returns_false(self, dedup):
        assert dedup.remove("nonexistent_hash_that_doesnt_exist") is False

    def test_remove_persists_to_file(self, dedup, activity, tmp_path):
        h = dedup.mark_processed(activity)
        dedup.remove(h)
        dedup2 = DedupManager(storage_path=tmp_path / "processed.json")
        assert dedup2.is_processed(activity) is False

    # --- remove_by_task_id ---

    def test_remove_by_task_id_returns_true_when_found(self, dedup, activity):
        dedup.mark_processed(activity, task_id=1001)
        assert dedup.remove_by_task_id(1001) is True

    def test_remove_by_task_id_removes_record(self, dedup, activity):
        dedup.mark_processed(activity, task_id=1001)
        dedup.remove_by_task_id(1001)
        assert dedup.is_processed(activity) is False

    def test_remove_by_task_id_returns_false_when_not_found(self, dedup):
        assert dedup.remove_by_task_id(9999) is False

    def test_remove_by_task_id_only_removes_matching_record(self, dedup):
        a1 = Activity(title="A", source=SourceType.OUTLOOK, date=date(2026, 2, 19), hours=1.0)
        a2 = Activity(title="B", source=SourceType.OUTLOOK, date=date(2026, 2, 20), hours=1.0)
        dedup.mark_processed(a1, task_id=1001)
        dedup.mark_processed(a2, task_id=1002)

        dedup.remove_by_task_id(1001)

        assert dedup.is_processed(a1) is False
        assert dedup.is_processed(a2) is True

    def test_remove_by_task_id_persists_to_file(self, dedup, activity, tmp_path):
        dedup.mark_processed(activity, task_id=1001)
        dedup.remove_by_task_id(1001)
        dedup2 = DedupManager(storage_path=tmp_path / "processed.json")
        assert dedup2.is_processed(activity) is False

    def test_remove_by_task_id_returns_false_when_no_task_id_stored(self, dedup, activity):
        """Atividade registrada sem task_id não deve ser encontrada por task_id."""
        dedup.mark_processed(activity, task_id=None)
        assert dedup.remove_by_task_id(1001) is False
