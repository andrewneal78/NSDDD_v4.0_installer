#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engine loader for the NSDDD v4.0 search system (multilingual Qwen3-Embedding-0.6B, 256 dimensions).

Executes the engine cells of document_metadata_search_voila.ipynb in a plain
Python namespace, so the MCP server uses exactly the same search code as the
Voila interface (single source of truth — no drift between notebook and
server). UI cells (loading widget, interface display, optional-init stub) are
skipped; IPython magics and top-level display calls are stripped.

All public functions redirect stdout to stderr: the notebook code prints
status messages, and stdout must stay clean for the MCP stdio protocol.
"""

import __future__
import json
import os
import re
import sys
import threading
import typing
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import guidance as _guidance

INSTALLER_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = INSTALLER_ROOT / 'document_metadata_search_voila.ipynb'
OUTPUTS_DIR = INSTALLER_ROOT / 'outputs'

_ns: Optional[Dict[str, Any]] = None
_model_ready = False
_lock = threading.Lock()

# Cells containing these markers are UI-only and are not executed
_EXCLUDE_MARKERS = ('_loading_widget', 'Initialize model (optional')
# IPython cell/line magics
_MAGIC_RE = re.compile(r'^\s*%{1,2}[A-Za-z]\S*.*$', re.M)
# Top-level UI calls that must not run outside the notebook
_UI_CALL_RE = re.compile(r'^(inject_app_favicon\(\)|display\(.*\))\s*$', re.M)


def load_namespace() -> Dict[str, Any]:
    """Execute the notebook's engine cells once; return the namespace."""
    global _ns
    if _ns is not None:
        return _ns

    with _lock:
        if _ns is not None:
            return _ns

        nb = json.loads(NOTEBOOK_PATH.read_text(encoding='utf-8'))
        sources = []
        for cell in nb['cells']:
            if cell.get('cell_type') != 'code':
                continue
            src = ''.join(cell['source'])
            if any(marker in src for marker in _EXCLUDE_MARKERS):
                continue
            src = _MAGIC_RE.sub('', src)
            src = _UI_CALL_RE.sub('', src)
            sources.append(src)

        # In Jupyter, cell 0's `from __future__ import annotations` persists to
        # later cells; plain exec compiles each cell separately, so the flag
        # must be applied to every cell or annotations would be evaluated.
        future_flags = __future__.annotations.compiler_flag

        # Exec into a real registered module: dataclasses (and pickling)
        # resolve cls.__module__ through sys.modules
        import types
        module = types.ModuleType('nsddd_notebook_engine')
        sys.modules['nsddd_notebook_engine'] = module
        ns = module.__dict__
        # Defensive: typing names used by the notebook without import
        ns.update({
            'Any': typing.Any, 'Dict': typing.Dict, 'List': typing.List,
            'Optional': typing.Optional, 'Set': typing.Set,
            'Tuple': typing.Tuple, 'Union': typing.Union,
        })
        prev_cwd = os.getcwd()
        os.chdir(INSTALLER_ROOT)  # the notebook resolves data paths from cwd
        try:
            with redirect_stdout(sys.stderr):
                for i, src in enumerate(sources):
                    code = compile(src, f'<nsddd-notebook-cell-{i}>', 'exec',
                                   future_flags)
                    exec(code, ns)
        finally:
            os.chdir(prev_cwd)

        _ns = ns
        return ns


def ensure_loaded(semantic=True) -> Dict[str, Any]:
    """Load data first; keyword/Boolean operations do not load the encoder."""
    ns = load_namespace()
    with _lock:
        with redirect_stdout(sys.stderr):
            model_dict, encoder = ns['initialize_model'](load_encoder=semantic)
        if model_dict is None:
            raise RuntimeError(f"Model failed to load: {ns.get('MODEL_LOAD_ERROR')}")
        if semantic and encoder is None:
            raise RuntimeError(f"Encoder failed to load: {ns.get('ENCODER_LOAD_ERROR')}")
    return ns


def _make_filters(ns: Dict[str, Any], filters: Optional[Dict]) -> Any:
    f = ns['MetadataFilters']()
    if filters:
        for key, value in filters.items():
            if not hasattr(f, key):
                raise ValueError(f'Unknown filter field: {key}')
            setattr(f, key, value)
    return f


def _truncate(text: str, limit: int) -> str:
    if text and len(text) > limit:
        return text[:limit] + '…'
    return text or ''


