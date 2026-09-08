from azure.search.documents.indexes.models import IndexingParameters, IndexingParametersConfiguration, SearchIndexer

from app.config import Settings, get_settings
from setup.client import get_indexer_client


def build_indexer(settings: Settings) -> SearchIndexer:
    return SearchIndexer(
        name=settings.indexer_name,
        description="Index retail PDF documents from blob storage",
        data_source_name=settings.datasource_name,
        target_index_name=settings.azure_search_index_name,
        skillset_name=settings.skillset_name,
        parameters=IndexingParameters(
            configuration=IndexingParametersConfiguration(
                parsing_mode="default",
                data_to_extract="contentAndMetadata",
            )
        ),
    )


def create_indexer(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client = get_indexer_client(settings)
    indexer = build_indexer(settings)
    client.create_or_update_indexer(indexer)
    print(f"Indexer '{settings.indexer_name}' created or updated.")


if __name__ == "__main__":
    create_indexer()
