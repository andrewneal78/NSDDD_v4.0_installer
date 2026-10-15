"""Manual smoke test for the MCP server's startup modes (not collected by pytest: slow, loads the real model).

Starts mcp_server_local.server as a child process and talks MCP over stdio, timing each step:
initialize, tools/list, keyword_search, semantic_search. No MCP client needs to be installed.

Use the Python that runs the server (the installer's venv, or python\\python.exe in the Windows package):

    python tests/mcp_lazy_smoke.py 0     # default: model loads before the handshake
    python tests/mcp_lazy_smoke.py 1     # NSDDD_LAZY_LOAD=1: handshake first, model on the first search

Prints OK per step and PASS, or HANG and exit code 1 if a step gets no answer in time.
Server stderr goes to mcp_lazy_smoke_stderr_<mode>.txt in the installer folder.
Passed on macOS and Windows 11 on 2026-10-15 (Windows handshake 43 s model-first, 11 s lazy).
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mode = sys.argv[1] if len(sys.argv) > 1 else '1'
env = dict(os.environ, NSDDD_LAZY_LOAD=mode)

stderr_log = open(ROOT / f'mcp_lazy_smoke_stderr_{mode}.txt', 'w')
proc = subprocess.Popen([sys.executable, '-m', 'mcp_server_local.server'], cwd=ROOT, env=env,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_log,
                        text=True, encoding='utf-8')
lines = queue.Queue()
threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()
start = time.time()


def send(message):
    proc.stdin.write(json.dumps(message) + '\n')
    proc.stdin.flush()


def rpc(request_id, method, params, limit, label):
    send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
    began = time.time()
    while time.time() - began < limit:
        try:
            reply = json.loads(lines.get(timeout=1))
        except queue.Empty:
            continue
        if reply.get('id') == request_id:
            print(f'OK    {label}: {time.time() - began:.1f}s (total {time.time() - start:.1f}s)', flush=True)
            return reply
    print(f'HANG  {label}: no answer after {limit}s', flush=True)
    proc.kill()
    sys.exit(1)


print('NSDDD_LAZY_LOAD =', mode)
rpc(1, 'initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                      'clientInfo': {'name': 'smoke', 'version': '0'}}, 120, 'initialize')
send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
rpc(2, 'tools/list', {}, 120, 'tools/list')
rpc(3, 'tools/call', {'name': 'keyword_search', 'arguments': {'keyword': 'cyber', 'result_limit': 2}},
    300, 'keyword_search')
rpc(4, 'tools/call', {'name': 'semantic_search', 'arguments': {
    'query': 'States protect critical infrastructure from cyber attacks.', 'max_results': 3, 'result_limit': 3}},
    600, 'semantic_search')
print('PASS')
proc.kill()
