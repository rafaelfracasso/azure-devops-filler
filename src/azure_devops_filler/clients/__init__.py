"""Clientes para APIs externas."""

from .azure_devops import AzureDevOpsClient
from .microsoft_graph import MicrosoftGraphClient

__all__ = ["AzureDevOpsClient", "MicrosoftGraphClient"]
