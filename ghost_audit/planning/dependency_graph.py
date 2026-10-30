"""Dependency-aware safety analysis of a plan.

Dependencies (A -> B means A must happen before B):
  disable a data flow  -> every record treatment (a live flow can recreate what is being cleaned)
  block a restore      -> every record treatment (a restore can bring deleted data back)
  record treatments    -> their verification
  disable / block      -> VERIFY_DATA_FLOW_DISABLED / VERIFY_RESTORE_BLOCKED
The submission order is fixed by the challenge (operation table, then system_id, then resource_id). `check_plan`
proves that this canonical order is a valid topological order of the dependency graph, i.e. that emitting it
is safe; it reports a violation instead of silently reordering."""
from common.constants import OP_ORDER

GUARDS = ('DISABLE_DATA_FLOW', 'BLOCK_RESTORE')
TREATMENTS = ('DELETE_RECORD', 'REDACT_RECORD', 'ANONYMIZE_RECORD')

def dependency_edges(steps):
    edges = []
    guards = [s for s in steps if s['operation'] in GUARDS]
    treat = [s for s in steps if s['operation'] in TREATMENTS]
    for g in guards:
        for t in treat: edges.append((g['step_no'], t['step_no'], 'guard-before-treatment'))
    by_res = {(s['operation'], s['resource_id']): s for s in steps}
    link = {'DELETE_RECORD': 'VERIFY_RECORD_ABSENT', 'REDACT_RECORD': 'VERIFY_RECORD_REDACTED', 'ANONYMIZE_RECORD': 'VERIFY_RECORD_ANONYMIZED',
            'DISABLE_DATA_FLOW': 'VERIFY_DATA_FLOW_DISABLED', 'BLOCK_RESTORE': 'VERIFY_RESTORE_BLOCKED'}
    for s in steps:
        v = link.get(s['operation'])
        if v and (v, s['resource_id']) in by_res: edges.append((s['step_no'], by_res[(v, s['resource_id'])]['step_no'], 'treatment-before-verification'))
    return edges

def check_plan(steps):
    """list of violated dependencies (empty = the canonical order is a valid topological order)"""
    return [f'step {a} must precede step {b} ({why})' for a, b, why in dependency_edges(steps) if a >= b]
