"""Cluster headings written by a small local language model (Qwen3-0.6B, 4-bit GGUF, about 520 MB).

Chosen over keywords, precomputed topics and phrase extraction in the 2026-10 label tests (72 clusters, blind judge:
about 55 wins to 10 against keyword headings). Everything here is optional and user-initiated (the 'Add AI headings'
button): if the model file or the runtime is missing, `label_clusters` returns nothing. The app never falls back to
keyword headings; a cluster without an AI heading simply keeps its number.

Rules applied to every heading (rule set C of the tests; minimum 3 words from 2026-10-02, 2 words from 2026-10-04): 2 to 8 words; no list marker, markdown, digits, colon or
verb; not made of generic words only; not in capitals; and not a near-copy of another heading in the same search
(content-word overlap of 60% or more). A rejected heading is regenerated from a different set of the cluster's
sentences (up to 8 tries); a cluster with no acceptable heading is left out of the result and the caller keeps its number.
The sentences the model reads are distinct (no identical sentence twice, no near copies, at most 2 per document).
"""
import os, re, time
from pathlib import Path

MODEL_FILE = 'qwen3-0.6b-q4_k_m.gguf'
OLLAMA_MODEL = 'qwen3:0.6b'

# ============================================================================================================
# THE RULES: edit here. A heading that breaks any rule is thrown away and the model tries again from a different
# set of the cluster's sentences (TRIES times); if nothing passes, the cluster keeps its keyword heading.
# ============================================================================================================
MIN_WORDS = 2              # fewest words in a heading (3 until 2026-10-04; two-word headings allowed at the editor's request)
MAX_WORDS = 8              # most words in a heading
BAN_COUNTRIES = True       # no country or nationality in a heading (names from the ISO list, plus aliases and nationalities below)
BAN_ALL_CAPS = True        # no heading in capitals, and no all-caps word of 6+ letters (short acronyms such as NATO, WMD are fine)
BAN_GENERIC_ONLY = True    # a heading must contain a word that is not on the GENERIC list below
BAN_VERBS = True           # no 'is', 'includes', 'discusses', ... (a heading names a subject, it does not state something)
BAN_IMPERATIVE_START = True  # a heading must not open with an instruction such as 'Develop ...' or 'Ensure ...'
BAN_REPEATED_WORD = True   # no word used twice within one heading
FORBIDDEN_CHARS = r'[:;()\[\]\d&/]'  # no colon, semicolon, brackets, digits, ampersand or slash (commas are allowed)
BAN_NON_ENGLISH = True     # headings are English: no accented or non-Latin letters, no foreign function words, no word cut off at a hyphen
BAN_INSTRUCTION_ECHO = True  # no heading that repeats the model's instructions ('aspect of the topic', 'these sentences', ...)
MAX_COMMAS = 2             # more commas than this means the model copied a list out of a sentence
MAX_OVERLAP = 0.6          # a heading may share at most this fraction of its content words with another heading in the same search
                           # (generic words such as 'issues' and 'challenges', and synonyms such as 'impacts' and 'effects', are ignored in this comparison)
SENTENCE_CASE = True       # write every heading in sentence case ('Climate change effects'); acronyms and the PROPER words below keep their capitals
# How the model is run (changing these changes speed, memory and quality):
TRIES = 16                 # attempts per cluster before it keeps its number (8 left about 8% of clusters unnamed)
N_SENT = 6                 # sentences shown to the model per cluster
N_CHAR = 150               # characters of each sentence shown
N_CTX = 1024               # model context window (tokens)
# ============================================================================================================

PROPER = {'Arctic', 'Antarctic', 'Pacific', 'Atlantic', 'Indian', 'Baltic', 'Mediterranean', 'Black', 'Sea', 'Gulf', 'Middle', 'East', 'West',
          'Asia', 'Asian', 'Europe', 'European', 'Africa', 'African', 'Sahel', 'Balkans', 'Caribbean', 'Indo-Pacific', 'Asia-Pacific', 'Eurasia',
          'Islamic', 'Cold', 'War', 'Nordic', 'Latin', 'Western', 'Eastern', 'Northern', 'Southern', 'Euro-Atlantic', 'Quadrennial'}