def _multilingual_fields(ns: Dict[str, Any], segment_id: str,
                         context_chars: int) -> Dict[str, Any]:
    """v4.0 cross-lingual enrichment for one segment id.

    The notebook (Qwen3-Embedding-0.6B, multilingual) stores per-segment ``lang`` and a
    document-level ``alignment_dict``/``alignment_anchor``. Original-language
    segments have ids of the form ``{prefix}/o/{n}``; English ``{prefix}/{n}``.
    These helpers live in the notebook namespace, so the MCP server stays in
    lock-step with the Voilà UI. Absent (pre-v4.0 notebooks) → empty enrichment.
    """
    seg_lang = ns.get('_seg_lang')
    if seg_lang is None:                       # pre-multilingual notebook
        return {}

    lang = seg_lang(segment_id)
    label_map = ns.get('LANG_LABEL', {})
    is_original = '/o/' in str(segment_id)

    seg_nums = ns.get('_seg_nums')
    segment_number = (seg_nums([segment_id])[0] if seg_nums else
                      str(segment_id).split('/')[-1])

    out: Dict[str, Any] = {
        'language': lang,
        'language_label': label_map.get(lang, lang.upper()),
        'is_original_language': is_original,
        'segment_number': segment_number,
    }

    # Aligned counterpart in the other language. _aligned_other returns
    # (text, label, lang, flag, other_ids); flag '' none, 'low' weak link,
    # 'doc' the whole document's alignment is unreliable. When flagged, the
    # notebook suppresses the (possibly wrong) counterpart text — we mirror that
    # but still report the flag so the caller knows alignment was uncertain.
    aligned_other = ns.get('_aligned_other')
    if aligned_other is not None:
        text, _label, other_lang, flag, other_ids = aligned_other(segment_id)
        nums = (ns['_seg_nums'](other_ids) if other_ids and ns.get('_seg_nums')
                else [])
        if text:
            out['counterpart'] = {
                'language': other_lang,
                'language_label': label_map.get(other_lang, other_lang.upper()),
                'text': _truncate(text, context_chars * 4),
                'segment_ids': list(other_ids),
                'segment_numbers': nums,
            }
        else:
            out['counterpart'] = None
        if flag:
            out['alignment_flag'] = flag      # 'low' or 'doc'
    return out


