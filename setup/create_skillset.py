from azure.search.documents.indexes.models import (
    AIServicesAccountKey,
    AzureOpenAIEmbeddingSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    SearchIndexerSkillset,
    SplitSkill,
)

from app.config import Settings, get_settings
from setup.client import get_indexer_client


def build_skillset(settings: Settings) -> SearchIndexerSkillset:
    api_key = settings.embedding_api_key
    if not api_key:
        raise ValueError(
            "AZURE_OPENAI_EMBEDDING_API_KEY or AZURE_OPENAI_API_KEY is required for skillset setup."
        )

    cognitive_services = AIServicesAccountKey(
        key=api_key,
        subdomain_url=settings.embedding_services_url,
        description="Foundry embedding service for indexer",
    )

    # Blob indexer extracts PDF text to /document/content (built-in parsing).
    split_skill = SplitSkill(
        description="Split extracted text into chunks",
        context="/document",
        text_split_mode="pages",
        maximum_page_length=settings.chunk_size,
        page_overlap_length=settings.chunk_overlap,
        inputs=[InputFieldMappingEntry(name="text", source="/document/content")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")],
    )

    embedding_skill = AzureOpenAIEmbeddingSkill(
        description="Generate embeddings for text chunks",
        context="/document/pages/*",
        resource_url=settings.embedding_services_url,
        api_key=api_key,
        deployment_name=settings.azure_openai_embedding_deployment,
        model_name=settings.azure_openai_embedding_model,
        dimensions=settings.embedding_dimensions,
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="text_vector")],
    )

    index_projections = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=settings.azure_search_index_name,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(name="snippet", source="/document/pages/*"),
                    InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                    InputFieldMappingEntry(name="title", source="/document/metadata_storage_name"),
                    InputFieldMappingEntry(name="filepath", source="/document/metadata_storage_name"),
                    InputFieldMappingEntry(name="url", source="/document/metadata_storage_path"),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode="skipIndexingParentDocuments"
        ),
    )

    return SearchIndexerSkillset(
        name=settings.skillset_name,
        description="Extract, chunk, and embed retail PDF documents",
        skills=[split_skill, embedding_skill],
        cognitive_services_account=cognitive_services,
        index_projection=index_projections,
    )


def create_skillset(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client = get_indexer_client(settings)
    skillset = build_skillset(settings)
    client.create_or_update_skillset(skillset)
    print(f"Skillset '{settings.skillset_name}' created or updated.")


if __name__ == "__main__":
    create_skillset()
