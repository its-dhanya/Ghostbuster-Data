"""Plain-text evidence (shift handover pipe tables) and data-catalog identity links from the activity stream."""
import re
from .normalizer import mk

def load_txt(fid, path):
    obs = []
    for l in open(path, encoding='utf-8'):
        m = re.match(r'- (\S+) \| (\w+) \| (\S+) \| (\w+) \| (\w+) \| (.*)', l.strip())
        if m:
            t, sysn, rid, rtype, res, subj = m.groups()
            f = {'record_type': rtype, 'result': res, 'subject_reference': subj, '_coll': 'handover'}
            obs.append(mk(fid, t, rid, f, 'handover', sysn))
    return obs

def load_links(acts):
    out = []
    for a in acts:
        if a['event_type'] != 'LINK_RESOURCE_IDENTITY': continue
        m = re.search(r' to (\S+@\S+) and (user_\d+)', a['details']) or re.search(r'belongs only to (\S+@\S+) and (user_\d+)', a['details'])
        if not m: continue
        o = mk(None, a['event_time'], a['resource_id'], {'_coll': 'catalog_link'}, 'link', a['target_system'], {m.group(1).lower().rstrip('.;,'), m.group(2)})
        o['file_t'] = a['event_time']
        out.append(o)
    return out
