"""Generate absent document viewers from the installed SQLite texts and alignments.

Existing supplied viewers are preserved. Generation streams one document at a time.
"""
import json
import sqlite3
from html import escape
from pathlib import Path

STYLE = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>body{font:18px/1.6 system-ui;max-width:1200px;margin:30px auto;padding:0 20px}p{scroll-margin:30px}
.target{background:#fff3a6}table{width:100%;table-layout:fixed}td{vertical-align:top;padding:10px;overflow-wrap:anywhere}
</style></head><body>'''
SCRIPT = '''<script>const id=new URLSearchParams(location.search).get('segment');
const el=document.getElementById(id);if(el){el.classList.add('target');el.scrollIntoView({block:'center'});}</script></body></html>'''


def ensure_viewers(model_dir, destination):
    model_dir, destination = Path(model_dir), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    docs = json.loads((model_dir / 'documents_dict.json').read_text(encoding='utf-8'))
    align = json.loads((model_dir / 'alignment_dict.json').read_text(encoding='utf-8'))
    created = 0
    with sqlite3.connect((model_dir / 'segments.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as con:
        original_docs = {r[0] for r in con.execute("SELECT DISTINCT doc FROM seg WHERE id LIKE '%/o/%'")}
        for doc, info in docs.items():
            if not str(doc).isdigit():
                raise ValueError('Invalid document ID in viewer filename')
            variants = [(f'{doc}.html', False)]
            if doc in original_docs:
                variants.append((f'{doc}_original.html', True))
            for filename, original in variants:
                path = destination / filename
                if path.is_file() and path.stat().st_size:
                    continue
                with path.with_suffix('.tmp').open('w', encoding='utf-8') as f:
                    f.write(STYLE + '<h1>' + escape(info.get('name', doc)) + '</h1>')
                    for sid, text in con.execute('SELECT id,text FROM seg WHERE doc=? ORDER BY row', (doc,)):
                        if ('/o/' in sid) == original:
                            f.write(f'<p id="{escape(sid.rsplit("/",1)[1], quote=True)}">{escape(text)}</p>\n')
                    f.write(SCRIPT)
                path.with_suffix('.tmp').replace(path)
                created += 1
            path = destination / f'{doc}_bilingual.html'
            if doc not in align or (path.is_file() and path.stat().st_size):
                continue
            texts = dict(con.execute('SELECT id,text FROM seg WHERE doc=?', (doc,)))
            def paragraph(sid, prefix):
                return f'<p id="{prefix}{escape(sid.rsplit("/",1)[1], quote=True)}">{escape(texts.get(sid, ""))}</p>'
            with path.with_suffix('.tmp').open('w', encoding='utf-8') as f:
                f.write(STYLE + '<h1>' + escape(info.get('name', doc)) + '</h1><table><thead><tr><th>Original</th><th>English</th></tr></thead><tbody>')
                seen = set()
                for original, english, *_ in align[doc]:
                    f.write('<tr><td>' + ''.join(paragraph(s, 'o') for s in original) + '</td><td>' +
                            ''.join(paragraph(s, 'e') for s in english) + '</td></tr>')
                    seen.update(original + english)
                # Preserve any unaligned sentences too, including deep links.
                for sid in texts.keys() - seen:
                    f.write('<tr><td>' + (paragraph(sid, 'o') if '/o/' in sid else '') + '</td><td>' +
                            (paragraph(sid, 'e') if '/o/' not in sid else '') + '</td></tr>')
                f.write('</tbody></table>' + SCRIPT)
            path.with_suffix('.tmp').replace(path)
            created += 1
    return created
