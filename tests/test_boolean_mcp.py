"""The MCP server and REST API offer Boolean search (AND, OR, NOT, brackets, phrases, wildcards)."""
import asyncio, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_server_local import engine, server


def test_boolean_search_is_listed_with_its_syntax():
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert 'boolean_search' in tools
    t = tools['boolean_search']
    assert t.inputSchema['required'] == ['query']
    assert all(w in t.description for w in ('AND', 'OR', 'NOT', 'wildcards'))


def test_bad_query_returns_an_error_not_an_empty_result(monkeypatch):
    monkeypatch.setattr(engine, 'ensure_loaded', lambda semantic=True: {})
    out = engine.boolean_search('cyber AND AND')
    assert 'Could not parse' in out['error'] and 'syntax' in out
    assert 'scoring' in engine.boolean_search('cyber', scoring='nonsense')['error']


def test_search_runs_the_notebook_boolean_search(monkeypatch):
    calls = {}

    class Cfg:
        def __init__(self, **kw): calls['cfg'] = kw

    ns = {'SearchConfig': Cfg, 'MODEL_DICT': {},
          'run_boolean_search': lambda q, cfg, md: (calls.setdefault('q', q) and [], {})}
    monkeypatch.setattr(engine, 'ensure_loaded', lambda semantic=True: ns)
    monkeypatch.setattr(engine, '_make_filters', lambda ns, f: f)
    monkeypatch.setattr(engine, '_format_response', lambda *a, **k: {'num_results': 0})
    out = engine.boolean_search('(cyber* OR digital) AND NOT terrorism', scoring='max_score')
    assert calls['q'] == '(cyber* OR digital) AND NOT terrorism'
    assert calls['cfg']['boolean_mode'] is True and calls['cfg']['boolean_scoring'] == 'max_score'
    assert out['search_type'] == 'boolean' and out['num_results'] == 0
