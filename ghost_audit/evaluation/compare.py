"""Structural comparator: explains HOW a predicted case differs from the expected one."""
import json

def _key(s): return (s['operation'], s['system_id'], s['resource_id'])

def compare_case(expected_status, expected_steps, status, steps):
    E = {_key(s): s for s in expected_steps}; P = {_key(s): s for s in steps}
    d = {'status': 'MATCH' if status == expected_status else f'MISMATCH ({status} vs {expected_status})',
         'missing_steps': sorted(set(E) - set(P)), 'extra_steps': sorted(set(P) - set(E)), 'field_mismatches': []}
    for k in sorted(set(E) & set(P)):
        for f in ('step_no', 'phase', 'state', 'evidence_id'):
            if E[k][f] != P[k][f]: d['field_mismatches'].append((k, f, E[k][f], P[k][f]))
    common = [k for k in (_key(s) for s in expected_steps) if k in P]
    d['sequence'] = 'MATCH' if steps == expected_steps else ('ORDER_OK_BUT_STEPS_DIFFER' if common == [k for k in (_key(s) for s in steps) if k in E] else 'MISMATCH')
    return d

def render(case_id, d):
    L = [f'{case_id}: status {d["status"]}; sequence {d["sequence"]}']
    L += [f'    missing {m}' for m in d['missing_steps']] + [f'    extra   {m}' for m in d['extra_steps']]
    L += [f'    field   {k} {f}: expected {a!r} got {b!r}' for k, f, a, b in d['field_mismatches']]
    return '\n'.join(L)
