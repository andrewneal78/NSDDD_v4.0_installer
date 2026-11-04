"""Derive the 'G77 Member' and 'G77_Member_Binary' columns of document_metadata_4.0.csv from G77.csv.

G77.csv is what the search filters read (_library/membership.py), so the two columns in the document metadata must be computed
from it rather than typed by hand; otherwise a document list can say one thing and a filter another. One meaning throughout:
status AT THE YEAR THE DOCUMENT WAS PUBLISHED (accession year inclusive, year of leaving exclusive, as in membership.py).

    Yes        member in the publication year                     binary 1
    Associate  not a member, but an associate (G77 and China)     binary 1
    Former     left the group in or before the publication year    binary 0
    No         not yet a member, or never one                     binary 0

Usage (from the installer folder):
    python utils/g77_columns.py --g77 PATH/TO/G77.csv            # report differences only
    python utils/g77_columns.py --g77 PATH/TO/G77.csv --write    # rewrite the two columns in place
Only those two columns change; every other byte of the file is kept."""
import argparse
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _library import membership  # noqa: E402

BINARY = {'Yes': '1', 'Associate': '1', 'Former': '0', 'No': '0'}


def _year(v):
    v = (v or '').strip()
    return int(v) if re.fullmatch(r'\d{4}', v) else None


def associate_since(g77_rows):
    """{iso: first year as associate, or 0 when the file gives the status without a year}."""
    out = {}
    for r in g77_rows:
        iso = (r.get('ISO-Alpha3 Code') or '').strip()
        a = (r.get('Associate') or '').strip()
        if iso and a and a.lower() not in ('no', 'n', '0', 'false'):
            out[iso] = min(out.get(iso, 9999), _year(a) or 0)
    return out


def status(history, assoc, iso, year):
    """'Yes' / 'Associate' / 'Former' / 'No' for one country in one year."""
    if membership.is_member(history, iso, year):
        return 'Yes'
    if iso in assoc and (year or 9999) >= assoc[iso]:
        return 'Associate'
    if any(end is not None and end <= year for _s, end in history.get(iso, [])):
        return 'Former'
    return 'No'


def recompute(csv_text, g77_path):
    """(new csv text, [(file prefix, country, year, old, new), ...]) with the two columns derived from G77.csv."""
    history = membership.load_history(g77_path)
    with open(g77_path, encoding='utf-8-sig', newline='') as f:
        assoc = associate_since(list(csv.DictReader(f)))
    rows = list(csv.reader(io.StringIO(csv_text, newline='')))
    head = rows[0]
    i_iso, i_year, i_lab, i_bin = (head.index(c) for c in ('ISO Alpha-3 Code', 'Year', 'G77 Member', 'G77_Member_Binary'))
    i_id, i_country = head.index('File prefix'), head.index('Country')
    changes = []
    for r in rows[1:]:
        new = status(history, assoc, r[i_iso], int(r[i_year]))
        if (r[i_lab], r[i_bin]) != (new, BINARY[new]):
            changes.append((r[i_id], r[i_country], r[i_year], r[i_lab], new))
            r[i_lab], r[i_bin] = new, BINARY[new]
    out = io.StringIO()
    csv.writer(out, lineterminator='\n').writerows(rows)
    return out.getvalue(), changes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--g77', required=True, help='G77.csv from the installed metadata folder')
    ap.add_argument('--csv', default=str(ROOT / 'document_metadata_4.0.csv'))
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    text = Path(a.csv).read_bytes().decode('utf-8')
    new_text, changes = recompute(text, a.g77)
    for c in changes:
        print('doc %s  %s %s: %s -> %s' % c)
    print(f'{len(changes)} document(s) differ from G77.csv')
    if a.write and changes:
        Path(a.csv).write_bytes(new_text.encode('utf-8'))
        print('Rewritten:', a.csv)


if __name__ == '__main__':
    main()