SYNONYMS = {'impact', 'impacts', 'effect', 'effects', 'consequence', 'consequences', 'implication', 'implications', 'concern', 'concerns',
            'pressure', 'pressures', 'problem', 'problems', 'dimension', 'dimensions', 'aspect', 'aspects'}
NON_ENGLISH_WORDS = set('sikkerhet sikkerhed klima klimaendringer klimaendringen klimaforandringer klimat sicherheit klimawandel seguridad sécurité securite og och der die das und det den har som med för är ikke ett eine einer des les une aux dans pour sur est sont el los las del por para con una et'.split())
ECHO = re.compile(r'\b(the\s+documents?|aspects?\s+of\s+the\s+topic|these\s+sentences|the\s+sentences|the\s+topic|headline|heading|sentence\s+group|two\s+to\s+eight)\b', re.I)

STOP = set('the of and in on for to a an by with against from as at its their security national threats threat policy'.split())
GENERIC = {'threat', 'threats', 'security', 'national', 'defence', 'defense', 'risk', 'risks', 'challenge', 'challenges',
           'issue', 'issues', 'will', 'must', 'need', 'needs', 'also', 'new', 'level', 'levels', 'order', 'role', 'support',
           'development', 'way', 'ways', 'part', 'particular', 'use', 'year', 'years', 'time', 'country', 'countries',
           'state', 'states', 'government', 'nation', 'nations', 'people', 'current', 'today', 'future', 'increasing',
           'increasingly', 'significant', 'major', 'main', 'key', 'general', 'related', 'different', 'based', 'number',
           'high', 'potential', 'situation', 'context', 'factors', 'factor', 'aspects', 'terms', 'possible', 'could',
           'would', 'section', 'chapter', 'paper', 'form', 'defined', 'implications', 'concept', 'one', 'two', 'many',
           'such', 'may', 'well', 'including', 'within', 'among', 'important', 'ensure', 'ensuring', 'provide', 'provides'}
VERB = (r'\b(discuss\w*|includ\w*|states|says|is|are|was|were|has|have|had|will|would|can|could|may|must|should|'
        r'contribut\w+|requir\w+|provid\w+|increasingly|focus on|continues?|evolves?|remains?|poses?|demands?|'
        r'destabili[sz]es|threatens|guarantees|expands|adds|ensures|enables|reflects|highlights|undermines|enhances|integrates|strengthens|promotes|supports|addresses|reinforces|shapes|drives|exacerbates|fuels|consider|considers|heightens|worsens|deepens|reshaped|reshapes|intensifies|amplifies|multiplies|causes|leads|creates|increases\s+(?!in\b|of\b)\w+|impacts?\s+(?!of\b|on\b|from\b|for\b|and\b|in\b|to\b)\w+)\b')
IMPERATIVE = {'develop', 'ensure', 'strengthen', 'promote', 'enhance', 'maintain', 'protect', 'prevent', 'improve', 'build',
              'support', 'address', 'combat', 'reduce', 'increase', 'establish', 'implement', 'continue', 'expand', 'invest',
              'encourage', 'foster', 'add', 'guarantee', 'enable', 'reflect', 'deter', 'counter', 'safeguard', 'respond', 'prepare', 'adapt', 'secure'}
SYSTEM = ('You write headings for groups of sentences from national security policy documents. '
          f'Reply with the heading ONLY: {MIN_WORDS} to {MAX_WORDS} words, no quotes, no list marker, no markdown, '
          "not a sentence, no verb phrase such as 'discusses' or 'includes'. Name the specific subject."
          + (' Do not name any country or nationality.' if BAN_COUNTRIES else ''))

