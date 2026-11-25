import csv
import errno
import io
import json
import math
import re
import socket
import ssl
import time
from datetime import date, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
RETRY_DELAYS = (2, 8, 20)
MAX_RETRY_WAIT = 30
RETRY_HTTP_CODES = {408, 429, 500, 502, 503, 504}
RETRY_CONNECTION_ERRORS = {
    errno.ECONNABORTED, errno.ECONNREFUSED, errno.ECONNRESET, errno.EHOSTUNREACH,
    errno.ENETUNREACH, errno.ETIMEDOUT, socket.EAI_AGAIN,
}


class ReviewRequired(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_temporary_error(error):
    if isinstance(error, HTTPError):
        return error.code in RETRY_HTTP_CODES
    if isinstance(error, URLError):
        error = error.reason
    return isinstance(error, (TimeoutError, ConnectionError, IncompleteRead)) or (
        isinstance(error, OSError) and error.errno in RETRY_CONNECTION_ERRORS)


def retry_delay(error, default):
    after = error.headers.get('Retry-After') if isinstance(error, HTTPError) and error.headers else None
    if not after:
        return default
    try:
        if after.strip().isdigit():
            server_wait = int(after)
        else:
            retry_at = parsedate_to_datetime(after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            server_wait = retry_at.timestamp() - time.time()
        return max(default, server_wait)
    except (TypeError, ValueError, OverflowError, OSError):
        return default


def fetch(url, *, query=None, post=None, referer=None, tls_context=None):
    if query:
        url += ('&' if '?' in url else '?') + urlencode(query)
    url = quote(url, safe=":/?&=%#@+;,")
    headers = {'User-Agent': 'BulkFlowData/1.0 (public market-data dashboard)',
               'Accept': '*/*'}
    if referer:
        headers['Referer'] = referer
    if post is not None:
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=json.dumps(post).encode() if post is not None else None,
                      headers=headers)
    context = tls_context if tls_context is not None else ssl.create_default_context()
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            with urlopen(request, timeout=18, context=context) as response:
                body = response.read(30_000_001)
                require(0 < len(body) <= 30_000_000, 'Empty or oversized source response')
                return body
        except (OSError, IncompleteRead) as error:
            if attempt == len(RETRY_DELAYS) or not is_temporary_error(error):
                raise
            delay = retry_delay(error, RETRY_DELAYS[attempt])
            if delay > MAX_RETRY_WAIT:
                raise
            if isinstance(error, HTTPError):
                error.close()
            time.sleep(delay)


def api(url, **options):
    data = fetch(url, **options)
    require(data.lstrip().startswith((b'{', b'[')), 'Expected JSON, received another format')
    return json.loads(data)


def document(raw):
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            pass
    return html.fromstring(raw)


def compact(value):
    return ' '.join(value.split())


def node_text(element):
    return compact(' '.join(element.itertext()))


def number(value):
    result = float(str(value).replace(',', '').strip())
    require(math.isfinite(result), 'Non-finite value')
    return result


def positive(value):
    result = number(value)
    require(result > 0, 'Expected a positive source value')
    return result


def month_shift(period, amount):
    year, month = map(int, period.split('-'))
    index = year * 12 + month - 1 + amount
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def periods(first, last):
    while first <= last:
        yield first
        first = month_shift(first, 1)


def date_shift(period, amount):
    return (date.fromisoformat(period) + timedelta(days=amount)).isoformat()


def display_start(period):
    return f'{int(period[:4])-4}-01'


def histories_to_maps(payload):
    return {key: dict(zip(payload['months'], values))
            for key, values in payload['series'].items()}


def apply_month_history(payload, maps, latest):
    first = min(min(rows) for rows in maps.values())
    months = list(periods(first, latest))
    payload.update(months=months, displayStart=display_start(latest), displayEnd=latest,
                   series={k: [rows.get(m) for m in months] for k, rows in maps.items()})


def load(path):
    raw = path.read_text(encoding='utf-8-sig')
    if path.suffix == '.js':
        return json.JSONDecoder().raw_decode(raw.partition('=')[2].lstrip())[0]
    return json.loads(raw)


def dump(data, js=None):
    raw = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=None if js else 2)
    return (f'window.{js}={raw};' if js else raw) + '\n'


def table(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def report_date(url):
    match = re.search(r'/(\d{4})(\d{2})/t(\d{4})(\d{2})(\d{2})_', url)
    require(match, 'Publication date not identified in official URL')
    return f'{match[3]}-{match[4]}-{match[5]}'
