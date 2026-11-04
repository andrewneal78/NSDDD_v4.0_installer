import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from utils import g77_columns as G  # noqa: E402

G77 = """ISO-Alpha3 Code,Member,Former,Associate
AAA,1976,,
BBB,1976,2004,
CCC,1990,,
DDD,,,
CHN,,,1964
"""
CSV = "File prefix,Document,Country,ISO Alpha-3 Code,Year,G77 Member,G77_Member_Binary\n" + ''.join(
    f"{i},d{i},{c},{c},{y},{lab},{b}\n" for i, (c, y, lab, b) in enumerate([
        ('AAA', 2000, 'No', 0), ('BBB', 2003, 'Former', 0), ('BBB', 2004, 'Yes', 1), ('BBB', 2010, 'No', 0),
        ('CCC', 1989, 'Yes', 1), ('CCC', 1990, 'No', 0), ('DDD', 2010, 'Yes', 1), ('CHN', 2000, 'No', 0)], 1))


def test_status_is_derived_for_the_publication_year(tmp_path):
    g = tmp_path / 'G77.csv'
    g.write_text(G77)
    new, changes = G.recompute(CSV, g)
    got = [(l.split(',')[3], l.split(',')[4], l.split(',')[5], l.split(',')[6]) for l in new.splitlines()[1:]]
    assert got == [('AAA', '2000', 'Yes', '1'), ('BBB', '2003', 'Yes', '1'), ('BBB', '2004', 'Former', '0'),
                   ('BBB', '2010', 'Former', '0'), ('CCC', '1989', 'No', '0'), ('CCC', '1990', 'Yes', '1'),
                   ('DDD', '2010', 'No', '0'), ('CHN', '2000', 'Associate', '1')]
    assert len(changes) == 8                                  # every hand-typed value above was wrong
    assert G.recompute(new, g)[1] == []                       # idempotent


def test_untouched_columns_and_bytes_are_preserved():
    real = (ROOT / 'document_metadata_4.0.csv').read_bytes().decode('utf-8')
    import csv, io
    rows = list(csv.reader(io.StringIO(real, newline='')))
    out = io.StringIO()
    csv.writer(out, lineterminator='\n').writerows(rows)
    assert out.getvalue() == real                              # the writer reproduces the shipped file exactly
