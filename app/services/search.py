import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.core.exceptions import HttpResponseError
from azure.identity import get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import OpenAI

from app.config import Settings, get_settings
from app.models.schemas import Citation
from app.services.azure_auth import get_azure_credential

logger = logging.getLogger(__name__)

SEARCH_AUTH_HELP = (
    "Add AZURE_SEARCH_QUERY_KEY or AZURE_SEARCH_ADMIN_KEY to .env "
    "(AI Search → Keys in Azure Portal), then restart uvicorn."
)


@dataclass
class RetrievedChunk:
    title: str | None
    snippet: str | None
    url: str | None
    path: str | None


class SearchAuthError(RuntimeError):
    pass


def _search_credential() -> TokenCredential:
    settings = get_settings()
    if settings.azure_search_admin_key:
        return AzureKeyCredential(settings.azure_search_admin_key)
    if settings.azure_search_query_key:
        return AzureKeyCredential(settings.azure_search_query_key)
    return get_azure_credential()


def _get_search_client() -> SearchClient:
    settings = get_settings()
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=_search_credential(),
    )


def _get_embedding_client() -> OpenAI:
    settings = get_settings()
    timeout = settings.api_timeout_seconds
    if settings.embedding_api_key:
        return OpenAI(
            base_url=settings.embedding_openai_endpoint,
            api_key=settings.embedding_api_key,
            timeout=timeout,
        )
    token_provider = get_bearer_token_provider(
        get_azure_credential(), "https://ai.azure.com/.default"
    )
    return OpenAI(
        base_url=settings.embedding_openai_endpoint,
        api_key=token_provider,
        timeout=timeout,
    )


def _normalize_chunk(raw: dict, settings: Settings) -> RetrievedChunk:
    title = raw.get("title") or "Unknown"
    filename = title

    url = raw.get("url")
    if url:
        url = unquote(url)
    if not url or not url.startswith("http"):
        url = f"{settings.blob_base_url}/{filename}"

    path = raw.get("filepath")
    if path and path.startswith("http"):
        path = unquote(path).split(f"/{settings.azure_storage_container}/", 1)[-1]
        path = f"{settings.azure_storage_container}/{path}"
    elif not path:
        path = f"{settings.azure_storage_container}/{filename}"
    elif "/" not in path:
        path = f"{settings.azure_storage_container}/{path}"

    return RetrievedChunk(
        title=title,
        snippet=raw.get("snippet"),
        url=url,
        path=path,
    )


def embed_query(query: str, settings: Settings | None = None) -> list[float]:
    settings = settings or get_settings()
    logger.info("Embedding query...")
    client = _get_embedding_client()
    response = client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=query,
    )
    logger.info("Embedding complete.")
    return response.data[0].embedding


def log_chunks(chunks: list[RetrievedChunk]) -> None:
    logger.info("Found %d chunk(s).", len(chunks))
    for index, chunk in enumerate(chunks, start=1):
        snippet_preview = (chunk.snippet or "").replace("\n", " ")[:120]
        logger.info(
            "  Chunk %d | title=%s | path=%s | url=%s | snippet=%s",
            index,
            chunk.title,
            chunk.path,
            chunk.url,
            snippet_preview,
        )


def search_chunks(query: str, settings: Settings | None = None) -> list[RetrievedChunk]:
    settings = settings or get_settings()
    embedding = embed_query(query, settings)
    search_client = _get_search_client()

    vector_query = VectorizedQuery(
        vector=embedding,
        k_nearest_neighbors=settings.top_k_chunks,
        fields="text_vector",
    )

    logger.info("Searching index...")
    try:
        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["title", "snippet", "url", "filepath"],
            top=settings.top_k_chunks,
        )
        chunks = [_normalize_chunk(dict(result), settings) for result in results]
        log_chunks(chunks)
        return chunks
    except HttpResponseError as exc:
        if exc.status_code == 403:
            raise SearchAuthError(SEARCH_AUTH_HELP) from exc
        raise


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    seen: set[tuple[str | None, str | None]] = set()
    citations: list[Citation] = []
    for chunk in chunks:
        key = (chunk.title, chunk.url)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                title=chunk.title,
                url=chunk.url,
                path=chunk.path,
            )
        )
    return citations


_PDF_TITLE_PATTERN = re.compile(r"[\w\-]+\.pdf", re.IGNORECASE)


def filter_citations_for_answer(
    citations: list[Citation],
    answer: str,
    chunks: list[RetrievedChunk],
) -> list[Citation]:
    """Keep only sources the answer actually references; fall back to top hit."""
    if not citations:
        return []

    answer_lower = answer.lower()
    referenced = [
        citation
        for citation in citations
        if citation.title and citation.title.lower() in answer_lower
    ]
    if referenced:
        return referenced

    for title in _PDF_TITLE_PATTERN.findall(answer):
        matched = next(
            (c for c in citations if c.title and c.title.lower() == title.lower()),
            None,
        )
        if matched and matched not in referenced:
            referenced.append(matched)
    if referenced:
        return referenced

    if chunks:
        top = chunks_to_citations(chunks[:1])
        if top:
            return top

    return citations[:1]
