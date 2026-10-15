#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP server for the NSDDD v4.0 search system (local use only).

Wraps the Voila notebook's search engine (via mcp_server_local.engine) and
exposes it over MCP stdio.

Start with:  python -m mcp_server_local.server   (from the app folder)

The search engine and model are loaded BEFORE the event loop and the stdio connection start (about 25 seconds on a
laptop). Loading lazily on the first tool call, inside a worker thread while the stdio pipes were in use, hung
indefinitely on Windows (Windows test, 2026-10-02: no answer after 9 min 45 s; loading first answered in 13 s).

v4.0 is multilingual (Qwen3-Embedding-0.6B cross-lingual embeddings): documents are searched
in their original language as well as English, and each result carries its
language plus, where available, its aligned counterpart in the other language
(suppressed when the alignment is low-confidence).

Tools:
  - semantic_search: Qwen3-Embedding-0.6B cross-lingual similarity search with metadata
    filters, clustering, context windows and CSV export (results +
    norm_context companion)
  - keyword_search: exact/fuzzy keyword search with the same filters/export
  - filter_options: enumerate available metadata filter values
  - corpus_stats: corpus, model and per-language information
"""

import asyncio
import json
import sys
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent, Tool

from . import engine, guidance

app = Server('nsddd-search', instructions=guidance.SERVER_INSTRUCTIONS)

_FILTERS_SCHEMA = {
    'type': 'object',
    'description': ('Metadata filters. Within a field values are OR; across '
                    'fields AND. Use filter_options to list available values.'),
    'properties': {
        'countries': {'type': 'array', 'items': {'type': 'string'},
                      'description': 'ISO3 codes, e.g. ["DEU", "FRA"]'},
        'regions': {'type': 'array', 'items': {'type': 'string'}},
        'subregions': {'type': 'array', 'items': {'type': 'string'}},
        'organizations': {'type': 'array', 'items': {'type': 'string'},
                          'description': 'e.g. NATO, EU, ASEAN. By default a country counts if it was a member in the year the document was published; set membership_at_publication to false to count current members'},
        'membership_at_publication': {'type': 'boolean',
                                      'description': 'With organizations (default true): count a country as a member if it was one in the year the '
                                                     'document was published (joining year inclusive, leaving year exclusive). Set false to count today\'s members'},
        'income_groups': {'type': 'array', 'items': {'type': 'string'}},
        'freedom_house_status': {'type': 'array', 'items': {'type': 'string'},
                                 'description': 'Free / Partly Free / Not Free'},
        'oda_status': {'type': 'array', 'items': {'type': 'string'}},
        'small_states_groups': {'type': 'array', 'items': {'type': 'string'},
                                'description': 'Small States / SSF / UN SIDS'},
        'huntington_civilizations': {'type': 'array', 'items': {'type': 'string'}},
        'doc_types': {'type': 'array', 'items': {'type': 'string'},
                      'description': 'NSS / WP / DD / TA'},
        'year_min': {'type': 'integer'},
        'year_max': {'type': 'integer'},
        'most_recent_only': {'type': 'boolean'},
    },
}


@app.list_tools()
async def list_tools() -> list[Tool]:
    _fuzzy = engine.fuzzy_available()      # fuzzy matching is offered only when its package is installed
    return [
        Tool(
            name='semantic_search',
            description=(
                'Cross-lingual semantic search across ' + engine.corpus_summary() + ' using '
                'Qwen3-Embedding-0.6B multilingual embeddings. A query in any language '
                'matches documents in their original language and in English. '
                'Each result reports its language, segment number and (when '
                'reliably aligned) its counterpart text in the other language. '
                'Returns clustered results with surrounding context segments. '
                'Clusters are numbered, largest first, and each comes with its most typical sentence ("example"); '
                'name them yourself from the examples if headings are needed. '
                'Write the query as one declarative policy-style sentence naming concrete measures or institutions, '
                'not a keyword string or a question. Each result has a `confidence` (strong >= 0.75, candidate 0.70-0.75, '
                'weak < 0.70) and the response has `score_bands` and `search_notes`; read candidates before using them. '
                'Searches take roughly 10 to 60 seconds.'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'query': {'type': 'string',
                              'description': 'Topic description, e.g. "threats to democracy and the democratic order"'},
                    'search_threshold': {'type': 'number', 'default': 0.72,
                                         'minimum': 0.5, 'maximum': 1.0,
                                         'description': 'Minimum similarity. 0.75+ is strong evidence, 0.70-0.75 candidates to read, below 0.70 mostly noise. '
                                                        'Use 0.70 to explore, 0.75 for evidence.'},
                    'cluster_threshold': {'type': 'number', 'default': 0.78,
                                          'minimum': 0.5, 'maximum': 1.0},
                    'context_window': {'type': 'integer', 'default': 1,
                                       'description': 'Segments of surrounding text returned before/after each hit (1 matches the search page)'},
                    'max_results': {'type': 'integer',
                                    'description': 'Cap on results (highest scores kept)'},
                    'filters': _FILTERS_SCHEMA,
                    'export': {'type': 'boolean', 'default': False,
                               'description': 'Export the results to outputs/ (CSV pair by default, or one Excel workbook)'},
                    'export_format': {'type': 'string', 'enum': ['csv', 'xlsx'], 'default': 'xlsx',
                                      'description': 'xlsx (default): one workbook with clickable links, opens correctly in every language version of Excel. '
                                                     'csv: results CSV + norm_context CSV with plain URLs (easiest to read in code). '
                                                     'Files carry a time stamp, so a repeated export never overwrites an earlier one'},
                    'export_name': {'type': 'string',
                                    'description': 'Base name for the export files (defaults to the query). The Topic recorded inside is always the query'},
                    'result_limit': {'type': 'integer', 'default': 20,
                                     'description': 'Max results returned inline (export contains all)'},
                    'count_passages_once': {'type': 'boolean', 'default': True,
                                            'description': 'Merge an original-language match into the English match of the same passage, so each passage '
                                                           'counts once (response field pairs_merged says how many were merged)'},
                },
                'required': ['query'],
            },
        ),
        Tool(
            name='keyword_search',
            description=(
                'Exact-string keyword search (word boundaries' + (', optional fuzzy matching' if _fuzzy else '') +
                ') across all segments, with the same metadata filters, '
                'context windows and export as semantic_search. Use for '
                'literal-term probes where semantic search is unsuitable.'
            ),
            inputSchema={
                'type': 'object',
                'properties': {
                    'keyword': {'type': 'string'},
                    'smart_boundaries': {'type': 'boolean', 'default': True,
                                         'description': 'Allow hyphenated variants'},
                    **({'fuzzy_matching': {'type': 'boolean', 'default': False},
                        'fuzzy_threshold': {'type': 'integer', 'default': 80}} if _fuzzy else {}),
                    'context_window': {'type': 'integer', 'default': 1},
                    'filters': _FILTERS_SCHEMA,
                    'export': {'type': 'boolean', 'default': False},
                    'export_format': {'type': 'string', 'enum': ['csv', 'xlsx'], 'default': 'xlsx'},
                    'export_name': {'type': 'string'},
                    'result_limit': {'type': 'integer', 'default': 20},
                    'count_passages_once': {'type': 'boolean', 'default': True},
                },
                'required': ['keyword'],
            },
        ),
        Tool(
            name='filter_options',
            description=('List available values for every metadata filter '
                         '(regions, organisations, income groups, Freedom House '
                         'status, document types, year range, etc.). Does not '
                         'load the model.'),
            inputSchema={'type': 'object', 'properties': {}},
        ),
        Tool(
            name='corpus_stats',
            description='Corpus and model statistics (loads the model).',
            inputSchema={'type': 'object', 'properties': {}},
        ),
    ]


@app.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [Prompt(
        name='formulate_queries',
        description='Turn a research topic into 4 optimised NSDDD semantic search queries, with filters and reading rules.',
        arguments=[PromptArgument(name='topic', description='Research topic, e.g. "military support to civil authorities"',
                                  required=True)],
    )]


@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
    if name != 'formulate_queries':
        raise ValueError(f'Unknown prompt: {name}')
    topic = (arguments or {}).get('topic', '[INSERT YOUR TOPIC HERE]')
    return GetPromptResult(
        description='Formulate NSDDD semantic search queries',
        messages=[PromptMessage(role='user', content=TextContent(type='text', text=guidance.FORMULATE_PROMPT.format(topic=topic)))],
    )


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    arguments = arguments or {}

    if name == 'semantic_search':
        result = await asyncio.to_thread(engine.semantic_search, **arguments)
    elif name == 'keyword_search':
        result = await asyncio.to_thread(engine.keyword_search, **arguments)
    elif name == 'filter_options':
        result = await asyncio.to_thread(engine.filter_options)
    elif name == 'corpus_stats':
        result = await asyncio.to_thread(engine.corpus_stats)
    else:
        result = {'error': f'Unknown tool: {name}'}

    return [TextContent(type='text', text=json.dumps(result, indent=2, default=str))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def run():
    print('NSDDD v4.0 search MCP server: loading the search model first (about 25 seconds)...', file=sys.stderr, flush=True)
    engine.ensure_loaded()
    print('Model loaded. Server ready.', file=sys.stderr, flush=True)
    asyncio.run(main())


if __name__ == '__main__':
    run()
