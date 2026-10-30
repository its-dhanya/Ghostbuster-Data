"""JSON evidence: snapshot bundles, per-service readback exports, lookup ledgers, single-collection dumps."""
import json
from .normalizer import mk, COVERAGE

def load_json(fid, path):
    d = json.load(open(path))
    obs = []
    if 'snapshots' in d:                                  # snapshot bundle
        for s in d['snapshots']:
            COVERAGE.append((s['data_store'], fid, s['captured_at']))
            for r in s['records']:
                f = dict(r); f['_coll'] = s['collection']
                if 'recorded_at' in r:
                    f['subject_reference'] = r.get('lookup_value'); t = r['recorded_at']; sysn = r.get('system')
                else:
                    t = s['captured_at']; sysn = s['data_store']
                obs.append(mk(fid, t, r['resource_id'], f, 'bundle', sysn))
    elif 'service_exports' in d:                          # per-service readback export
        for svc, secs in d['service_exports'].items():
            for coll, lst in secs.items():
                for r in lst:
                    f = dict(r); f['_coll'] = coll
                    if 'hits' in r:                       # search index query
                        docs = r['hits'].get('documents', [])
                        f['_hit'] = r['hits'].get('total', len(docs)) > 0
                        for dd in docs: f.update({k: v for k, v in dd.items() if k != 'resource_id'})
                        f['query'] = r.get('query')
                    obs.append(mk(fid, r.get('observed_at', d['exported_at']), r['resource_id'], f, 'export', svc,
                                  [r['query'].lower()] if r.get('query') else ()))
    elif 'records' in d and d['records'] and 'record_type' in d['records'][0]:   # lookup ledger
        for r in d['records']:
            f = dict(r); f['_coll'] = 'ledger'
            obs.append(mk(fid, r['recorded_at'], r['resource_id'], f, 'ledger', r['system']))
    elif 'records' in d:                                  # single-collection dumps
        t = d.get('captured_at') or d.get('exported_at')
        for r in d['records']:
            f = dict(r); f['_coll'] = d.get('collection')
            obs.append(mk(fid, t, r['resource_id'], f, 'collection', None))
    return obs
