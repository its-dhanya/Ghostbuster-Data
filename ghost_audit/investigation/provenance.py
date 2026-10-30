"""Provenance: why does each resource belong to the subject, and why is its state believed?"""
import json
from planning import build_steps, emit, check_plan

def explain_case(world, c):
    """JSON-serialisable decision record for one case."""
    rec = {'case_id': c.id, 'email': c.req['email'], 'deletion_requested': c.deletion, 'user_id': c.uid}
    if not c.deletion:
        rec['status'] = 'NOT_APPLICABLE'; return rec
    if c.identity: rec['identity'] = {'rationale': c.identity['rationale'], 'identifiers': sorted(c.identity['edges'])}
    ex = {}
    st, steps = emit(*build_steps(world, c.req, c.rids, ex))
    for rid, d in ex.items(): d['linked_by'] = c.prov.get(rid)
    rec.update(status=st, resources=ex, plan_safety=check_plan(steps),
               ties=[r for r, p in c.prov.items() if p.get('tie')])
    return rec

def write_jsonl(path, records):
    with open(path, 'w', encoding='utf-8') as f:
        for r in records: f.write(json.dumps(r, sort_keys=True) + '\n')
