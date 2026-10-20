#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI server for the NSDDD v4.0 search system (local use only).

HTTP counterpart of the MCP server. Both wrap the SAME v4.0 engine
(``mcp_server_local.engine``), which executes the Voilà notebook's search
cells directly — so the REST API, the MCP tools and the Voilà UI all share one
implementation of the Qwen3-Embedding-0.6B cross-lingual search, with no duplicated logic to
drift and no dependency on any v3.5 component.

Multilingual: every result carries ``language`` / ``language_label``,
``is_original_language``, ``segment_number`` and (when reliably aligned) a
``counterpart`` in the other language — see ``engine._multilingual_fields``.

The model loads lazily on the first search/stats request (~60 s for that call);
the server itself starts instantly. Set ``NSDDD_API_PRELOAD=1`` to load the
model eagerly at startup instead.

Run:
    PYTHONPATH=<installer root> python3 -m api_server_local.app
    # or
    PYTHONPATH=<installer root> uvicorn api_server_local.app:app --port 8868
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from mcp_server_local import engine

HOST = os.environ.get('NSDDD_API_HOST', '127.0.0.1')
PORT = int(os.environ.get('NSDDD_API_PORT', '8868'))


# --------------------------------------------------------------------------- #
# Request models (mirror the MCP tool inputs; all filter fields optional)
# --------------------------------------------------------------------------- #
class Filters(BaseModel):
    """Metadata filters. Within a field values are OR; across fields AND.
    Use GET /filters to list available values."""
    countries: Optional[List[str]] = Field(None, description='ISO3 codes, e.g. ["DEU", "FRA"]')
    regions: Optional[List[str]] = None
    subregions: Optional[List[str]] = None
    organizations: Optional[List[str]] = Field(None, description='e.g. NATO, EU, ASEAN')
    membership_at_publication: Optional[bool] = Field(None, description='With organizations: members in the year each document was published (default true); false = members today')
    income_groups: Optional[List[str]] = None
    freedom_house_status: Optional[List[str]] = Field(None, description='Free / Partly Free / Not Free')
    oda_status: Optional[List[str]] = None
    small_states_groups: Optional[List[str]] = Field(None, description='Small States / SSF / UN SIDS')
    huntington_civilizations: Optional[List[str]] = None
    doc_types: Optional[List[str]] = Field(None, description='NSS / WP / DD / TA')
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    most_recent_only: Optional[bool] = None

    def as_engine_dict(self) -> Optional[Dict[str, Any]]:
        d = {k: v for k, v in self.model_dump().items()
             if v not in (None, [], False) or (k == 'membership_at_publication' and v is not None)}
        return d or None


class SearchRequest(BaseModel):
    query: str = Field(..., description='Topic description, e.g. "threats to democracy"')
    search_threshold: float = Field(0.72, ge=0.5, le=1.0)
    cluster_threshold: float = Field(0.78, ge=0.5, le=1.0)
    context_window: int = Field(1, description='Segments of surrounding text per hit')
    max_results: Optional[int] = Field(None, description='Cap on results (highest scores kept)')
    filters: Optional[Filters] = None
    export: bool = Field(False, description='Export results CSV + norm_context CSV to outputs/')
    export_name: Optional[str] = None
    result_limit: int = Field(20, description='Max results returned inline (export contains all)')


class KeywordRequest(BaseModel):
    keyword: str
    smart_boundaries: bool = Field(True, description='Allow hyphenated variants')
    fuzzy_matching: bool = False
    fuzzy_threshold: int = 80
    context_window: int = 1
    filters: Optional[Filters] = None
    export: bool = False
    export_name: Optional[str] = None
    result_limit: int = 20


class BooleanRequest(BaseModel):
    query: str = Field(..., description='e.g. (cyber* OR digital) AND "critical infrastructure" AND NOT terrorism')
    scoring: str = Field('match_count', description="'match_count', 'avg_score' or 'max_score'")
    context_window: int = 1
    filters: Optional[Filters] = None
    export: bool = False
    export_name: Optional[str] = None
    result_limit: int = 20


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    print('=== NSDDD v4.0 search FastAPI server starting '
          '(model loads on first use) ===', flush=True)
    if os.environ.get('NSDDD_API_PRELOAD') == '1':
        print('NSDDD_API_PRELOAD=1 → loading model now...', flush=True)
        await _to_thread(engine.ensure_loaded)
        print('Model ready.', flush=True)
    yield
    print('=== NSDDD v4.0 search FastAPI server shutting down ===', flush=True)


