"""Democracy, income and aid status of a country in the year a document was published (standard library only).

Four sources, all read from the metadata CSVs, each looked up for the document's own year:
  Freedom_house.csv  Freedom House status (Free / Partly Free / Not Free). One row per change; the year is the Freedom in
                     the World year under review. A country has the status of its latest row up to the document's year.
  OGHIST.csv         World Bank income group (Low / Lower-middle / Upper-middle / High) for each calendar year, 1987 to 2024.
  ODA.csv            OECD aid-recipient status (ODA_Recipient / Non_Recipient). One row per change, from 1996.
  Vdem.csv           V-Dem indices for each country and year, 1945 to 2025, with the Regimes of the World category.

Conventions
- Yearly series (income, V-Dem): the document's own year. A year after the last one in the data uses the last year (a 2026
  document gets 2024 income and 2025 V-Dem). A year before the first gives no value.
- Change-point series (Freedom House, aid): the latest row not later than the document's year; before the first row, no value.
- A document with no year gets the latest value.
- SCG (the State Union of Serbia and Montenegro, 2003 to 2006): where a source has no SCG rows it takes Serbia's, as in membership.py.
"""
import csv
import re
from pathlib import Path

INCOME = {'L': 'Low', 'LM': 'Lower-middle', 'LM*': 'Lower-middle', 'UM': 'Upper-middle', 'H': 'High'}
STAND_IN = {'SCG': 'SRB'}
HEADLINE = ['v2x_polyarchy', 'v2x_libdem', 'v2x_partipdem', 'v2x_delibdem', 'v2x_egaldem']
REGIMES = ['Closed autocracy', 'Electoral autocracy', 'Electoral democracy', 'Liberal democracy']


def _year(v):
    v = str(v if v is not None else '').strip()
    m = re.match(r'^(\d{4})(\.0+)?$', v)
    return int(m.group(1)) if m else None


def _rows(path):
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.reader(f))


def load_freedom_history(path):
    """{iso: [(year, 'Free'|'Partly Free'|'Not Free'), ...]} in year order."""
    rows = _rows(path)
    h = rows[0]
    iso_c = next(i for i, c in enumerate(h) if 'alpha' in c.lower())
    cols = {name: h.index(name) for name in ('Not Free', 'Partly Free', 'Free')}
    out = {}
    for r in rows[1:]:
        if len(r) <= iso_c or not r[iso_c].strip():
            continue
        for status, c in cols.items():
            y = _year(r[c]) if c < len(r) else None
            if y:
                out.setdefault(r[iso_c].strip(), []).append((y, status))
    return {k: sorted(v) for k, v in out.items()}


def load_income_history(path):
    """{iso: {calendar_year: income group}} from the World Bank history (OGHIST.csv)."""
    rows = _rows(path)
    year_row = next(r for r in rows if r and any('calendar year' in c.lower() for c in r))
    years = [(i, _year(c)) for i, c in enumerate(year_row) if _year(c)]
    out = {}
    for r in rows:
        if len(r) < 3 or not re.fullmatch(r'[A-Z]{3}', r[0].strip()):
            continue
        series = {y: INCOME[r[i].strip()] for i, y in years if i < len(r) and r[i].strip() in INCOME}
        if series:
            out[r[0].strip()] = series
    return out


def load_aid_history(path):
    """{iso: [(year, 'ODA_Recipient'|'Non_Recipient'), ...]} in year order."""
    rows = _rows(path)
    h = rows[0]
    iso_c, y_c, s_c = h.index('ISO_Code'), h.index('Year'), h.index('Status')
    out = {}
    for r in rows[1:]:
        if len(r) > s_c and _year(r[y_c]) and r[s_c].strip():
            out.setdefault(r[iso_c].strip(), []).append((_year(r[y_c]), r[s_c].strip()))
    return {k: sorted(v) for k, v in out.items()}


def load_vdem(path, variables_path=None):
    """({iso: {year: {column: value}}}, [(column, title, scale)]). Values are floats, the regime columns ints; blanks are left out."""
    with open(path, encoding='utf-8', newline='') as f:
        rd = csv.DictReader(f)
        measures = [c for c in rd.fieldnames if c.startswith('v2x')]
        data = {}
        for r in rd:
            y = _year(r.get('Year'))
            if not y:
                continue
            row = {'Regime of the World': r.get('Regime of the World', '')}
            for c in measures:
                v = r.get(c, '')
                if v not in ('', None):
                    try:
                        row[c] = float(v)
                    except ValueError:
                        pass
            data.setdefault(r['ISO-Alpha3 Code'], {})[y] = row
    titles = []
    if variables_path and Path(variables_path).exists():
        info = {r['Column']: r for r in csv.DictReader(open(variables_path, encoding='utf-8', newline=''))}
        titles = [(c, info.get(c, {}).get('Title', c), info.get(c, {}).get('Scale', '')) for c in measures]
    else:
        titles = [(c, c, '') for c in measures]
    return data, titles


def _stand_in(table, iso, year):
    if iso in table:
        return table[iso]
    sub = STAND_IN.get(iso)
    if sub and sub in table and (year is None or year <= 2006):
        return table[sub]
    return None


def change_point_asof(table, iso, year):
    """Latest value not after `year` in a {iso: [(year, value)]} change-point table; None before the first row."""
    hist = _stand_in(table, iso, year)
    if not hist:
        return None
    if year is None:
        return hist[-1][1]
    found = None
    for y, v in hist:
        if y <= year:
            found = v
        else:
            break
    return found


def yearly_asof(table, iso, year):
    """Value for `year` in a {iso: {year: value}} table; the last year if `year` is later, nothing if it is earlier."""
    ser = _stand_in(table, iso, year)
    if not ser:
        return None
    if year is None or year > max(ser):
        return ser[max(ser)]
    if year in ser:
        return ser[year]
    earlier = [y for y in ser if y < year]
    return ser[max(earlier)] if earlier else None


def vdem_year_used(table, iso, year):
    """The V-Dem year that yearly_asof used for this document, or None."""
    ser = _stand_in(table, iso, year)
    if not ser:
        return None
    if year is None or year > max(ser):
        return max(ser)
    if year in ser:
        return year
    earlier = [y for y in ser if y < year]
    return max(earlier) if earlier else None


def parse_document_numbers(text):
    """'12, 45 100-103' -> ['12', '45', '100', '101', '102', '103'] (document numbers, as strings, in order, no repeats)."""
    out, seen = [], set()
    for part in re.split(r'[\s,;]+', str(text or '').strip()):
        if not part:
            continue
        m = re.fullmatch(r'(\d+)\s*[-–]\s*(\d+)', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            nums = range(min(a, b), max(a, b) + 1) if abs(b - a) <= 2000 else []
        elif part.isdigit():
            nums = [int(part)]
        else:
            continue
        for n in nums:
            s = str(n)
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def unusable_document_numbers(text):
    """The parts of a document-number list that parse_document_numbers cannot use ('abc', '1-5000'), as a list of strings.
    An empty list means every part was understood. Callers that must not silently widen a search check this."""
    bad = []
    for part in re.split(r'[\s,;]+', str(text or '').strip()):
        if not part:
            continue
        m = re.fullmatch(r'(\d+)\s*[-\u2013]\s*(\d+)', part)
        if m:
            if abs(int(m.group(2)) - int(m.group(1))) > 2000:
                bad.append(part)
        elif not part.isdigit():
            bad.append(part)
    return bad
