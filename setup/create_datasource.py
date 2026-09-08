from azure.search.documents.indexes.models import SearchIndexerDataContainer, SearchIndexerDataSourceConnection

from app.config import Settings, get_settings
from setup.client import get_indexer_client


def build_datasource(settings: Settings) -> SearchIndexerDataSourceConnection:
    if not settings.azure_storage_connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required for datasource setup.")

    container = SearchIndexerDataContainer(name=settings.azure_storage_container)
    return SearchIndexerDataSourceConnection(
        name=settings.datasource_name,
        type="azureblob",
        connection_string=settings.azure_storage_connection_string,
        container=container,
        description="Retail PDF documents from blob storage",
    )


def create_datasource(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client = get_indexer_client(settings)
    datasource = build_datasource(settings)
    client.create_or_update_data_source_connection(datasource)
    print(f"Datasource '{settings.datasource_name}' created or updated.")


if __name__ == "__main__":
    create_datasource()