app = FastAPI(
    title='NSDDD v4.0 Search API',
    description=('Cross-lingual (Qwen3-Embedding-0.6B) semantic + keyword search over the '
                'National Security and Defence Documents Dataset. Shares one '
                'engine with the MCP server and the Voilà UI.'),
    version='4.0.0',
    lifespan=lifespan,
)


async def _to_thread(fn, **kwargs):
    import asyncio
    return await asyncio.to_thread(fn, **kwargs)


@app.get('/')
async def root():
    return {
        'name': 'NSDDD v4.0 Search API',
        'version': '4.0.0',
        'cross_lingual': True,
        'model_loaded': engine._model_ready,
        'endpoints': {
            'health': '/health',
            'semantic_search': '/search (POST)',
            'keyword_search': '/keyword (POST)',
            'boolean_search': '/boolean (POST)',
            'filters': '/filters',
            'stats': '/stats',
            'guidance': '/guidance',
            'docs': '/docs',
        },
    }


@app.get('/guidance')
async def guidance_endpoint():
    """Query-writing and score-reading guidance (same text the MCP server sends as its instructions)."""
    from mcp_server_local import guidance
    return {'instructions': guidance.SERVER_INSTRUCTIONS, 'formulate_queries_prompt': guidance.FORMULATE_PROMPT,
            'score_bands': {'strong': guidance.STRONG, 'candidate': guidance.CANDIDATE}, 'provisional': True}


@app.get('/health')
async def health():
    """Liveness + whether the model has been loaded yet (does not trigger a load)."""
    return {
        'status': 'healthy',
        'model_loaded': engine._model_ready,
    }


@app.post('/search')
async def search(req: SearchRequest):
    """Cross-lingual semantic search. First call loads the model (~60 s)."""
    try:
        return await _to_thread(
            engine.semantic_search,
            query=req.query,
            search_threshold=req.search_threshold,
            cluster_threshold=req.cluster_threshold,
            context_window=req.context_window,
            max_results=req.max_results,
            filters=req.filters.as_engine_dict() if req.filters else None,
            export=req.export,
            export_name=req.export_name,
            result_limit=req.result_limit,
        )
    except Exception as e:  # noqa: BLE001 — surface engine errors as 500
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'Search failed: {e}')


@app.post('/keyword')
async def keyword(req: KeywordRequest):
    """Exact / fuzzy keyword search with the same filters and multilingual fields."""
    try:
        return await _to_thread(
            engine.keyword_search,
            keyword=req.keyword,
            smart_boundaries=req.smart_boundaries,
            fuzzy_matching=req.fuzzy_matching,
            fuzzy_threshold=req.fuzzy_threshold,
            context_window=req.context_window,
            filters=req.filters.as_engine_dict() if req.filters else None,
            export=req.export,
            export_name=req.export_name,
            result_limit=req.result_limit,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'Keyword search failed: {e}')


@app.post('/boolean')
async def boolean(req: BooleanRequest):
    """Boolean keyword search: AND, OR, NOT, brackets, "phrases", wildcards * and ?."""
    try:
        out = await _to_thread(
            engine.boolean_search,
            query=req.query,
            scoring=req.scoring,
            context_window=req.context_window,
            filters=req.filters.as_engine_dict() if req.filters else None,
            export=req.export,
            export_name=req.export_name,
            result_limit=req.result_limit,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'Boolean search failed: {e}')
    if 'error' in out:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=out)
    return out


@app.get('/filters')
async def filters():
    """Enumerate available values for every metadata filter (no model load)."""
    try:
        return await _to_thread(engine.filter_options)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'filter_options failed: {e}')


@app.get('/stats')
async def stats():
    """Corpus, model and per-language statistics. Loads the model if needed."""
    try:
        return await _to_thread(engine.corpus_stats)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'corpus_stats failed: {e}')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level='info')
