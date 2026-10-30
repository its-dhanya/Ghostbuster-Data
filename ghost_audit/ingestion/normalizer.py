"""Shared normalisation: an observation is one statement about one resource at one time:
  {file_id, t, system, rid, role, fields, ids}
`fields` keeps the raw attributes; `ids` holds identifiers (emails lower-cased, user refs, hashes, phones) found in
the record - the provenance links used by identity resolution."""
import re
from common.constants import EMAIL, REF, HASH, system_of
from common.timeutil import norm_ts

COVERAGE = []   # (system, file_id, snapshot_time): which systems each snapshot actually inspected (negative evidence)

def idents(obj):
    out = set()
    def walk(v, key=''):
        if isinstance(v, dict):
            for k, x in v.items(): walk(x, k)
        elif isinstance(v, list):
            for x in v: walk(x, key)
        elif isinstance(v, str):
            for e in EMAIL.findall(v): out.add(e.lower())
            for r in REF.findall(v): out.add(r)
            for h in HASH.findall(v): out.add(h)
            if 'phone' in key and v.strip() and v != 'null': out.add(re.sub(r'\D', '', v))
    walk(obj)
    return out

def mk(file_id, t, rid, fields, role='snapshot', system=None, extra_ids=()):
    ids = idents(fields) | set(extra_ids)
    return {'file_id': file_id, 't': norm_ts(t), 'rid': rid, 'system': system or system_of(rid),
            'role': role, 'fields': fields, 'ids': ids}
