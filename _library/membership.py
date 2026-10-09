"""Organisation membership over time, read from the metadata CSVs (standard library only).

Each file lists, per country, rows such as 'M, joined 1973' and 'Left, year left 2020'. A country's history is a list of
membership intervals (first_year, year_left_or_None); an open interval means a current member.

Conventions
- A document counts as written by a member when first_year <= publication year < year_left. Accession year is inclusive,
  year of leaving exclusive. A document published in the year of accession may predate it; the year is all we have.
- A suspended member remains a member (Honduras in the OAS 2009 to 2011, African Union members after a coup, New Zealand in
  ANZUS 1986 to 2007): suspension removes participation, not membership.
- Observers, dialogue partners, partners for co-operation and associate members are not members. A row for one ends any
  open membership in that year (India was an SCO observer from 2005 and a member from 2017).
- A row with a year left and no year joined ends the open membership: 'Left', 'Withdraw', and 'OCT' (Greenland left the
  EU's predecessor in 1985 and is now an overseas territory).
- The CIS and G77 files have their own layouts and are read by their own functions.
- SCG (the State Union of Serbia and Montenegro, 2003 to 2006): where a file has no rows for it, SCG takes the history of Serbia,
  the continuator state, for years up to 2006 (as the OSCE file does for 1973 onwards). Where a file has its own SCG rows
  (UN.csv: 2000 to 2006) those are used.
"""
import csv
import re
from pathlib import Path

MEMBER = {'m', 'member', 'full member', 'permanent member', 'participating country', 'ldc', 're-admitted',
          'non-enumerated member'}
SUSPENDED = {'suspended'}
PREDECESSOR = {'SCG': ('SRB', 2006)}          # iso -> (continuator, last year it applies)


def _year(v):
    v = (v or '').strip()
    return int(v) if re.fullmatch(r'\d{4}', v) else None


def _col(cols, *needles, exclude=()):
    for c in cols:
        low = c.lower()
        if all(n in low for n in needles) and not any(x in low for x in exclude):
            return c
    return None


def _build(events):
    """events: [(year, kind)] with kind 'join' | 'end' | ('closed', end_year). Returns sorted intervals."""
    out, open_ = [], None
    for year, kind in sorted(events, key=lambda e: (e[0], 0 if e[1] == 'end' else 1)):
        if isinstance(kind, tuple):
            out.append((year, kind[1]))
        elif kind == 'join':
            if open_ is None:
                open_ = year
        elif open_ is not None:                # 'end'
            out.append((open_, year))
            open_ = None
    if open_ is not None:
        out.append((open_, None))
    return sorted(out, key=lambda iv: iv[0])


def _read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def _load_standard(path):
    rows = _read(path)
    if not rows:
        return {}
    cols = list(rows[0].keys())
    iso_c = _col(cols, 'iso')
    st_c = _col(cols, 'status')
    jc = _col(cols, 'joined')
    lc = _col(cols, 'left')
    ev = {}
    for r in rows:
        iso = (r.get(iso_c) or '').strip()
        if not iso:
            continue
        status = (r.get(st_c) or 'M').strip().lower() if st_c else 'm'
        j, l = _year(r.get(jc)), _year(r.get(lc))
        e = ev.setdefault(iso, [])
        if status in SUSPENDED:                  # suspension changes nothing, but a join year on the row still counts
            if j:
                e.append((j, 'join'))
            continue
        if status in MEMBER:
            if j and l:
                e.append((j, ('closed', l)))
            elif j:
                e.append((j, 'join'))
            elif l:
                e.append((l, 'end'))
        elif j:                                  # observer, partner, associate...: ends membership when it starts
            e.append((j, 'end'))
        elif l:                                  # Left, Withdraw, OCT
            e.append((l, 'end'))
    return {iso: _build(e) for iso, e in ev.items()}


def _load_g77(path):
    """Columns Member (year joined), Former (year left), Associate. Mexico has two rows (1964; rejoined 2023)."""
    ev = {}
    for r in _read(path):
        iso = (r.get('ISO-Alpha3 Code') or '').strip()
        j, l = _year(r.get('Member')), _year(r.get('Former'))
        if not iso or not j:
            continue
        ev.setdefault(iso, []).append((j, ('closed', l) if l else 'join'))
    return {iso: _build(e) for iso, e in ev.items()}


def _load_cis(path):
    """Columns Full Member / Associate Member / Founding State (a year) and Note. Rows whose Note starts 'Withdr'
    carry the year of withdrawal in 'Founding State'; 'Suspend' rows are suspensions and change nothing."""
    ev = {}
    for r in _read(path):
        iso = (r.get('ISO- Alpha3 Code') or '').strip()
        full, assoc, found = _year(r.get('Full Member')), _year(r.get('Associate Member')), _year(r.get('Founding State'))
        note = (r.get('Note') or '').strip().lower()
        if not iso:
            continue
        e = ev.setdefault(iso, [])
        if full:
            e.append((full, 'join'))
        elif assoc:
            e.append((assoc, 'end'))
        elif found and re.match(r'withdr', note):
            e.append((found, 'end'))
        elif found and not re.match(r'suspend', note):
            e.append((found, 'join'))
    return {iso: _build(e) for iso, e in ev.items()}


def load_history(path):
    """{iso: [(first_year, year_left_or_None), ...]} for one membership file."""
    name = Path(path).name
    if name == 'G77.csv':
        return _load_g77(path)
    if name == 'CIS.csv':
        return _load_cis(path)
    return _load_standard(path)


def is_current(intervals):
    return any(end is None for _, end in intervals)


def current_members(history):
    return {iso for iso, iv in history.items() if is_current(iv)}


def is_member(history, iso, year):
    """Was `iso` a member in `year`? An unknown year (None or 0) falls back to current membership."""
    if iso in PREDECESSOR and iso not in history and year and year <= PREDECESSOR[iso][1]:   # only if the file has no rows of its own (UN.csv has)
        iso = PREDECESSOR[iso][0]
    iv = history.get(iso)
    if not iv:
        return False
    if not year:
        return is_current(iv)
    return any(start <= year and (end is None or year < end) for start, end in iv)
