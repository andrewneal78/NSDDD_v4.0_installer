"""Democracy, income and aid status as of the document's year (_library/country_context.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _library import country_context as C

FH = """Country,ISO- Alpha3 Code,Not Free,Partly Free,Free,Note
Hungary,HUN,,1987,,baseline
Hungary,HUN,,,1990,
Hungary,HUN,,2018,,
Kosovo,XKX,,2009,,first
Serbia,SRB,,1987,,
Serbia,SRB,,,2001,
"""
OGHIST = """,World Bank Analytical Classifications,,,
,Bank's fiscal year:,FY89,FY90,FY91
,Data for calendar year :,1987,1988,1989
,Low income (L),<= 480,<= 545,<= 580
,,,,
AFG,Afghanistan,L,L,L
ALB,Albania,..,LM,LM*
"""
ODA = """Country,ISO_Code,Year,Status
Albania,ALB,1996,ODA_Recipient
Albania,ALB,2011,Non_Recipient
"""
VDEM = """Country,ISO-Alpha3 Code,V-Dem country_text_id,Year,Regime of the World,v2x_polyarchy,v2x_regime,Note
Hungary,HUN,HUN,2005,Liberal democracy,0.9,3,
Hungary,HUN,HUN,2025,Electoral autocracy,0.42,1,
"""


@pytest.fixture
def files(tmp_path):
    for name, text in (('fh.csv', FH), ('inc.csv', OGHIST), ('oda.csv', ODA), ('vdem.csv', VDEM)):
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def test_freedom_follows_the_year(files):
    fh = C.load_freedom_history(files / 'fh.csv')
    assert C.change_point_asof(fh, 'HUN', 2005) == 'Free'
    assert C.change_point_asof(fh, 'HUN', 2018) == 'Partly Free'
    assert C.change_point_asof(fh, 'HUN', 2026) == 'Partly Free'
    assert C.change_point_asof(fh, 'HUN', 1986) is None
    assert C.change_point_asof(fh, 'HUN', None) == 'Partly Free'
    assert C.change_point_asof(fh, 'XKX', 2008) is None


def test_serbia_and_montenegro_takes_serbia_to_2006(files):
    fh = C.load_freedom_history(files / 'fh.csv')
    assert C.change_point_asof(fh, 'SCG', 2005) == 'Free'
    assert C.change_point_asof(fh, 'SCG', 2010) is None


def test_income_is_the_documents_year_and_later_years_use_the_last(files):
    inc = C.load_income_history(files / 'inc.csv')
    assert C.yearly_asof(inc, 'ALB', 1987) is None          # '..' means no classification
    assert C.yearly_asof(inc, 'ALB', 1988) == 'Lower-middle'
    assert C.yearly_asof(inc, 'ALB', 1989) == 'Lower-middle'
    assert C.yearly_asof(inc, 'AFG', 2026) == 'Low'
    assert C.yearly_asof(inc, 'AFG', 1980) is None


def test_aid_status_changes_in_its_year(files):
    oda = C.load_aid_history(files / 'oda.csv')
    assert C.change_point_asof(oda, 'ALB', 1995) is None
    assert C.change_point_asof(oda, 'ALB', 2010) == 'ODA_Recipient'
    assert C.change_point_asof(oda, 'ALB', 2011) == 'Non_Recipient'


def test_vdem_year_and_latest(files):
    data, titles = C.load_vdem(files / 'vdem.csv')
    assert C.yearly_asof(data, 'HUN', 2005)['Regime of the World'] == 'Liberal democracy'
    assert C.yearly_asof(data, 'HUN', 2026)['v2x_polyarchy'] == 0.42
    assert C.vdem_year_used(data, 'HUN', 2026) == 2025
    assert C.yearly_asof(data, 'HUN', 1999) is None
    assert [t[0] for t in titles] == ['v2x_polyarchy', 'v2x_regime']


@pytest.mark.parametrize('text,expected', [
    ('12', ['12']),
    ('12, 45 100-102', ['12', '45', '100', '101', '102']),
    ('7;7,8', ['7', '8']),
    ('103-101', ['101', '102', '103']),
    ('abc 5', ['5']),
    ('', []),
])
def test_parse_document_numbers(text, expected):
    assert C.parse_document_numbers(text) == expected


def test_real_metadata_if_present():
    import os   # point NSDDD_TEST_METADATA at an installed metadata/ folder to run this check
    meta = Path(os.environ.get('NSDDD_TEST_METADATA', 'metadata_4.0_not_set'))
    if not (meta / 'Vdem.csv').exists():
        pytest.skip('4.0 metadata not available (set NSDDD_TEST_METADATA to an installed metadata folder)')
    fh = C.load_freedom_history(meta / 'Freedom_house.csv')
    assert C.change_point_asof(fh, 'HUN', 2005) == 'Free'
    assert C.change_point_asof(fh, 'HUN', 2025) == 'Partly Free'
    data, titles = C.load_vdem(meta / 'Vdem.csv', meta / 'Vdem_variables.csv')
    assert len(titles) == 128
    assert C.yearly_asof(data, 'HUN', 2005)['Regime of the World'] == 'Liberal democracy'


def test_notebook_filter_fields_and_summary():
    """The notebook's MetadataFilters carries the new fields and says so in its summary."""
    import json
    from dataclasses import dataclass, field, asdict
    from typing import Dict, List, Optional
    nb = json.loads((Path(__file__).resolve().parents[1] / 'document_metadata_search_voila.ipynb').read_text(encoding='utf-8'))
    src = ''.join(next(c['source'] for c in nb['cells'] if c['cell_type'] == 'code' and 'class MetadataFilters' in ''.join(c['source'])))
    ns = {'dataclass': dataclass, 'field': field, 'asdict': asdict, 'List': List, 'Dict': Dict, 'Optional': Optional}
    exec(compile('\n'.join(l for l in src.split('\n') if not l.startswith('%%')), 'cell', 'exec'), ns)
    f = ns['MetadataFilters'](vdem_regimes=['Closed autocracy'], vdem_ranges=[{'measure': 'v2x_polyarchy', 'min': None, 'max': 0.2}],
                              doc_numbers=['431', '138'], freedom_house_status=['Free'])
    s = f.get_summary()
    assert 'V-Dem regime (year published): Closed autocracy' in s and 'v2x_polyarchy: any to 0.2' in s
    assert 'Documents: 431, 138' in s and 'Democracy, Freedom House (year published): Free' in s
    assert ns['MetadataFilters']().to_dict() == {'membership_at_publication': True}
    sr = ns['SearchResult'](segment_id='1/1', text='t', score=1.0, document_id='1', document_name='d', country='c', country_iso='ABC', year=2000, doc_type='NSS')
    assert sr.vdem == {} and sr.oda_status == '' and sr.vdem_regime == ''
