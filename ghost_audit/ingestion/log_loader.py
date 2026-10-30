"""Log evidence. Any dialect that carries key=value / JSON fields is handled by log_parser; lines of one trace are
joined so the lookup key (an email) on the 'started' line identifies the resource on the 'completed' line."""
import re
from common.constants import PREFIX_SYSTEM
from .log_parser import parse_line
from .normalizer import mk, idents

ID_KEYS = ('lookup_key', 'match_key', 'scan_key', 'subject_key', 'subject_ref', 'correlation_key', 'email',
           'customer_email', 'requester_email', 'owner_email', 'matched_value', 'subject_reference', 'customer_reference',
           'requester_name', 'requester_phone', 'phone')
def load_log(fid, path):
    lines = [d for d in (parse_line(l) for l in open(path, encoding='utf-8')) if d]
    traces = {}
    for d in lines:
        tid = d.get('trace_id') or d.get('requestId')
        if tid: traces.setdefault(tid, []).append(d)
    obs = []
    for d in lines:
        rid = d.get('resource_id')
        if not rid: continue
        ev = d.get('event') or ''
        if ev.endswith('_started') or ev in ('connection_acquired',): continue
        f = {k: v for k, v in d.items() if k not in ('_ts', 'instance', 'pod', 'region', 'level', 'service', 'logger',
                                                       'function', 'took_ms', 'duration_ms', 'shard', 'latency_ms')}
        f['_coll'] = ev
        tid = d.get('trace_id') or d.get('requestId')
        extra = set()
        for o in traces.get(tid, []) if tid else [d]:
            for k in ID_KEYS:
                v = o.get(k)
                if v: extra.add(v)
        o = mk(fid, d['_ts'], rid, f, 'log', d.get('service') if (d.get('service') or '') in PREFIX_SYSTEM.values() else None,
               set())
        for v in extra: o['ids'] |= idents({'x': v}) | ({re.sub(r'\D','',v)} if re.match(r'^\+?[\d\s()\-]{7,}$', v) else set())
        o['trace'] = tid
        obs.append(o)
    return obs
