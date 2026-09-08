from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from app.config import Settings, get_settings
from setup.client import get_index_client


def build_index(settings: Settings) -> SearchIndex:
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"},
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config",
            )
        ],
    )

    fields = [
        SearchField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
            analyzer_name="keyword",
        ),
        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="snippet", type=SearchFieldDataType.String),
        SearchField(
            name="text_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.embedding_dimensions,
            vector_search_profile_name="vector-profile",
        ),
        SimpleField(name="url", type=SearchFieldDataType.String, retrievable=True),
        SimpleField(name="filepath", type=SearchFieldDataType.String, retrievable=True),
    ]

    return SearchIndex(
        name=settings.azure_search_index_name,
        fields=fields,
        vector_search=vector_search,
    )


def create_index(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client = get_index_client(settings)
    index = build_index(settings)
    client.create_or_update_index(index)
    print(f"Index '{settings.azure_search_index_name}' created or updated.")


if __name__ == "__main__":
    create_index()
