"""Segment texts read from SQLite on demand, so the search app does not hold ~1.9 GB of text in memory.

SegmentStore behaves like the dict the app used before (segments_dict): get / [] / in / items() / keys() / len(),
each value being {'text': ..., 'lang': ...}. subset(docs) gives a view limited to some documents (Boolean search).
"""
import re
import sqlite3
import threading


class SegmentStore:
    def __init__(self, path, docs=None):
        self.path = str(path)
        self.docs = None if docs is None else {str(d) for d in docs}
        self._local = threading.local()

    def _con(self):
        con = getattr(self._local, 'con', None)
        if con is None:
            con = self._local.con = sqlite3.connect(self.path, check_same_thread=False)
        return con

    def _in_scope(self, key):
        return self.docs is None or str(key).split('/')[0] in self.docs

    def _where(self):
        if self.docs is None:
            return '', ()
        return ' WHERE doc IN (%s)' % ','.join('?' * len(self.docs)), tuple(self.docs)

    def get(self, key, default=None):
        if not isinstance(key, str) or not self._in_scope(key):
            return default
        row = self._con().execute('SELECT text, lang FROM seg WHERE id = ?', (key,)).fetchone()
        return {'text': row[0], 'lang': row[1]} if row else default

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key):
        if not isinstance(key, str) or not self._in_scope(key):
            return False
        return self._con().execute('SELECT 1 FROM seg WHERE id = ?', (key,)).fetchone() is not None

    def items(self):
        where, args = self._where()
        cur = self._con().cursor()
        for sid, text, lang in cur.execute('SELECT id, text, lang FROM seg' + where + ' ORDER BY row', args):
            yield sid, {'text': text, 'lang': lang}

    def keys(self):
        return (k for k, _ in self.items())

    def values(self):
        return (v for _, v in self.items())

    def __iter__(self):
        return self.keys()

    def __len__(self):
        where, args = self._where()
        return self._con().execute('SELECT COUNT(*) FROM seg' + where, args).fetchone()[0]

    def subset(self, docs):
        return SegmentStore(self.path, docs)


_UNSPACED = re.compile(r'[぀-ヿ㐀-鿿가-힯฀-๿]')


def _fts_query(keyword):
    """FTS5 query from an app keyword ('Innere Führung', 'resilien*', 'defen?e'): every literal word must occur
    (a word next to a wildcard as a prefix). None when no usable word (the caller then scans everything)."""
    parts = []
    for tok in re.split(r'\s+', keyword.strip()):
        m = re.match(r'^([^\W_]{2,})', tok.replace('?', '*'))
        if not m:
            continue
        word = m.group(1)
        prefix = len(word) < len(re.sub(r'[^\w*?]', '', tok)) or '*' in tok or '?' in tok
        parts.append('"%s"%s' % (word.replace('"', ''), '*' if prefix else ''))
    return ' AND '.join(parts) or None


def _candidates(self, keyword):
    """Segments that may match a keyword, from the full-text index (unicode61: case-folded for every script,
    accents kept); the caller confirms each with its own pattern. Falls back to every segment for unspaced
    scripts (Chinese, Japanese, Korean, Thai), when the index is missing, or when no literal word is given."""
    q = _fts_query(keyword)
    con = self._con()
    has_fts = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'seg_fts'").fetchone()
    if not q or not has_fts or _UNSPACED.search(keyword):
        yield from self.items()
        return
    where, args = self._where()
    sql = ('SELECT seg.id, seg.text, seg.lang FROM seg_fts JOIN seg ON seg.rowid = seg_fts.rowid '
           'WHERE seg_fts MATCH ?' + where.replace(' WHERE doc', ' AND seg.doc') + ' ORDER BY seg.row')
    for sid, text, lang in con.execute(sql, (q,) + args):
        yield sid, {'text': text, 'lang': lang}


SegmentStore.candidates = _candidates


def build_fts(path):
    """Add the full-text index to a segments.sqlite (build_search_index_qwen3.py calls this)."""
    con = sqlite3.connect(str(path))
    con.execute('DROP TABLE IF EXISTS seg_fts')
    con.execute("CREATE VIRTUAL TABLE seg_fts USING fts5(text, content='seg', content_rowid='rowid', "
                "tokenize='unicode61 remove_diacritics 0')")
    con.execute('INSERT INTO seg_fts(rowid, text) SELECT rowid, text FROM seg')
    con.commit()
    con.close()
