"""Link to the project's feedback form (Microsoft Forms, University of Edinburgh account, anonymous responses allowed).

Opening the link shows the form with three boxes already filled in: app version, data version and operating system.
Nothing is sent from the user's computer by this code; the form is submitted only when the user presses Submit there.
If the form is moved, change FORM_URL (keep the three placeholders APPVER, DATAVER and OSNAME)."""
import json
import platform
from pathlib import Path
from urllib.parse import quote

FORM_URL = ('https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=sAafLmkWiUWHiRCgaTTcYe6os8tOy5JDo0yn0iTzDApUNFhEOTZGM0w1U0dYVDcyM0JOS0NJSkpaUC4u'
            '&r671e5e56bfd24598bcbe667b0b1d71b0=APPVER&rd13c6aac5bca4054b7b503a8189b7377=DATAVER&r8d37d3fd6c084016ad18469c1fad9ec0=OSNAME')

SYSTEM_NAMES = {'Darwin': 'macOS', 'Windows': 'Windows', 'Linux': 'Linux'}


def data_version(model_dir):
    """Installed data version (DATA_STATE.json sits in the data folder that holds model/), or 'unknown'."""
    try:
        return str(json.loads((Path(model_dir).parent / 'DATA_STATE.json').read_text(encoding='utf-8')).get('version') or 'unknown')
    except Exception:
        return 'unknown'


def feedback_url(app_version, data_ver, system=None):
    """The form link with the three version boxes filled in."""
    system = system or SYSTEM_NAMES.get(platform.system(), platform.system() or 'unknown')
    out = FORM_URL
    for key, value in (('APPVER', app_version), ('DATAVER', data_ver), ('OSNAME', system)):
        out = out.replace('=' + key, '=' + quote(str(value or 'unknown'), safe=''))
    return out