def _format_response(results: List[Any], cluster_info: Dict, result_limit: int,
                     context_chars: int = 400,
                     ns: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    formatted = []
    for r in sorted(results, key=lambda x: x.score, reverse=True)[:result_limit]:
        row = {
            'segment_id': r.segment_id,
            'score': round(float(r.score), 3),
            'text': r.text,
            'context_before': _truncate(r.context_before, context_chars),
            'context_after': _truncate(r.context_after, context_chars),
            'document': r.document_name,
            'country': r.country,
            'iso': r.country_iso,
            'year': r.year,
            'doc_type': r.doc_type,
            'cluster_id': r.cluster_id,
            'cluster_name': r.cluster_name,
            'region': r.region,
            'income_group': r.income_group,
            'freedom_status': r.freedom_status,
        }
        if ns is not None:
            row.update(_multilingual_fields(ns, r.segment_id, context_chars))
        formatted.append(row)

    cluster_summary = []
    cluster_dict = cluster_info.get('cluster_dict', {}) if cluster_info else {}
    names = cluster_info.get('cluster_names', {}) if cluster_info else {}
    for cid, indices in cluster_dict.items():
        if cid == 'singletons':
            continue
        cluster_summary.append({
            'cluster_id': cid,
            'name': names.get(cid, ''),
            'example': (cluster_info.get('cluster_examples') or {}).get(cid, ''),
            'size': len(indices),
        })
    cluster_summary.sort(key=lambda c: c['size'], reverse=True)

    return {
        'num_results': len(results),
        'num_clusters': cluster_info.get('num_clusters', 0) if cluster_info else 0,
        'num_singletons': cluster_info.get('num_singletons', 0) if cluster_info else 0,
        'clusters': cluster_summary,
        'clustering_note': cluster_info.get('clustering_note') if cluster_info else None,
        'countries': sorted({r.country_iso for r in results if r.country_iso}),
        'year_range': ([min(r.year for r in results if r.year),
                        max(r.year for r in results if r.year)]
                       if any(r.year for r in results) else None),
        'results': formatted,
    }


def fuzzy_available() -> bool:
    """Whether fuzzy keyword matching can run (needs rapidfuzz or fuzzywuzzy). Loads the notebook cells if needed."""
    return bool(load_namespace().get('FUZZY_AVAILABLE'))


def _export(ns, key: str, results, cluster_info, cfg, file_stem: Optional[str] = None) -> List[str]:
    written = ns['export_search_results'](
        {key: results}, {key: cluster_info}, cfg,
        output_dir=str(OUTPUTS_DIR), enable_export=True, file_stem=file_stem,
        iterative_names=True                      # time-stamped names, so a repeated export never overwrites an earlier one
    )
    return [str(p) for p in (written or [])]


def semantic_search(query: str,
                    search_threshold: float = 0.72,
                    cluster_threshold: float = 0.78,
                    context_window: int = 1,
                    max_results: Optional[int] = None,
                    filters: Optional[Dict] = None,
                    export: bool = False,
                    export_format: str = 'xlsx',
                    export_name: Optional[str] = None,
                    result_limit: int = 20,
                    count_passages_once: bool = True) -> Dict[str, Any]:
    """Semantic search via the notebook's run_similarity_search."""
    ns = ensure_loaded()
    with redirect_stdout(sys.stderr):
        cfg = ns['SearchConfig'](
            topics=[query],
            search_threshold=search_threshold,
            cluster_threshold=cluster_threshold,
            context_window=context_window,
            max_results_per_topic=max_results,
            filters=_make_filters(ns, filters),
            export_format=export_format,
            count_passages_once=count_passages_once,
        )
        results, cluster_info = ns['run_similarity_search'](
            query, cfg, ns['MODEL_DICT'], ns['ENCODER']
        )
        export_paths: List[str] = []
        if export and results:
            export_paths = _export(ns, query, results, cluster_info, cfg, file_stem=export_name)

    response = _format_response(results, cluster_info, result_limit, ns=ns)
    _guidance.annotate(response, (r.score for r in results))
    response.update({
        'query': query,
        'search_threshold': search_threshold,
        'pairs_merged': cluster_info.get('pairs_merged', 0),
        'cluster_threshold': cluster_threshold,
        'context_window': context_window,
        'filters': filters or {},
        'export_paths': export_paths,
    })
    return response


def keyword_search(keyword: str,
                   smart_boundaries: bool = True,
                   fuzzy_matching: bool = False,
                   fuzzy_threshold: int = 80,
                   context_window: int = 1,
                   filters: Optional[Dict] = None,
                   export: bool = False,
                   export_format: str = 'xlsx',
                   export_name: Optional[str] = None,
                   result_limit: int = 20,
                   count_passages_once: bool = True) -> Dict[str, Any]:
    """Exact/fuzzy keyword search via the notebook's run_keyword_search."""
    ns = ensure_loaded(semantic=False)
    with redirect_stdout(sys.stderr):
        cfg = ns['SearchConfig'](
            topics=[keyword],
            keyword_search=True,
            smart_boundaries=smart_boundaries,
            fuzzy_matching=fuzzy_matching,
            fuzzy_threshold=fuzzy_threshold,
            context_window=context_window,
            filters=_make_filters(ns, filters),
            export_format=export_format,
            count_passages_once=count_passages_once,
        )
        results, cluster_info = ns['run_keyword_search'](keyword, cfg, ns['MODEL_DICT'])
        export_paths: List[str] = []
        if export and results:
            export_paths = _export(ns, keyword, results, cluster_info, cfg, file_stem=export_name)

    response = _format_response(results, cluster_info, result_limit, ns=ns)
    response.update({
        'keyword': keyword,
        'smart_boundaries': smart_boundaries,
        'fuzzy_matching': fuzzy_matching,
        'pairs_merged': cluster_info.get('pairs_merged', 0),
        'context_window': context_window,
        'filters': filters or {},
        'export_paths': export_paths,
    })
    return response


def boolean_search(query: str,
                   scoring: str = 'match_count',
                   context_window: int = 1,
                   filters: Optional[Dict] = None,
                   export: bool = False,
                   export_format: str = 'xlsx',
                   export_name: Optional[str] = None,
                   result_limit: int = 20,
                   count_passages_once: bool = True) -> Dict[str, Any]:
    """Boolean keyword search (AND, OR, NOT, brackets, "phrases", * and ? wildcards) via the notebook's run_boolean_search."""
    ns = ensure_loaded(semantic=False)
    if scoring not in ('match_count', 'avg_score', 'max_score'):
        return {'error': f"scoring must be 'match_count', 'avg_score' or 'max_score', not {scoring!r}"}
    try:    # the notebook function prints a parse error and returns nothing; say so in the reply instead
        from _library.boolean_parser import BooleanQueryParser
        BooleanQueryParser().parse(query)
    except Exception as e:  # noqa: BLE001
        return {'error': f'Could not parse the Boolean query: {e}',
                'syntax': 'AND (&), OR (|), NOT (!), brackets, "exact phrase", wildcards * and ?; '
                          'example: (cyber* OR digital) AND "critical infrastructure" AND NOT terrorism'}
    with redirect_stdout(sys.stderr):
        cfg = ns['SearchConfig'](
            topics=[query],
            boolean_mode=True,
            boolean_scoring=scoring,
            context_window=context_window,
            filters=_make_filters(ns, filters),
            export_format=export_format,
            count_passages_once=count_passages_once,
        )
        results, cluster_info = ns['run_boolean_search'](query, cfg, ns['MODEL_DICT'])
        export_paths: List[str] = []
        if export and results:
            export_paths = _export(ns, query, results, cluster_info, cfg, file_stem=export_name)

    response = _format_response(results, cluster_info, result_limit, ns=ns)
    response.update({
        'query': query,
        'search_type': 'boolean',
        'scoring': scoring,
        'pairs_merged': cluster_info.get('pairs_merged', 0),
        'context_window': context_window,
        'filters': filters or {},
        'export_paths': export_paths,
    })
    return response


def filter_options() -> Dict[str, Any]:
    """Enumerate available values for every metadata filter field."""
    ns = load_namespace()
    metadata = ns['METADATA']
    doc_df = metadata['documents']

    def col(*candidates):
        for c in candidates:
            if c in doc_df.columns:
                return sorted({str(v) for v in doc_df[c].dropna().unique()})
        return []

    years = []
    for c in ('Year', 'year'):
        if c in doc_df.columns:
            years = [int(doc_df[c].min()), int(doc_df[c].max())]
            break

    return {
        'regions': sorted(metadata.get('unique_regions', [])),
        'subregions': sorted(metadata.get('unique_subregions', [])),
        'countries_iso3': sorted(set(metadata.get('regions', {}).keys())),
        'organizations': sorted(metadata.get('organizations', {}).keys()),
        'income_groups': sorted(set(metadata.get('income_groups', {}).values())),
        'freedom_house_status': sorted(set(metadata.get('freedom_house', {}).values())),
        'oda_status': sorted(set(metadata.get('oda_mapping', {}).values())),
        'small_states_groups': ['Small States', 'SSF', 'UN SIDS'],
        'huntington_civilizations': sorted(metadata.get('huntington_civilizations', [])),
        'doc_types': col('NSS/WP/DD', 'Type', 'type'),
        'year_range': years,
        'notes': ('Within a filter field values are OR; across fields AND. '
                  'countries take ISO3 codes; most_recent_only (bool) keeps each '
                  "country's most recent document only."),
    }


def corpus_summary() -> str:
    """One-line corpus size for tool descriptions, read from the loaded data (empty if unavailable)."""
    try:
        ns = _ns
        md = ns['MODEL_DICT']
        years = filter_options()['year_range']
        span = f', {years[0]}–{years[1]}' if years else ''
        return (f"{len(md['documents_dict']):,} national security documents "
                f"({len(md['countries_dict']):,} countries and territories{span}, "
                f"{len(md['segments_dict']):,} segments)")
    except Exception:
        return 'national security documents'


def corpus_stats() -> Dict[str, Any]:
    """Corpus statistics (loads the model if not yet loaded)."""
    ns = ensure_loaded(semantic=False)
    md = ns['MODEL_DICT']

    # v4.0 cross-lingual: per-segment language breakdown + alignment coverage
    languages: Dict[str, int] = {}
    label_map = ns.get('LANG_LABEL', {})
    for seg in md['segments_dict'].values():
        lang = (seg or {}).get('lang', 'en') if isinstance(seg, dict) else 'en'
        languages[lang] = languages.get(lang, 0) + 1
    language_breakdown = [
        {'language': k, 'label': label_map.get(k, k.upper()), 'segments': v}
        for k, v in sorted(languages.items(), key=lambda kv: kv[1], reverse=True)
    ]
    alignment_dict = md.get('alignment_dict', {})

    stats = {
        'documents': len(md['documents_dict']),
        'countries': len(md['countries_dict']),
        'segments_total': len(md['segments_dict']),
        'segments_encoded': len(md['encoded_segments']),
        'embedding_shape': list(md['segment_encodings'].shape),
        'model_path': str(ns.get('MODEL_PATH', '')),
        'metadata_path': str(ns.get('BASE_PATH', '')),
        'outputs_dir': str(OUTPUTS_DIR),
        'languages': len(languages),
        'language_breakdown': language_breakdown,
        'documents_with_alignment': len(alignment_dict),
        'cross_lingual': bool(alignment_dict),
    }
    return stats
