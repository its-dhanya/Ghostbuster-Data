"""Hand-built evaluation worlds (independent of the supplied dataset).

Each case builds a tiny World from scratch so the expected answer is known by construction.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.constants import DS
from investigation import World, Case, infer
from planning import build_steps, emit
from ingestion.normalizer import mk

USERS = {'user_900': {'user_id': 'user_900', 'name': 'Ada Test', 'email': 'ada.new@example.org', 'phone': '+44 7000 111 222',
                      'email_hash': 'a' * 64, 'updated_at': '2026-01-01T00:00:00Z'}}
AUDIT = [{'audit_id': 'audit_x1', 'user_id': 'user_900', 'event_time': '2026-01-01T00:00:00Z', 'field_name': 'email',
          'old_value': 'ada.old@example.org', 'new_value': 'ada.new@example.org'}]
META = {f'evidence_{i}': {'file_id': f'evidence_{i}', 'captured_at': t} for i, t in
        [(1, '2026-03-01T10:00:00Z'), (2, '2026-03-05T10:00:00Z'), (3, '2026-03-20T10:00:00Z')]}

def world(obs):
    for o in obs: o['file_t'] = META[o['file_id']]['captured_at']
    return World((obs, META, USERS, AUDIT, []))

def req(email, text='Please delete my account and personal data.', audit='2026-03-10T00:00:00Z'):
    return dict(case_id='c', email=email, requested_at='2026-02-20T00:00:00Z', reported_status='COMPLETE',
                reported_at='2026-02-25T00:00:00Z', audit_at=audit, request_text=text)

def run_case(obs, r):
    w = world(obs)
    c = Case(r, False); infer(w, [c])
    if not c.deletion: return 'NOT_APPLICABLE', []
    return emit(*build_steps(w, r, c.rids))

def ops(steps): return [(s['operation'], s['resource_id'], s['evidence_id']) for s in steps]

CASES = []
def case(f): CASES.append(f); return f

@case
def non_deletion_request_is_not_applicable():
    st, steps = run_case([], req('ada.new@example.org', 'Quiero actualizar mi número de teléfono. Por favor no cierren la cuenta, no es una solicitud de eliminación.'))
    return st == 'NOT_APPLICABLE' and steps == []

@case
def later_evidence_must_not_change_the_answer():
    # search entry absent at 03-01 (before audit), re-appears 03-20 (after audit 03-10): answer stays COMPLETE
    obs = [mk('evidence_1', '2026-03-01T09:00:00Z', 'search_77', {'result': 'miss', 'event': 'index_query_completed', '_coll': 'x'}, 'log', None, ['ada.old@example.org']),
           mk('evidence_3', '2026-03-20T09:00:00Z', 'search_77', {'result': 'hit', 'event': 'index_query_completed', '_coll': 'x'}, 'log', None, ['ada.old@example.org'])]
    for o in obs: o['state'] = None
    st, steps = run_case(obs, req('ada.old@example.org'))     # historical email resolves to user_900
    return st == 'COMPLETE' and ('VERIFY_RECORD_ABSENT', 'search_77', 'evidence_1') in ops(steps)

@case
def replica_drift_and_active_flow_produce_ordered_remediation():
    obs = [mk('evidence_2', '2026-03-05T10:00:00Z', 'account_5', {'_coll': 'customer_profiles_failover_replica', 'email': 'ada.new@example.org', 'full_name': 'Ada'}, 'sql:customer_profiles_failover_replica', 'account_service'),
           mk('evidence_2', '2026-03-05T10:00:00Z', 'data_flow_9', {'_coll': 'connector_configurations', 'subject_selector': 'user_900', 'enabled': True}, 'bundle', 'integration_service'),
           mk('evidence_2', '2026-03-05T10:00:00Z', 'audit_record_4', {'_coll': 'security_audit_events', 'subject_reference': 'user_900'}, 'bundle', 'security_service')]
    st, steps = run_case(obs, req('ada.new@example.org'))
    o = [s['operation'] for s in steps]
    return (st == 'INCOMPLETE' and o.index('DISABLE_DATA_FLOW') < o.index('DELETE_RECORD') and
            o.index('REPORT_REMAINING_RECORD') < o.index('REPORT_ACTIVE_DATA_FLOW') and
            [s['step_no'] for s in steps] == list(range(1, len(steps) + 1)) and
            all(s['evidence_id'] == '' for s in steps if s['phase'] != 'FINDING'))

@case
def tombstone_keeps_reference_but_redacts_identifiers():
    obs = [mk('evidence_2', '2026-03-05T10:00:00Z', 'tombstone_3', {'_coll': 'deleted_customer_references', 'subject_reference': 'user_900', 'name': 'Ada Test', 'email': 'ada.new@example.org'}, 'bundle', 'identity_service')]
    st, steps = run_case(obs, req('ada.new@example.org'))
    o = ops(steps)
    return st == 'INCOMPLETE' and ('REDACT_RECORD', 'tombstone_3', '') in o and ('VERIFY_RECORD_REDACTED', 'tombstone_3', '') in o

@case
def similar_email_is_not_the_subject():
    obs = [mk('evidence_2', '2026-03-05T10:00:00Z', 'search_8', {'result': 'hit', 'event': 'index_query_completed', '_coll': 'x', 'email': 'ada.new2@example.org'}, 'log', None, [])]
    st, steps = run_case(obs, req('ada.new@example.org'))
    return all(s['resource_id'] != 'search_8' for s in steps)

@case
def model_media_output_is_validated_and_usage_is_counted():
    from llm import assist, client
    client.USAGE.calls.clear()
    reply = {'content': [{'type': 'text', 'text': 'Sure: {"resources": [{"resource_id": "data_flow_7", "state": "ACTIVE", "identifiers": ["A@X.org"], "evidence": "sync on"},'
             ' {"resource_id": "made_up_1", "state": "ACTIVE"}, {"resource_id": "account_9", "state": "ACTIVE"}]}'}], 'usage': {'input_tokens': 1200, 'output_tokens': 80}}
    import tempfile, os
    p = tempfile.NamedTemporaryFile(suffix='.png', delete=False); p.write(b'\x89PNG'); p.close()
    got = assist.extract_media('evidence_x', p.name, transport=lambda body: reply)
    os.unlink(p.name)
    s = client.USAGE.summary()
    return [g['rid'] for g in got] == ['data_flow_7'] and got[0]['ids'] == ['a@x.org'] and list(s.values())[0]['input_tokens'] == 1200

@case
def model_cannot_turn_a_deletion_request_into_non_deletion_silently():
    from llm import assist
    reply = {'content': [{'type': 'text', 'text': '{"deletion_requested": false, "reason": "x"}'}], 'usage': {'input_tokens': 50, 'output_tokens': 10}}
    v = assist.classify_intent('Please delete my account', transport=lambda b: reply)
    from policy import rule_intent
    return v is False and rule_intent('Please delete my account') is True   # disagreement is surfaced, rules decide

@case
def strict_validator_rejects_empty_complete_and_bad_order():
    from output import validate_row
    bad_empty, _ = validate_row('c', 'COMPLETE', '[]')
    steps = [{'step_no': 1, 'phase': 'VERIFICATION', 'system_id': 'b', 'resource_id': 'x', 'operation': 'VERIFY_RECORD_ABSENT', 'state': 'ABSENT', 'evidence_id': 'e'},
             {'step_no': 2, 'phase': 'VERIFICATION', 'system_id': 'a', 'resource_id': 'x', 'operation': 'VERIFY_RECORD_ABSENT', 'state': 'ABSENT', 'evidence_id': 'e'}]
    import json
    bad_order, _ = validate_row('c', 'COMPLETE', json.dumps(steps))
    return bool(bad_empty) and any('out of order' in e for e in bad_order)

@case
def identity_graph_never_merges_by_similarity_and_explains_edges():
    from identity import resolve_explained
    uid, ids, why = resolve_explained('ada.old@example.org', USERS, AUDIT)
    other, _, _ = resolve_explained('ada.new2@example.org', USERS, AUDIT)
    return uid == 'user_900' and other is None and 'previously used' in why['rationale'] and why['edges']['ada.old@example.org']

@case
def rules_csv_drives_the_plan():
    from policy.rule_engine import RuleEngine
    import tempfile, os
    p = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False)
    p.write('rule_id,data_category,condition,required_action\nr1,SEARCH_INDEX_ENTRY,Always,RETAIN\nr2,ANALYTICS_PROFILE,Always,DELETE\n'); p.close()
    e = RuleEngine(p.name); os.unlink(p.name)
    return e.treatment('search').verification == 'VERIFY_RECORD_PRESENT' and e.treatment('analytics').remediation == 'DELETE_RECORD' \
        and e.treatment('account').remediation == 'DELETE_RECORD'      # untouched categories keep their defaults

@case
def dependency_check_flags_an_unsafe_order():
    from planning import check_plan
    mk_ = lambda n, op, r: {'step_no': n, 'operation': op, 'resource_id': r}
    safe = [mk_(1, 'DISABLE_DATA_FLOW', 'f'), mk_(2, 'DELETE_RECORD', 'a'), mk_(3, 'VERIFY_RECORD_ABSENT', 'a'), mk_(4, 'VERIFY_DATA_FLOW_DISABLED', 'f')]
    unsafe = [mk_(1, 'DELETE_RECORD', 'a'), mk_(2, 'DISABLE_DATA_FLOW', 'f')]
    return check_plan(safe) == [] and len(check_plan(unsafe)) == 1

@case
def absence_needs_coverage_not_just_silence():
    from investigation.coverage import CoverageTracker
    t = CoverageTracker([('account_service', 'evidence_1', '2026-03-01T10:00:00Z')], {'evidence_1': '2026-03-01T10:00:00Z'})
    return t.absence('account_service', '2026-03-10T00:00:00Z', None) == ('COVERED', 'evidence_1') and \
        t.absence('account_service', '2026-02-01T00:00:00Z', None) == ('UNRESOLVED', '') and \
        t.absence('account_service', '2026-03-10T00:00:00Z', {'file_id': 'evidence_9'}) == ('CONFIRMED', 'evidence_9')

@case
def timestamps_are_normalised_so_string_comparison_is_safe():
    from common.timeutil import norm_ts
    return (norm_ts('2026-03-10 00:00:00') == '2026-03-10T00:00:00Z' and norm_ts('2026-03-10T02:00:00.5+02:00') == '2026-03-10T00:00:00Z'
            and norm_ts('2026-03-10') == '2026-03-10T00:00:00Z' and norm_ts('???') == '???')

@case
def unverifiable_requester_is_not_a_deletion_and_is_queued():
    import main as app
    w = world([])
    c = Case(req('stranger@nowhere.test'), False); infer(w, [c])
    st, steps, ex, flags = app.audit_case(w, c)
    return st == 'NOT_APPLICABLE' and steps == [] and 'identity_unresolved' in flags

@case
def subject_with_no_evidence_never_gets_an_empty_success():
    import main as app
    w = world([])
    c = Case(req('ada.new@example.org'), False); infer(w, [c])
    st, steps, ex, flags = app.audit_case(w, c)
    return st == 'NOT_APPLICABLE' and 'no_resources_found' in flags

@case
def missing_retained_audit_record_and_coverage_only_absence_are_queued():
    from output import build_review
    obs = [mk('evidence_1', '2026-03-01T09:00:00Z', 'search_5', {'result': 'miss', 'event': 'index_query_completed', '_coll': 'x'}, 'log', None, ['ada.new@example.org'])]
    import main as app
    w = world(obs); c = Case(req('ada.new@example.org'), False); infer(w, [c])
    st, steps, ex, flags = app.audit_case(w, c)
    rows = build_review([(c, st, ex, flags)])
    return st == 'COMPLETE' and rows and 'retention_unconfirmed' in rows[0][3]

@case
def model_prompt_never_contains_direct_identifiers():
    from llm import assist
    t = assist.mask_pii('Delete ada.new@example.org, call +44 7000 111 222, hash ' + 'a' * 64)
    return '@' not in t and '7000' not in t and 'a' * 20 not in t

@case
def unknown_rule_action_never_destroys_data():
    from policy.rule_engine import RuleEngine
    import tempfile, os
    p = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False)
    p.write('rule_id,data_category,condition,required_action\nr1,SEARCH_INDEX_ENTRY,Always,OBLITERATE\n'); p.close()
    e = RuleEngine(p.name); os.unlink(p.name)
    return e.treatment('search').remediation is None

@case
def pdf_text_layer_is_read_offline():
    from ingestion.media_loader import pdf_text
    p = os.path.join(DS, 'evidence', 'documents', 'delivery_correction_attachment.pdf')
    return not os.path.exists(p) or 'support_001' in pdf_text(p)

@case
def verified_transcription_is_never_overridden_by_the_model():
    from ingestion import media_loader as ml
    from llm import assist
    old, old_use = assist.extract_media_text, ml.USE_LLM
    try:
        ml.USE_LLM = True
        assist.extract_media_text = lambda fid, text, transport=None: [
            dict(rid='account_9', state='PRESENT', ids=['a@x.org'], note=''), dict(rid='account_77', state='PRESENT', ids=['b@x.org'], note='')]
        text = 'Customer page account_9 a@x.org account_77 b@x.org'
        out = ml._merge_ai('evidence_x', text, [dict(rid='account_9', state='EXPOSED', ids=['a@x.org'], note='t')])
        return [f['rid'] for f in out] == ['account_9'] and out[0]['state'] == 'EXPOSED'
    finally: assist.extract_media_text, ml.USE_LLM = old, old_use

@case
def unseen_artifact_is_read_by_the_ai_pipeline_with_grounding():
    from ingestion import media_loader as ml
    from llm import assist
    old, old_use = assist.extract_media_text, ml.USE_LLM
    try:
        ml.USE_LLM = True
        assist.extract_media_text = lambda fid, text, transport=None: [dict(rid='data_flow_5', state='ACTIVE', ids=['z@x.org'], note='')]
        out = ml._merge_ai('evidence_new', 'Connector data_flow_5 selector z@x.org Healthy Continuous', [])
        ml.USE_LLM = False
        out2 = ml._merge_ai('evidence_new', 'Connector data_flow_5 selector z@x.org Healthy Continuous', [])      # rules only
        return out and out[0]['rid'] == 'data_flow_5' and out[0]['ids'] == ['z@x.org'] and out2 and out2[0]['state'] == 'ACTIVE'
    finally: assist.extract_media_text, ml.USE_LLM = old, old_use

@case
def ungrounded_model_output_is_dropped():
    from llm.assist import validate_media
    got = validate_media({'resources': [{'resource_id': 'account_1', 'state': 'PRESENT', 'identifiers': ['ghost@x.org']},
                                        {'resource_id': 'account_2', 'state': 'PRESENT'}]}, 'only account_1 is printed here')
    return [g['rid'] for g in got] == ['account_1'] and got[0]['ids'] == []

def run():
    ok = True
    for f in CASES:
        try: res = bool(f())
        except Exception as e: res = False; print('  error', f.__name__, repr(e))
        print(('PASS ' if res else 'FAIL ') + f.__name__); ok &= res
    return ok

if __name__ == '__main__': sys.exit(0 if run() else 1)
