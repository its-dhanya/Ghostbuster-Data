"""Timestamps are compared as strings throughout the engine, so every source is normalised once, at the edge, to the
canonical UTC form YYYY-MM-DDTHH:MM:SSZ (accepts fractional seconds, +hh:mm offsets, a space separator, date-only)."""
import re
from datetime import datetime, timezone

_RX = re.compile(r'^(\d{4}-\d\d-\d\d)(?:[T ](\d\d:\d\d)(?::(\d\d))?(?:\.\d+)?)?\s*(Z|[+-]\d\d:?\d\d)?$')

def norm_ts(s):
    if s is None or s == '': return s
    m = _RX.match(str(s).strip())
    if not m: return s                                   # leave unknown shapes untouched rather than guess
    d, hm, sec, tz = m.groups()
    dt = datetime.strptime(f'{d}T{hm or "00:00"}:{sec or "00"}', '%Y-%m-%dT%H:%M:%S')
    if tz and tz != 'Z':
        sign = 1 if tz[0] == '+' else -1
        digits = tz[1:].replace(':', '')
        off = sign * (int(digits[:2]) * 60 + int(digits[2:]))
        from datetime import timedelta
        dt = dt - timedelta(minutes=off)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
