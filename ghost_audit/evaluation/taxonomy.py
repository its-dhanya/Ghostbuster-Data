"""Error taxonomy: bucket every missing / extra step of a case by its likely cause."""
from collections import Counter

BUCKETS = {
    'missed_audit_record': 'audit record id present in no evidence file (unrecoverable)',
    'missed_secondary_record': 'search / support / analytics / export / marketing record not found',
    'missed_account': 'account id not linked (activity inference could not attribute it)',
    'tie_swap': 'same-day resources of two cases swapped (indistinguishable ties)',
    'missed_active_flow': 'active data flow or restore path missed',
    'incorrect_tombstone_treatment': 'tombstone state / treatment wrong',
    'incorrect_evidence_reference': 'right step, wrong evidence id',
    'extra_resource': 'resource attributed to the wrong case',
    'status_error': 'case status differs',
}

def classify(case_id, d):
    out = []
    miss, extra = d['missing_steps'], d['extra_steps']
    def kind(k): return k[2].rsplit('_', 1)[0]
    swapped = {kind(m) for m in miss} & {kind(e) for e in extra}
    for m in miss:
        k = kind(m)
        if k in swapped: out.append('tie_swap')
        elif k == 'audit_record': out.append('missed_audit_record')
        elif k == 'account': out.append('missed_account')
        elif k in ('data_flow', 'backup'): out.append('missed_active_flow')
        elif k == 'tombstone': out.append('incorrect_tombstone_treatment')
        else: out.append('missed_secondary_record')
    for e in extra:
        if kind(e) not in swapped: out.append('extra_resource')
    out += ['incorrect_evidence_reference'] * sum(1 for f in d['field_mismatches'] if f[1] == 'evidence_id')
    if d['status'] != 'MATCH': out.append('status_error')
    return out

def summarize(per_case):
    c = Counter(b for buckets in per_case.values() for b in buckets)
    return [f'{n:3d}  {b}: {BUCKETS[b]}' for b, n in c.most_common()]