_state = {'llm': None, 'backend': None, 'note': None, 'tried': False, 'resource': None}


def _toks(s):
    return {w for w in re.findall(r'[a-z]+', s.lower()) if w not in STOP}


def _dtoks(s):
    """Content words for the near-copy test: without generic words or synonyms ('issues', 'effects', ...)."""
    t = {w for w in _toks(s) if w not in GENERIC and w not in SYNONYMS}
    return t or _toks(s)


def _words(s):
    return set(re.sub(r'[^a-z0-9 ]', '', s.lower()).split())


def distinct(sentences, n, per_doc=2, jmax=0.6):
    """sentences: [(text, document_id)] most central first. Keeps up to n that are not identical or near copies."""
    keep, docs, exact = [], {}, set()
    for text, doc in sentences:
        w = _words(text)
        if not w or frozenset(w) in exact or docs.get(doc, 0) >= per_doc:
            continue
        if any(len(w & _words(k)) / max(1, len(w | _words(k))) >= jmax for k, _ in keep):
            continue
        exact.add(frozenset(w)); docs[doc] = docs.get(doc, 0) + 1; keep.append((text, doc))
        if len(keep) == n:
            break
    return [t for t, _ in keep]


def _sentence_case(s):
    letters = [c for c in s if c.isalpha()]
    return s[:1] + s[1:].lower() if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6 else s


def _case(t):
    """Sentence case: first word capitalised; later words lower-case unless they are acronyms or in PROPER."""
    if not SENTENCE_CASE:
        return t
    out = []
    for i, w in enumerate(t.split()):
        core = re.sub(r'[^A-Za-z-]', '', w)
        if i == 0 or (core.isupper() and len(core) > 1) or core.title() in PROPER or core in PROPER:
            out.append(w)
        else:
            out.append(w.lower() if core[:1].isupper() else w)
    return ' '.join(out)


def _clean(t):
    t = t.strip().split('\n')[0].replace('\u2019', "'")
    t = re.sub(r'^[\s\-\*#\d\.\)]+', '', t).replace('**', '').strip(' "\'*.:;,')
    t = re.sub(r'^(heading|title|label)\s*:\s*', '', t, flags=re.I)
    t = t[:1].upper() + t[1:]
    return _case(t)


ALIASES = ['USA', 'US', 'U.S.', 'U.S.A.', 'UK', 'U.K.', 'PRC', 'DPRK', 'ROK', 'UAE', 'America', 'Britain', 'Great Britain',
           'England', 'Scotland', 'Wales', 'Russia', 'Iran', 'Syria', 'Vietnam', 'Laos', 'Taiwan', 'Czechia', 'Czech Republic',
           'Korea', 'North Korea', 'South Korea', 'Burma', 'Turkey', 'Turkiye', 'Holland', 'Macedonia', 'Kosovo', 'Palestine',
           'Americas', 'Tibet', 'Hong Kong', 'Macau', 'Bolivia', 'Venezuela', 'Tanzania', 'Moldova', 'Brunei', 'Ivory Coast', 'Cape Verde']
