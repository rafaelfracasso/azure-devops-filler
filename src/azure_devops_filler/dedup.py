"""Controle de duplicatas de atividades."""

import hashlib
import json
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from .models import Activity, SourceType


def normalize_text(text: str) -> str:
    """Normaliza texto para comparação.

    Remove acentos, converte para minúsculas e remove espaços extras.

    Args:
        text: Texto a normalizar

    Returns:
        Texto normalizado
    """
    # Remove acentos
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))

    # Converte para minúsculas e remove espaços extras
    return " ".join(ascii_text.lower().split())


def generate_user_story_hash(year: int, month: int) -> str:
    """Gera um hash único para uma User Story mensal.

    Args:
        year: Ano
        month: Mês (1-12)

    Returns:
        Hash SHA256
    """
    content = f"user_story:{year}{month:02d}"
    return hashlib.sha256(content.encode()).hexdigest()


def generate_hash(source: SourceType, title: str, activity_date: date) -> str:
    """Gera um hash único para uma atividade.

    O hash é baseado na fonte, título normalizado e data.

    Args:
        source: Tipo da fonte
        title: Título da atividade
        activity_date: Data da atividade

    Returns:
        Hash SHA256 da atividade
    """
    normalized_title = normalize_text(title)
    date_str = activity_date.strftime("%Y%m%d")
    content = f"{source.value}:{normalized_title}:{date_str}"
    return hashlib.sha256(content.encode()).hexdigest()


class DedupManager:
    """Gerenciador de duplicatas de atividades."""

    def __init__(self, storage_path: Optional[Path] = None):
        """Inicializa o gerenciador.

        Args:
            storage_path: Caminho para o arquivo de armazenamento
        """
        self.storage_path = storage_path or Path("data/processed.json")
        self._data: Optional[dict] = None

    def _ensure_dir(self) -> None:
        """Garante que o diretório de armazenamento existe."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        """Carrega os dados do arquivo.

        Returns:
            Dicionário com os hashes processados
        """
        if self._data is not None:
            return self._data

        if not self.storage_path.exists() or self.storage_path.stat().st_size == 0:
            self._data = {"processed": {}, "user_stories": {}}
            return self._data

        with open(self.storage_path, encoding="utf-8") as f:
            self._data = json.load(f)

        # Migração: garante que a seção user_stories existe
        if "user_stories" not in self._data:
            self._data["user_stories"] = {}

        return self._data

    def _save(self) -> None:
        """Salva os dados no arquivo."""
        self._ensure_dir()
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def is_processed(self, activity: Activity) -> bool:
        """Verifica se uma atividade já foi processada.

        Args:
            activity: Atividade a verificar

        Returns:
            True se a atividade já foi processada
        """
        data = self._load()
        activity_hash = generate_hash(activity.source, activity.title, activity.date)
        return activity_hash in data["processed"]

    def mark_processed(
        self,
        activity: Activity,
        task_id: Optional[int] = None,
        task_url: Optional[str] = None,
    ) -> str:
        """Marca uma atividade como processada.

        Args:
            activity: Atividade a marcar
            task_id: ID da Task criada no Azure DevOps
            task_url: URL da Task criada

        Returns:
            Hash da atividade
        """
        data = self._load()
        activity_hash = generate_hash(activity.source, activity.title, activity.date)

        data["processed"][activity_hash] = {
            "source": activity.source.value,
            "title": activity.title,
            "date": activity.date.isoformat(),
            "task_id": task_id,
            "task_url": task_url,
            "processed_at": date.today().isoformat(),
        }

        self._save()
        return activity_hash

    def is_user_story_processed(self, year: int, month: int) -> bool:
        """Verifica se a User Story mensal já foi criada.

        Args:
            year: Ano
            month: Mês (1-12)

        Returns:
            True se a User Story já foi criada
        """
        data = self._load()
        us_hash = generate_user_story_hash(year, month)
        return us_hash in data["user_stories"]

    def mark_user_story_processed(self, year: int, month: int, user_story_id: int, user_story_url: str) -> None:
        """Marca uma User Story mensal como criada.

        Args:
            year: Ano
            month: Mês (1-12)
            user_story_id: ID da User Story no Azure DevOps
            user_story_url: URL da User Story
        """
        data = self._load()
        us_hash = generate_user_story_hash(year, month)
        data["user_stories"][us_hash] = {
            "year": year,
            "month": month,
            "user_story_id": user_story_id,
            "user_story_url": user_story_url,
            "created_at": date.today().isoformat(),
        }
        self._save()

    def get_user_story_id(self, year: int, month: int) -> Optional[int]:
        """Retorna o ID de uma User Story mensal já criada.

        Args:
            year: Ano
            month: Mês (1-12)

        Returns:
            ID da User Story ou None se não encontrada
        """
        data = self._load()
        us_hash = generate_user_story_hash(year, month)
        entry = data["user_stories"].get(us_hash)
        if entry:
            return entry["user_story_id"]
        return None

    def get_stats(self) -> dict:
        """Retorna estatísticas de processamento.

        Returns:
            Dicionário com estatísticas
        """
        data = self._load()
        processed = data["processed"]

        stats = {
            "total": len(processed),
            "by_source": {},
        }

        for entry in processed.values():
            source = entry["source"]
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

        return stats

    def clear(self) -> int:
        """Limpa todos os registros de processamento.

        Returns:
            Número de registros removidos
        """
        data = self._load()
        count = len(data["processed"])
        data["processed"] = {}
        self._save()
        return count

    def remove_by_task_id(self, task_id: int) -> bool:
        """Remove um registro de processamento pelo ID da Task no Azure DevOps.

        Args:
            task_id: ID da Task no Azure DevOps

        Returns:
            True se o registro foi encontrado e removido
        """
        data = self._load()
        for activity_hash, entry in list(data["processed"].items()):
            if entry.get("task_id") == task_id:
                del data["processed"][activity_hash]
                self._save()
                return True
        return False

    def remove(self, activity_hash: str) -> bool:
        """Remove um registro de processamento.

        Args:
            activity_hash: Hash da atividade a remover

        Returns:
            True se o registro foi removido
        """
        data = self._load()
        if activity_hash in data["processed"]:
            del data["processed"][activity_hash]
            self._save()
            return True
        return False
