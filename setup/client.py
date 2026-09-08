from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient

from app.config import Settings, get_settings


def get_search_credential(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.azure_search_admin_key:
        return AzureKeyCredential(settings.azure_search_admin_key)
    if settings.azure_search_query_key:
        return AzureKeyCredential(settings.azure_search_query_key)
    return DefaultAzureCredential()


def get_index_client(settings: Settings | None = None) -> SearchIndexClient:
    settings = settings or get_settings()
    return SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=get_search_credential(settings),
    )


def get_indexer_client(settings: Settings | None = None) -> SearchIndexerClient:
    settings = settings or get_settings()
    return SearchIndexerClient(
        endpoint=settings.azure_search_endpoint,
        credential=get_search_credential(settings),
    )
