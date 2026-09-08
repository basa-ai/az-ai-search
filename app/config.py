from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    azure_search_endpoint: str
    azure_search_index_name: str = "retail-docs-index"
    azure_search_admin_key: str | None = None
    azure_search_query_key: str | None = None

    azure_storage_account: str = "retaildemobasa"
    azure_storage_container: str = "retaildocs"
    azure_storage_connection_string: str | None = None

    azure_openai_endpoint: str
    azure_openai_resource_url: str | None = None
    azure_openai_chat_deployment: str = "gpt-5-mini-1"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_embedding_model: str = "text-embedding-3-small"
    azure_openai_api_key: str | None = None
    # Embedding may live on a different Foundry project than chat (e.g. srius2023-1305)
    azure_openai_embedding_resource_url: str | None = None
    azure_openai_embedding_api_key: str | None = None

    chunk_size: int = 500
    chunk_overlap: int = 100
    top_k_chunks: int = 5
    llm_top_k_chunks: int = 5
    llm_snippet_chars: int = 450
    max_history_turns: int = 10
    api_timeout_seconds: float = 180.0
    chat_max_completion_tokens: int = 4096

    embedding_dimensions: int = 1536

    datasource_name: str = "retail-blob-datasource"
    skillset_name: str = "retail-skillset"
    indexer_name: str = "retail-indexer"

    @property
    def blob_base_url(self) -> str:
        return f"https://{self.azure_storage_account}.blob.core.windows.net/{self.azure_storage_container}"

    @property
    def ai_services_url(self) -> str:
        if self.azure_openai_resource_url:
            return self.azure_openai_resource_url.rstrip("/")
        endpoint = self.azure_openai_endpoint.rstrip("/")
        if endpoint.endswith("/openai/v1"):
            return endpoint[: -len("/openai/v1")]
        return endpoint

    @property
    def embedding_services_url(self) -> str:
        return (self.azure_openai_embedding_resource_url or self.ai_services_url).rstrip("/")

    @property
    def embedding_api_key(self) -> str | None:
        return self.azure_openai_embedding_api_key or self.azure_openai_api_key

    @property
    def embedding_openai_endpoint(self) -> str:
        return f"{self.embedding_services_url}/openai/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
