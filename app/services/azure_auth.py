from azure.identity import AzureCliCredential, DefaultAzureCredential


def get_azure_credential():
    """Prefer Azure CLI for local dev — DefaultAzureCredential can hang probing other sources."""
    try:
        return AzureCliCredential()
    except Exception:
        return DefaultAzureCredential(
            exclude_managed_identity_credential=True,
            exclude_visual_studio_code_credential=True,
            exclude_shared_token_cache_credential=True,
        )