NATIONALITIES = ['American', 'British', 'Chinese', 'Russian', 'Japanese', 'Korean', 'Indian', 'French', 'German', 'Italian', 'Spanish',
                 'Canadian', 'Australian', 'New Zealand', 'Norwegian', 'Swedish', 'Danish', 'Finnish', 'Icelandic', 'Dutch', 'Belgian',
                 'Swiss', 'Austrian', 'Polish', 'Czech', 'Slovak', 'Slovenian', 'Croatian', 'Serbian', 'Bosnian', 'Hungarian',
                 'Romanian', 'Bulgarian', 'Greek', 'Turkish', 'Cypriot', 'Maltese', 'Irish', 'Portuguese', 'Estonian', 'Latvian',
                 'Lithuanian', 'Ukrainian', 'Belarusian', 'Georgian', 'Armenian', 'Azerbaijani', 'Kazakh', 'Uzbek', 'Kyrgyz', 'Tajik',
                 'Turkmen', 'Mongolian', 'Iranian', 'Iraqi', 'Syrian', 'Israeli', 'Saudi', 'Emirati', 'Qatari', 'Kuwaiti', 'Omani',
                 'Yemeni', 'Jordanian', 'Lebanese', 'Palestinian', 'Egyptian', 'Libyan', 'Tunisian', 'Algerian', 'Moroccan', 'Sudanese',
                 'Nigerian', 'Kenyan', 'Ethiopian', 'Somali', 'Ugandan', 'Ghanaian', 'Senegalese', 'Congolese', 'Angolan', 'Zimbabwean',
                 'South African', 'Pakistani', 'Afghan', 'Bangladeshi', 'Nepalese', 'Nepali', 'Sri Lankan', 'Burmese', 'Thai', 'Vietnamese',
                 'Cambodian', 'Laotian', 'Indonesian', 'Malaysian', 'Singaporean', 'Filipino', 'Philippine', 'Taiwanese', 'Mexican',
                 'Brazilian', 'Argentine', 'Argentinian', 'Chilean', 'Colombian', 'Peruvian', 'Venezuelan', 'Cuban', 'Albanian',
                 'Macedonian', 'Montenegrin', 'Kosovan', 'Moldovan', 'Luxembourg', 'Slovene', 'Haitian', 'Jamaican', 'Panamanian',
                 'Fijian', 'Samoan', 'Tongan', 'Bahraini', 'Maldivian', 'Bhutanese', 'Mauritian', 'Gabonese', 'Cameroonian', 'Rwandan',
                 'Burundian', 'Malawian', 'Zambian', 'Namibian', 'Mozambican', 'Malagasy', 'Ivorian', 'Malian', 'Chadian', 'Eritrean',
                 'Djiboutian', 'Liberian', 'Beninese', 'Togolese', 'Gambian', 'Guinean', 'Sierra Leonean', 'Mauritanian', 'Bolivian',
                 'Ecuadorian', 'Paraguayan', 'Uruguayan', 'Guatemalan', 'Honduran', 'Salvadoran', 'Nicaraguan', 'Costa Rican',
                 'Dominican', 'Trinidadian', 'Guyanese', 'Surinamese', 'Barbadian', 'Bahamian', 'Belizean', 'Bruneian', 'Timorese',
                 'Papua New Guinean', 'Solomon Islander', 'Vanuatuan', 'Liechtenstein', 'Monégasque', 'Andorran', 'Sammarinese']
_ACRONYMS = {'USA', 'US', 'U.S.', 'U.S.A.', 'UK', 'U.K.', 'PRC', 'DPRK', 'ROK', 'UAE'}      # matched case-sensitively
_country = {'ci': None, 'cs': None, 'dir': object()}


