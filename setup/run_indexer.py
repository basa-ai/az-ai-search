import sys
import time

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.search.documents import SearchClient

from app.config import get_settings
from setup.client import get_indexer_client, get_search_credential


def _status_value(state) -> str:
    return state.value if hasattr(state, "value") else str(state)


def _print_indexer_errors(last_result) -> None:
    if last_result.errors:
        for error in last_result.errors[:10]:
            print(f"Error: {error.error_message}")
            if error.details:
                print(f"  Details: {error.details}")

    if last_result.failed_item_count:
        print(
            "\nCommon fixes for embedding skill failures:\n"
            "  1. Verify AZURE_OPENAI_EMBEDDING_DEPLOYMENT matches the deployment name in Azure AI Foundry exactly\n"
            "  2. In retail-ai-agent → Networking, enable 'Allow Azure services on the trusted services list'\n"
            "  3. Confirm text-embedding-3-small is deployed on retail-ai-agent\n"
        )


def _get_document_count(settings) -> int | None:
    try:
        search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
            credential=get_search_credential(settings),
        )
        results = search_client.search(search_text="*", include_total_count=True, top=0)
        return results.get_count()
    except HttpResponseError as exc:
        print(f"Could not query index document count: {exc.message}")
        print("Add AZURE_SEARCH_ADMIN_KEY to .env or grant Search Index Data Reader role.")
        return None


def run_indexer(poll_interval: int = 10, timeout: int = 3600) -> None:
    settings = get_settings()
    client = get_indexer_client(settings)

    try:
        client.get_indexer(settings.indexer_name)
    except ResourceNotFoundError:
        print(f"Indexer '{settings.indexer_name}' not found. Run 'python -m setup.run_setup' first.")
        sys.exit(1)

    print(f"Resetting indexer '{settings.indexer_name}'...")
    client.reset_indexer(settings.indexer_name)

    print(f"Starting indexer '{settings.indexer_name}'...")
    client.run_indexer(settings.indexer_name)

    elapsed = 0
    while elapsed < timeout:
        status = client.get_indexer_status(settings.indexer_name)
        last_result = status.last_result
        if last_result:
            state = _status_value(last_result.status)
            if state != "reset":
                print(f"Indexer status: {state}")
            if state in ("success", "transientFailure", "persistentFailure"):
                print(f"Processed {last_result.item_count} blob item(s).")
                if last_result.failed_item_count:
                    print(f"Failed items: {last_result.failed_item_count}")
                if last_result.warnings:
                    for warning in last_result.warnings[:10]:
                        print(f"Warning: {warning.message}")
                _print_indexer_errors(last_result)

                if state != "success":
                    print(f"Indexer failed: {last_result.error_message}")
                    sys.exit(1)

                doc_count = _get_document_count(settings)
                if doc_count is not None:
                    print(f"Documents in index: {doc_count}")
                    if doc_count == 0:
                        print(
                            "Indexer succeeded but index is empty. "
                            "Check Azure Portal → AI Search → Indexers → retail-indexer → Execution history."
                        )
                        sys.exit(1)
                else:
                    print("Indexer succeeded. Could not verify document count (add AZURE_SEARCH_ADMIN_KEY to .env).")

                return
        time.sleep(poll_interval)
        elapsed += poll_interval

    print("Indexer timed out.")
    sys.exit(1)


if __name__ == "__main__":
    run_indexer()
