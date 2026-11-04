"""Integrity of the document metadata shipped with the code (document_metadata_4.0.csv).

These are the checks of the 2026-11-03 audit made permanent. Known data problems that need an editorial decision are listed
in KNOWN_ISSUES, so that the tests pass today but fail when a NEW problem appears (or when a listed one is fixed and the
entry should be removed)."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

df = pd.read_csv(ROOT / 'document_metadata_4.0.csv', dtype=str, keep_default_na=False, encoding='utf-8')

# Bosnia and Herzegovina left the G77 around 2019-20, so documents of 2005, 2006 and 2009 cannot be Former, No and Former.
KNOWN_NON_MONOTONIC_G77 = {'Bosnia and Herzegovina'}
# Document numbers whose page count is implausible for their word count (a pages column error, to be checked against the PDF).
KNOWN_LENGTH_OUTLIERS = {'434', '642', '175'}
# Rows whose URL cell is not a web address.
KNOWN_NON_URL = {"Have downloaded PDF but can't find link"}


def test_counts_match_the_published_figures():
    assert len(df) == config.DATASET_DOCUMENTS
    assert df['Country'].nunique() == config.DATASET_COUNTRIES
    assert (int(df.Year.min()), int(df.Year.max())) == (1987, 2026)


def test_keys_are_unique_and_titles_carry_their_number():
    assert df['File prefix'].is_unique and df['Document'].is_unique
    assert all(d.startswith(p + ' ') for p, d in zip(df['File prefix'], df['Document']))


def test_country_iso_and_m49_are_one_to_one():
    pairs = df[['Country', 'ISO Alpha-3 Code', 'M49 code']].drop_duplicates()
    assert pairs['Country'].is_unique and pairs['ISO Alpha-3 Code'].is_unique
    assert df['ISO Alpha-3 Code'].str.fullmatch(r'[A-Z]{3}').all()
    no_m49 = set(df.loc[df['M49 code'] == '', 'ISO Alpha-3 Code'])
    assert no_m49 == {'XKX'}                     # Kosovo has a user-assigned ISO code and no UN M49 code
    assert df.loc[df['M49 code'] != '', 'M49 code'].str.fullmatch(r'\d{1,3}').all()


def test_types_and_numeric_columns():
    assert set(df['NSS/WP/DD']) == {'NSS', 'WP', 'DD', 'TA'}
    for c in ('Year', 'Length', 'segment_count', 'word_count'):
        assert df[c].str.fullmatch(r'\d+').all(), c
        assert (df[c].astype(int) > 0).all(), c
    assert int(df.segment_count.astype(int).sum()) < config.DATASET_SEGMENTS      # English segments; originals make up the rest


def test_g77_columns_agree_and_are_time_consistent():
    label_to_bin = {'Yes': '1', 'Associate': '1', 'Former': '0', 'No': '0'}
    assert all(label_to_bin[a] == b for a, b in zip(df['G77 Member'], df['G77_Member_Binary']))
    order = {'No': 0, 'Yes': 1, 'Associate': 1, 'Former': 2}      # a country goes No -> member -> Former, never back
    for country, g in df.groupby('Country'):
        seq = [order[v] for v in g.assign(y=g.Year.astype(int)).sort_values('y')['G77 Member']]
        if country not in KNOWN_NON_MONOTONIC_G77:
            assert seq == sorted(seq), country
    assert KNOWN_NON_MONOTONIC_G77 <= set(df.Country)


def test_language_columns_have_no_gaps_and_english_first():
    cols = [f'Language {i}' for i in range(1, 12)]
    for _, r in df.iterrows():
        vals = [r[c] for c in cols]
        assert vals[0].startswith('English'), r['File prefix']
        blanks = [i for i, v in enumerate(vals) if not v]
        assert not blanks or blanks == list(range(blanks[0], len(vals))), r['File prefix']
    translated = df['Language 1'] == 'English (Translated)'
    assert (df.loc[translated, 'Language 2'] != '').all()


def test_urls_are_web_addresses_or_listed_exceptions():
    for p, u in zip(df['File prefix'], df['URL Link to Docs']):
        for part in (x.strip() for x in u.split(';') if x.strip()):
            assert re.match(r'https?://\S+$', part) or part in KNOWN_NON_URL, (p, part)


def test_length_is_plausible_for_word_count():
    words_per_page = df.word_count.astype(int) / df.Length.astype(int)
    odd = set(df.loc[(words_per_page < 80) | (words_per_page > 1500), 'File prefix'])
    assert odd == KNOWN_LENGTH_OUTLIERS, sorted(odd ^ KNOWN_LENGTH_OUTLIERS)