def _country_patterns(model_dir):
    """Names of every country in the ISO list (metadata/ISO-3166-Countries-with-Regional-Codes.csv), plus the aliases and
    nationalities above, as two regexes (case-insensitive names; case-sensitive acronyms)."""
    if _country['dir'] == str(model_dir):
        return _country['ci'], _country['cs']
    names = set(ALIASES) | set(NATIONALITIES)
    try:
        import csv
        iso = Path(model_dir).parent / 'metadata' / 'ISO-3166-Countries-with-Regional-Codes.csv'
        with open(iso, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                n = row['name']
                names |= {n, n.split('(')[0].strip(), n.split(',')[0].strip()}
    except Exception:
        pass                                                      # no ISO file: the aliases and nationalities still apply
    names = {n for n in names if len(n) > 2 or n in _ACRONYMS}
    ci = sorted((n for n in names if n not in _ACRONYMS), key=len, reverse=True)
    cs = sorted((n for n in names if n in _ACRONYMS), key=len, reverse=True)
    mk = lambda ns, fl: re.compile(r'(?<![A-Za-z])(?:' + '|'.join(re.escape(n) for n in ns) + r')(?![A-Za-z])', fl) if ns else None
    _country.update(ci=mk(ci, re.I), cs=mk(cs, 0), dir=str(model_dir))
    return _country['ci'], _country['cs']


def _names_country(t):
    return any(rx and rx.search(t) for rx in (_country['ci'], _country['cs']))


def _english(t):
    words = re.findall(r"[^\W\d_]+", t)
    return (not re.search(r'[^\x00-\x7f]', t)                      # accented or non-Latin letters (ä, ø, å, é, ...)
            and not re.search(r'[A-Za-z]-(\s|$)', t)                # 'Klima- og ...': a word cut off at a hyphen
            and not any(w.lower() in NON_ENGLISH_WORDS for w in words))


def _valid(t):
    words = t.split()
    content = [w.lower() for w in words if w.lower() not in STOP]
    caps = (t.upper() == t and any(c.isalpha() for c in t)) or any(
        w.isupper() and len(w) > 5 for w in re.findall(r'[A-Za-z]{2,}', t))
    return (MIN_WORDS <= len(words) <= MAX_WORDS
            and not re.search(FORBIDDEN_CHARS, t)
            and not re.match(r'(st|nd|rd|th)-', t, re.I)                               # a cut-off '21st-century'
            and not (BAN_ALL_CAPS and caps)
            and not (BAN_VERBS and re.search(VERB, t, re.I))
            and not (BAN_IMPERATIVE_START and words and words[0].lower() in IMPERATIVE)
            and not (BAN_GENERIC_ONLY and not any(w not in GENERIC for w in _toks(t)))
            and not (BAN_REPEATED_WORD and len(set(content)) < len(content))
            and not (BAN_NON_ENGLISH and not _english(t))
            and not (BAN_INSTRUCTION_ECHO and ECHO.search(t))
            and t.count(',') <= MAX_COMMAS
            and not (BAN_COUNTRIES and _names_country(t)))


# ---------------------------------------------------------------- model backends
def _load(model_dir):
    """Prefer llama.cpp with the bundled GGUF; fall back to a running Ollama; else report why not."""
    if _state['tried']:
        return _state['llm']
    _state['tried'] = True
    gguf = Path(model_dir) / 'label_model' / MODEL_FILE if model_dir else None
    try:
        from llama_cpp import Llama
        if gguf and gguf.exists():
            threads = int(os.environ.get('NSDDD_THREADS', min(4, os.cpu_count() or 2)))
            llm = Llama(model_path=str(gguf), n_ctx=N_CTX, n_threads=threads, n_gpu_layers=-1, verbose=False)

            _state['resource'] = llm
            import atexit
            if not _state.get('cleanup_registered'):
                atexit.register(unload)
                _state['cleanup_registered'] = True
            def generate(p, t, seed):
                c = llm.create_completion(p, max_tokens=24, temperature=t, seed=seed, stop=['\n', '<|im_end|>'])['choices'][0]
                return '' if c.get('finish_reason') == 'length' else c['text']     # a heading cut off at the token limit is thrown away
            _state.update(llm=generate,
                          backend='llama.cpp', note=None)
            return _state['llm']
        _state['note'] = f'label model file not found ({gguf})'
    except ImportError:
        _state['note'] = 'llama-cpp-python is not installed'
    except Exception as e:                                           # a broken model file or runtime must never break a search
        _state['note'] = f'label model failed to load: {e}'
    try:
        import requests
        if requests.get('http://localhost:11434/api/tags', timeout=1).ok:
            def ollama(p, t, seed):
                r = requests.post('http://localhost:11434/api/generate', json={
                    'model': OLLAMA_MODEL, 'prompt': p, 'raw': True, 'stream': False, 'keep_alive': '10m',
                    'options': {'temperature': t, 'seed': seed, 'num_predict': 24, 'stop': ['\n', '<|im_end|>'], 'num_ctx': N_CTX}},
                    timeout=60).json()
                return r.get('response', '')
            ollama('<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n', 0.0, 1)       # fails fast if the model is absent
            _state.update(llm=ollama, backend='ollama', note=None)
    except Exception:
        pass
    return _state['llm']


def status(model_dir=None):
    """(available, message) without loading the model."""
    gguf = Path(model_dir) / 'label_model' / MODEL_FILE if model_dir else None
    try:
        import llama_cpp  # noqa: F401
        has_rt = True
    except Exception:
        has_rt = False
    if has_rt and gguf and gguf.exists():
        return True, 'small local model (llama.cpp)'
    return False, 'AI headings need llama-cpp-python and the label model file, which are not installed'


HINT = ('Write a noun phrase of two to eight words, with no verb, that names the specific aspect of the topic '
        'these sentences cover, not just the topic itself.')
HINT_LOOSE = ('The headline must be two to eight words and must say what the sentences add to the topic, '
              'not just repeat the topic itself.')
HINT_AFTER, HINT_LOOSE_AFTER = 3, 9      # tries from the 4th add HINT; from the 10th HINT_LOOSE (earlier tries: the plain prompt)


def _prompt(sentences, hint=0):
    body = ('Sentences:\n' + '\n'.join('- ' + _sentence_case(s[:N_CHAR]) for s in sentences)
            + ({0: '', 1: '\n\n' + HINT, 2: '\n\n' + HINT_LOOSE}[hint]) + '\n\nHeading:')
    return (f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{body}<|im_end|>\n'
            '<|im_start|>assistant\n<think>\n\n</think>\n\n')


def _label_clusters(clusters, model_dir, budget_s=None, progress=None):
    """clusters: [{'id', 'size', 'sentences': [(text, document_id)] most central first}].
    Returns {id: heading} for the clusters that got an acceptable one; the others keep their numbers (the caller's job).
    budget_s=None means no time limit. progress(done, total, named) is called after each cluster."""
    gen = _load(model_dir)
    if gen is None:
        return {}
    import random
    _country_patterns(model_dir)
    t0, used, out = time.time(), [], {}
    ordered = sorted(clusters, key=lambda c: -c['size'])             # largest first: they pick their headings first
    for done, c in enumerate(ordered):
        if progress:
            progress(done, len(ordered), len(out))
        if budget_s is not None and time.time() - t0 > budget_s:
            break
        pool = distinct(c['sentences'], 40)
        if not pool:
            continue
        rnd = random.Random(c['size'])
        views = [pool[:N_SENT]] + [rnd.sample(pool, min(N_SENT, len(pool))) for _ in range(TRIES - 1)]
        for k, view in enumerate(views):
            if budget_s is not None and time.time() - t0 >= budget_s:
                break
            try:
                cand = _clean(gen(_prompt(view, hint=0 if k < HINT_AFTER else (1 if k < HINT_LOOSE_AFTER else 2)), 0.0 if k == 0 else 0.7, 1 + k))
            except Exception:
                break
            tk = _dtoks(cand)
            dup = any(len(tk & _dtoks(u)) / max(1, len(tk | _dtoks(u))) >= MAX_OVERLAP or cand.lower() == u.lower() for u in used)
            if _valid(cand) and not dup:
                out[c['id']] = cand; used.append(cand)
                break
    if progress:
        progress(len(ordered), len(ordered), len(out))
    return out


def unload():
    """Release native heading-model memory, including the completion closure."""
    resource = _state.get('resource')
    _state.update(llm=None, resource=None, backend=None, tried=False)
    if resource is not None:
        try:
            resource.close()
        except Exception:
            pass


def label_clusters(clusters, model_dir, budget_s=None, progress=None):
    try:
        return _label_clusters(clusters, model_dir, budget_s=budget_s, progress=progress)
    finally:
        unload()
