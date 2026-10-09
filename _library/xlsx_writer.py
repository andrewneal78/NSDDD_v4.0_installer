"""Minimal .xlsx writer using only the standard library, so the offline Windows package needs no extra wheel.

Why: a CSV opens in a single column in Excel under continental European regional settings (Excel expects semicolons),
and `=HYPERLINK("...","...")` formulas written to a CSV use English argument separators that those versions reject.
A workbook stores values and links in a locale-independent form, so it opens correctly everywhere.

Cells may be str, int, float, None, or Link(url, label). Sheets are written with a bold frozen header row when
`header_row` is given (0-based index into rows) and column widths taken from the first rows.
"""
import math
import numbers
import re
import zipfile
from collections import namedtuple
from xml.sax.saxutils import escape

Link = namedtuple('Link', 'url label')

_ILLEGAL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')
_MAX_CELL = 32767


def _col(n):
    s = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _text(v):
    return escape(_ILLEGAL.sub('', str(v))[:_MAX_CELL])


def _sheet_xml(rows, header_row, widths):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">']
    if header_row is not None:
        out.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" '
                   'state="frozen"/></sheetView></sheetViews>' % (header_row + 1, header_row + 2))
    if widths:
        out.append('<cols>' + ''.join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i + 1, i + 1, w)
                                      for i, w in enumerate(widths)) + '</cols>')
    out.append('<sheetData>')
    links = []
    ncols = 0
    for r, row in enumerate(rows, 1):
        cells = []
        for c, v in enumerate(row):
            ref = '%s%d' % (_col(c), r)
            if v is None or v == '':
                continue
            bold = header_row is not None and r - 1 == header_row
            if isinstance(v, Link):
                if not v.url:
                    continue
                links.append((ref, v.url))
                cells.append('<c r="%s" s="2" t="inlineStr"><is><t>%s</t></is></c>' % (ref, _text(v.label)))
            elif isinstance(v, bool):
                cells.append('<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, v))
            elif isinstance(v, numbers.Integral):
                cells.append('<c r="%s"><v>%d</v></c>' % (ref, int(v)))
            elif isinstance(v, numbers.Real):
                if math.isfinite(float(v)):
                    cells.append('<c r="%s"><v>%s</v></c>' % (ref, repr(float(v))))
            else:
                cells.append('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                             % (ref, ' s="1"' if bold else '', _text(v)))
        ncols = max(ncols, len(row))
        out.append('<row r="%d">%s</row>' % (r, ''.join(cells)))
    out.append('</sheetData>')
    if header_row is not None and ncols and len(rows) > header_row + 1:
        out.append('<autoFilter ref="A%d:%s%d"/>' % (header_row + 1, _col(ncols - 1), len(rows)))
    if links:
        out.append('<hyperlinks>' + ''.join('<hyperlink ref="%s" r:id="rId%d"/>' % (ref, i + 1)
                                            for i, (ref, _) in enumerate(links)) + '</hyperlinks>')
    out.append('</worksheet>')
    rels = None
    if links:
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                          'relationships/hyperlink" Target="%s" TargetMode="External"/>' % (i + 1, escape(u, {'"': '&quot;'}))
                          for i, (_, u) in enumerate(links)) + '</Relationships>')
    return ''.join(out), rels


_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
           '<font><b/><sz val="11"/><name val="Calibri"/></font>'
           '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font></fonts>'
           '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
           '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
           '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
           '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def _sheet_name(name, used):
    n = re.sub(r'[\[\]\*\?/\\:]', ' ', name).strip()[:31] or 'Sheet'
    base, k = n, 2
    while n.lower() in used:
        n = base[:28] + ' %d' % k
        k += 1
    used.add(n.lower())
    return n


def write_xlsx(path, sheets):
    """sheets: [{'name': str, 'rows': [[cell, ...], ...], 'header_row': int | None, 'widths': [float, ...] | None}]"""
    used, names, parts = set(), [], []
    for sh in sheets:
        names.append(_sheet_name(sh['name'], used))
        parts.append(_sheet_xml(sh['rows'], sh.get('header_row'), sh.get('widths')))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        n = len(sheets)
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                             'spreadsheetml.worksheet+xml"/>' % i for i in range(1, n + 1)) + '</Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(nm, {'"': '&quot;'}), i, i)
                             for i, nm in enumerate(names, 1)) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                             'Target="worksheets/sheet%d.xml"/>' % (i, i) for i in range(1, n + 1))
                   + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                     'Target="styles.xml"/></Relationships>' % (n + 1))
        z.writestr('xl/styles.xml', _STYLES)
        for i, (xml, rels) in enumerate(parts, 1):
            z.writestr('xl/worksheets/sheet%d.xml' % i, xml)
            if rels:
                z.writestr('xl/worksheets/_rels/sheet%d.xml.rels' % i, rels)
    return path
