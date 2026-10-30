"""Strict validator for output.csv rows (contract in problem_statement.md)."""
import csv, json
from common.constants import OP_ORDER, OP_STATE as STATE, OP_PHASE, PHASE_RANK as PHASE

PHASE_OF = OP_PHASE
FIELDS = {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}

def validate_row(case_id, status, steps_json):
    errs, warns = [], []
    if status not in ('COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'): return [f'{case_id}: bad status {status}'], warns
    try: steps = json.loads(steps_json)
    except ValueError: return [f'{case_id}: steps_json is not valid JSON'], warns
    if not isinstance(steps, list): return [f'{case_id}: steps_json is not an array'], warns
    if status == 'NOT_APPLICABLE':
        return ([f'{case_id}: NOT_APPLICABLE must have []'] if steps else []), warns
    if not steps: return [f'{case_id}: {status} with no steps (an empty array must never imply a successful deletion)'], warns
    prev = None
    for i, s in enumerate(steps, 1):
        if set(s) != FIELDS: errs.append(f'{case_id} step {i}: fields {sorted(s)}'); continue
        if s['step_no'] != i: errs.append(f'{case_id} step {i}: step_no {s["step_no"]}')
        op = s['operation']
        if op not in STATE: errs.append(f'{case_id} step {i}: unknown operation {op}'); continue
        if s['state'] != STATE[op] or s['phase'] != PHASE_OF[op]: errs.append(f'{case_id} step {i}: phase/state do not match {op}')
        key = (PHASE[s['phase']], OP_ORDER.index(op), s['system_id'], s['resource_id'])
        if prev and key < prev: errs.append(f'{case_id} step {i}: out of order')
        prev = key
        if s['phase'] == 'FINDING' and not s['evidence_id']: errs.append(f'{case_id} step {i}: finding without evidence')
        if s['phase'] == 'REMEDIATION' and s['evidence_id']: errs.append(f'{case_id} step {i}: remediation must have empty evidence')
        if status == 'INCOMPLETE' and s['phase'] == 'VERIFICATION' and s['evidence_id']: errs.append(f'{case_id} step {i}: future verification must have empty evidence')
        if status == 'COMPLETE':
            if s['phase'] != 'VERIFICATION': errs.append(f'{case_id} step {i}: COMPLETE may only contain verification steps')
            if not s['evidence_id']: warns.append(f'{case_id} step {i}: verification without evidence')
    if status == 'INCOMPLETE' and not any(s['phase'] == 'FINDING' for s in steps): errs.append(f'{case_id}: INCOMPLETE without findings')
    return errs, warns

def validate_rows(rows, expected_ids=None):
    errs, warns = [], []
    ids = [r[0] for r in rows]
    if ids != sorted(ids) or len(set(ids)) != len(ids): errs.append('case ids not unique/sorted')
    if expected_ids is not None and ids != sorted(expected_ids): errs.append('case ids differ from deletion_requests.csv')
    for cid, st, sj in rows:
        e, w = validate_row(cid, st, sj); errs += e; warns += w
    return errs, warns
