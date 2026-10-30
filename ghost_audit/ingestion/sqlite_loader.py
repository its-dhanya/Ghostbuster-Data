"""SQLite snapshot exports (primary + regional / read / reporting / failover replicas, inventory snapshots).
The text is executed with sqlite3 and every table row becomes an observation tagged with its table, so replication
drift (a record present only in a replica) is visible to the state engine."""
import json, re, sqlite3
from .normalizer import mk, COVERAGE

def load_sql(fid, path):
    txt = open(path, encoding='utf-8').read()
    con = sqlite3.connect(':memory:')
    con.executescript(txt)
    con.row_factory = sqlite3.Row
    cap = re.search(r'Captured at: (\S+)', txt)
    cap = cap.group(1) if cap else None
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    scope = {}
    if 'snapshot_scope' in tables:
        scope = {r[0]: r[1] for r in con.execute('select * from snapshot_scope')}
        for k, v in scope.items(): COVERAGE.append((k, fid, v))
    if any(t.startswith('customer_profiles_') for t in tables): COVERAGE.append(('account_service', fid, cap))
    obs = []
    for tb in tables:
        if tb == 'snapshot_scope': continue
        for row in con.execute(f'select * from {tb}'):
            r = dict(row)
            if 'record_json' in r:
                f = json.loads(r['record_json']); f['_coll'] = r['collection_name']
                t = r['updated_at']; system = r['origin_system']
                f['_updated'] = t
            else:
                f = {k: v for k, v in r.items()}; f['_coll'] = tb
                t = r.get('updated_at') or r.get('indexed_at') or cap
                system = None
                if tb == 'customer_profiles_primary' or tb == 'customer_profiles_failover_replica': system = 'account_service'
                f['_updated'] = t
            rid = r['resource_id']
            obs.append(mk(fid, cap, rid, f, 'sql:' + tb, system))
            obs[-1]['row_t'] = t
    return obs
