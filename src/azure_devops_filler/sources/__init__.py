"""Coletores de atividades de diferentes fontes."""

from .base import BaseSource
from .outlook import OutlookSource
from .recurring import RecurringSource
from .git import GitSource

__all__ = ["BaseSource", "OutlookSource", "RecurringSource", "GitSource"]
