"""Resource-level findings -> ordered remediation and verification plan, serialised in the mandated order.

Per resource: violating -> finding + remediation + (future) verification; compliant -> verification only (with the
evidence that proves the state). A case is INCOMPLETE as soon as one finding exists."""
from common.constants import OP_ORDER, OP_STATE, OP_PHASE, PHASE_RANK
from investigation.resource_classifier import is_attachment
from policy import treatment

def build_steps(world, req, rids, explain=None):
    """returns (findings, remediation, verification) tuples (op, system, resource, evidence_id).
    `explain`, when given, is filled with {resource: {...}} - the decision record behind each resource."""
    audit_at = req['audit_at']
    findings, remed, verif = [], [], []
    for rid in sorted(rids):
        k = world.kind(rid)
        o = world.state_at(rid, audit_at)
        att = bool(o and is_attachment(o)) if k == 'support' else False
        t = treatment(k, att)
        if t is None:                                 # a kind the rules do not cover: surfaced, never silently dropped
            if explain is not None: explain.setdefault('_unhandled', []).append(rid)
            continue
        sys_ = world.sys(rid)
        st = o['state'] if o else None
        if o: ev, conf = o['file_id'], 'CONFIRMED'
        elif k in ('account', 'search', 'export'):
            conf, ev = world.coverage.absence(sys_, audit_at, None)
        else: ev, conf = '', 'UNRESOLVED'
        if explain is not None:
            explain[rid] = dict(kind=k, system=sys_, category=t.category, rule=t.rule_id, action=t.action,
                                observed_state=st, evidence=ev, confidence=conf, at=o['t'] if o else None)
        if t.violating is None:                      # retained record: must still exist
            verif.append((t.verification, sys_, rid, ev)); continue
        if st == t.violating:
            findings.append((t.finding, sys_, rid, ev)); remed.append((t.remediation, sys_, rid, '')); verif.append((t.verification, sys_, rid, ''))
        else:
            verif.append((t.verification, sys_, rid, ev))
    return findings, remed, verif

def emit(findings, remed, verif):
    incomplete = bool(findings)
    rows = []
    if incomplete:
        rows += [(0,) + x for x in findings] + [(1,) + x for x in remed]
        rows += [(2, v[0], v[1], v[2], '') for v in verif]
    else:
        rows += [(2,) + x for x in verif]
    rows.sort(key=lambda r: (r[0], OP_ORDER.index(r[1]), r[2], r[3]))
    steps = [{'step_no': n, 'phase': OP_PHASE[r[1]], 'system_id': r[2], 'resource_id': r[3], 'operation': r[1],
              'state': OP_STATE[r[1]], 'evidence_id': r[4]} for n, r in enumerate(rows, 1)]
    assert all(PHASE_RANK[s['phase']] == r[0] for s, r in zip(steps, rows))
    return ('INCOMPLETE' if incomplete else 'COMPLETE'), steps
