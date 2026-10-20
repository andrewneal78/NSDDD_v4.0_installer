"""Anonymous start-up count for NSDDD installs.

At most once a day, when NSDDD starts, one small request goes to the project's GoatCounter page
(https://nsddd.goatcounter.com, free, no cookies). It carries only the app version, the data version and the
operating system family. No document, search, name, e-mail or file path is sent. GoatCounter sees the IP address as
any web server does, keeps no cookie, and stores a one-way hash to tell visitors apart.

Switch it off: set NSDDD_NO_PING=1, or create an empty file called no_ping next to launch.py.
A failed or offline request never stops NSDDD from starting. A git checkout (a developer's copy) never pings."""
import datetime
import os
import platform
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

ENDPOINT = os.environ.get('NSDDD_PING_URL') or 'https://nsddd.goatcounter.com/count'
STAMP = '.last_usage_ping'


def disabled(app_dir):
    app_dir = Path(app_dir)
    return (os.environ.get('NSDDD_NO_PING') == '1' or (app_dir / 'no_ping').exists()
            or (app_dir / '.git').exists())


def build_url(app_version, data_version):
    return ENDPOINT + '?' + urlencode({'p': f'/start/{app_version or "unknown"}', 't': f'data {data_version or "unknown"}'})


def ping_once_a_day(app_dir, app_version, today=None, opener=None):
    """Send the daily count. Returns True when sent. Never raises."""
    try:
        if disabled(app_dir):
            return False
        import data_update
        data_dir, _ = data_update.locate(app_dir)
        if not data_dir:
            return False
        today = today or datetime.date.today().isoformat()
        stamp = Path(data_dir) / STAMP
        if stamp.exists() and stamp.read_text().strip() == today:
            return False
        data_version = data_update.read_state(data_dir)[0]
        req = Request(build_url(app_version, data_version),
                      headers={'User-Agent': f'Mozilla/5.0 (NSDDD-launcher; {platform.system()})'})
        (opener or data_update.urlopen)(req, 3).read(1)
        stamp.write_text(today)
        return True
    except Exception:
        return False
