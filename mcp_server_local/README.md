# NSDDD v4.0 — Local MCP Server



> **Model/metadata paths:** this server reads model + metadata from the install workspace
> resolved via `install_config.json`. See [`../WORKSPACE_NOTES.md`](../WORKSPACE_NOTES.md)
> for where the workspace is, how it's resolved, and why it's a thin symlink dir in `~/`.

An MCP (stdio) server wrapping the search engine of
`document_metadata_search_voila.ipynb`. The engine cells of the notebook are
executed directly at load time, so the server always uses exactly the same
search code, thresholds, filters and CSV export format as the Voilà interface
— there is no duplicated logic to drift.

## Multilingual (v4.0)

v4.0 uses **Qwen3-Embedding-0.6B cross-lingual embeddings** (256 dimensions; ~1.16M segments across 680
documents, 121 countries, 34 languages). A query in any language matches
documents in their original language as well as in English. Each search result
carries:

- `language` / `language_label` — the segment's language (e.g. `es` / `Espanol`),
- `is_original_language` — `true` for original-language segments,
- `segment_number` — the bare 1-based segment number,
- `counterpart` — the aligned text in the other language (`{language, text,
  segment_ids, segment_numbers}`), or `null` when there is no reliable
  alignment. When the document's overall alignment is unreliable, or a specific
  link is weak, the counterpart text is suppressed and `alignment_flag` is set
  to `doc` or `low` respectively (matching the Voilà UI's confidence gating).

`corpus_stats` additionally reports the per-language `language_breakdown` and
`documents_with_alignment`.

## Tools

| Tool              | Purpose                                                                                                                                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `semantic_search` | Qwen3-Embedding-0.6B cross-lingual similarity search; metadata filters; clustering; `context_window` segments of surrounding text per hit; multilingual fields per result; CSV export (results + `_norm_context` companion) |
| `keyword_search`  | Exact-string search with word boundaries (optional fuzzy matching); same filters/context/export/multilingual fields                                                                                                         |
| `filter_options`  | Enumerate available filter values (regions, organisations, income groups, Freedom House status, doc types, years…) — no model load                                                                                          |
| `corpus_stats`    | Corpus, model and per-language statistics                                                                                                                                                                                   |

Defaults: search threshold 0.72, organisation membership counted as of each document's year, cluster detail 0.78, `context_window` 1.
Exports land in the installer's `outputs/` directory.

## Registration (`~/.claude/mcp_servers.json`)

```json
{
  "nsddd-search": {
    "command": "/path/to/python3",
    "args": ["-m", "mcp_server_local.server"],
    "env": {
      "PYTHONPATH": "/path/to/NSDDD_v4.0_installer"
    }
  }
}
```

Open a new Claude Code instance after registering. The MCP handshake is
immediate; the model loads lazily on the first tool call (~60 s for that call:
metadata + segments + memmap embeddings + encoder), then all calls are fast.

## Notes

- Model and metadata paths are resolved exactly as the notebook resolves them
  (`install_config.json` → installed workspace, with fallbacks).
- The notebook's status `print()` output is redirected to stderr so the MCP
  stdout protocol stream stays clean.
- Smoke test (loads the model, runs one search, ~60 s):
  `PYTHONPATH=<installer root> python3 -c "import json; from mcp_server_local import engine; print(json.dumps(engine.corpus_stats()))"`
