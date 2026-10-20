# NSDDD v4.0 — Local FastAPI Server

**Local use only — not part of the public NSDDD distribution.**

> **Model/metadata paths:** this server reads model + metadata from the install workspace
> resolved via `install_config.json`. See [`../WORKSPACE_NOTES.md`](../WORKSPACE_NOTES.md)
> for where the workspace is, how it's resolved, and why it's a thin symlink dir in `~/`.

The HTTP counterpart of the [MCP server](../mcp_server_local/README.md). Both wrap the
**same** v4.0 engine (`mcp_server_local.engine`), which executes the engine cells of
`document_metadata_search_voila.ipynb` directly — so the REST API, the MCP tools and the
Voilà UI all share one implementation of the Qwen3-Embedding-0.6B cross-lingual search. There is no
duplicated logic to drift, and **no dependency on any v3.5 component**.

## Multilingual (v4.0)

Every result carries the same multilingual fields as the MCP server:
`language` / `language_label`, `is_original_language`, `segment_number`, and a
`counterpart` (aligned text in the other language, or `null` when there is no reliable
alignment — with `alignment_flag` set to `doc`/`low` when suppressed). `GET /stats`
reports the per-language `language_breakdown` and `documents_with_alignment`.

## Endpoints

| Method | Path | Purpose | Loads model? |
|---|---|---|---|
| `GET`  | `/` | API info | no |
| `GET`  | `/health` | Liveness + whether the model is loaded yet | no |
| `GET`  | `/filters` | Enumerate available metadata filter values | no |
| `POST` | `/search` | Qwen3-Embedding-0.6B cross-lingual semantic search | yes (first call) |
| `POST` | `/keyword` | Exact / fuzzy keyword search | yes (first call) |
| `POST` | `/boolean` | Boolean keyword search (AND, OR, NOT, brackets, "phrases", wildcards) | yes (first call) |
| `GET`  | `/stats` | Corpus, model and per-language statistics | yes |
| `GET`  | `/docs` | Interactive OpenAPI (Swagger) UI | no |

Request bodies mirror the MCP tool inputs. Example:

```bash
curl -s http://127.0.0.1:8868/search -H 'Content-Type: application/json' -d '{
  "query": "national sovereignty and defence",
  "search_threshold": 0.72,
  "max_results": 40,
  "filters": {"regions": ["Europe"], "year_min": 2015},
  "result_limit": 10
}' | jq
```

Defaults: search threshold 0.72, organisation membership counted as of each document's year, cluster detail 0.78, `context_window` 1.
Exports (`"export": true`) land in the installer's `outputs/` directory.

## Running

```bash
# from the installer root
PYTHONPATH="$PWD" python3 -m api_server_local.app
# or with uvicorn directly (auto-reload, custom port, etc.)
PYTHONPATH="$PWD" uvicorn api_server_local.app:app --host 127.0.0.1 --port 8868
```

The model loads lazily on the first `/search`, `/keyword` or `/stats` call (~60 s for
that call); the server starts instantly. Set `NSDDD_API_PRELOAD=1` to load the model
eagerly at startup instead.

Environment overrides: `NSDDD_API_HOST` (default `127.0.0.1`), `NSDDD_API_PORT`
(default `8868`).

## Install the extra deps

`fastapi` and `uvicorn` are not in the public installer requirements. Install them into
the installer's `.venv`:

```bash
/path/to/python3 -m pip install -r api_server_local/requirements.txt
```

## Notes

- The notebook's status `print()` output goes to stderr; JSON responses stay clean.
- Smoke test (no model load): `PYTHONPATH=<installer root> python3 -c "from fastapi.testclient import TestClient; from api_server_local.app import app; print(TestClient(app).get('/filters').status_code)"`
