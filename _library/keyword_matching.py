"""One definition of what a keyword or Boolean term matches, and the full-text query that is exactly equivalent to it.

Keyword search, Boolean search and the SQLite prefilter used to define a match separately, so the same term gave different
results in each. Everything now comes from here.

A term is one or more words. A word is an exact word: 'security' does not match 'cybersecurity' or 'securities'.
- Between the words of a phrase there must be at least one separator, never none: 'cyber security' does not match
  'cybersecurity'. With smart=True (the default) a separator is a space, hyphen, slash or soft hyphen, so 'cyber security' also
  matches 'cyber-security'; a hyphen or slash typed in the query counts as a separator too ('counter-terrorism' matches
  'counter terrorism'). With smart=False a separator is white space only and a typed hyphen is literal.
- Boundaries are Unicode word boundaries: a match cannot start or end inside a word, whatever the script. Text in scripts
  written without spaces (Chinese, Japanese, Korean, Thai) is matched as a substring, because it has no word boundaries.
- Wildcards stay inside a word: * is any run of letters or digits (including none), ? is exactly one. cyber* finds cyber,
  cyberspace and cybersecurity; it never reaches across a space.
- Case is ignored.
- inside=True ('match inside words') drops the word-boundary rule: a word then also matches where it is part of a longer word
  ('Sicherheit' finds Sicherheitspolitik, 'hrung' finds Führung). Wildcards still stay inside a word. This cannot use the
  full-text index, so every segment in scope is scanned.

fts_query() returns the SQLite FTS5 query that finds every segment the pattern can match (and no segment that cannot match its
words), or None when the whole text must be scanned. Because each word is a separate full-text token, the prefilter is exact in
the sense that tests/test_keyword_matching.py checks: prefiltered and full-scan results are identical."""
import re

SEPARATORS = '\\s\\-/–—‑−­'
_SEP = '[' + SEPARATORS + ']+'
_UNSPACED = re.compile('[぀-ヿ㐀-鿿가-힯฀-๿]')
MATCH_NOTHING = re.compile(r'(?!)')


def split_words(term, smart=True):
    """The words of a term: split on separators when smart, on white space otherwise. Runs of * are collapsed."""
    parts = re.split(_SEP if smart else r'\s+', str(term or '').strip())
    return [re.sub(r'\*+', '*', p) for p in parts if p]


def _word_regex(word):
    return ''.join(r'\w*' if ch == '*' else r'\w' if ch == '?' else re.escape(ch) for ch in word)


def compile_term(term, smart=True, inside=False):
    """Compiled pattern for a term (see the module docstring). An empty term matches nothing; a word made only of wildcards is
    refused with ValueError, because it would match every segment."""
    words = split_words(term, smart)
    if not words:
        return MATCH_NOTHING
    for w in words:
        if not w.strip('*?'):
            raise ValueError(f'"{w}" has no letters or digits; a wildcard needs some text beside it, as in cyber*')
    body = (_SEP if smart else r'\s+').join(_word_regex(w) for w in words)
    if not inside and not _UNSPACED.search(str(term)):
        if re.match(r'[\w*?]', words[0]):
            body = r'(?<!\w)' + body
        if re.search(r'[\w*?]$', words[-1]):
            body += r'(?!\w)'
    return re.compile(body, re.IGNORECASE)


_ITEM = re.compile(r'[^\W_]+|[*?]|.', re.S)


def fts_query(term, smart=True, inside=False):
    """FTS5 query selecting every segment that can match `term`, or None when no safe query exists (then scan everything).

    Each word contributes the letters-and-digits runs that must be whole tokens of the text: a run is an exact token unless a
    wildcard follows it in the word (then a prefix), and a run that a wildcard may extend at the front is not used."""
    if inside or _UNSPACED.search(str(term or '')):
        return None
    parts = []
    for word in split_words(term, smart):
        items = [m.group() for m in _ITEM.finditer(word)]
        open_front = False                                  # True while a wildcard may still extend the next run at its front
        for k, item in enumerate(items):
            if item in ('*', '?'):
                open_front = True
            elif re.fullmatch(r'[^\W_]+', item):
                if not open_front:
                    followed = k + 1 < len(items) and items[k + 1] in ('*', '?')
                    parts.append('"%s"%s' % (item, '*' if followed else ''))
                open_front = False
            else:                                           # a literal punctuation mark ends the token and starts a new one
                open_front = False
    seen, unique = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return ' AND '.join(unique) or None
