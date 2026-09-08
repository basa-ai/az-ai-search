# Azure RAG Application

## Prerequisites

- Python 3.11+
- `az login` and subscription set:
  ```bash
  az login
  az account set --subscription 53bf6043-e666-4cba-aff6-b1127545b48f
  ```

## Setup

```bash
cd az-ai-search
cp .env.example .env
# Fill AZURE_STORAGE_CONNECTION_STRING and AZURE_OPENAI_API_KEY in .env

pip install -r requirements.txt

# One-time: create index, datasource, skillset, indexer
python -m setup.run_setup
python -m setup.run_indexer

# Run API
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the return policy?"}'
```

See **[LEARNING.md](LEARNING.md)** for architecture notes (SharePoint ingestion, video, ACLs, Teams, queues, indexing).
