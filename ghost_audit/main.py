"""Ghost Data Still Exists - deletion audit agent.

  python3 ghost_audit/main.py              AI-assisted run: a local Ollama (or ANTHROPIC_API_KEY) reads artifact text and gives
                                    an intent verdict; every proposal is grounded, validated and cross-checked by
                                    deterministic code. Falls back to the deterministic stages when no model is reachable.
  python3 ghost_audit/main.py --no-llm     deterministic stages only
  python3 ghost_audit/main.py --explain    also write ghost_audit/evaluation/provenance.jsonl (why each resource and state)
  python3 ghost_audit/main.py --no-sample-truth   blind run: the supplied sample answers are not used at all

Side files (ghost_audit/evaluation/): review_queue.csv (cases that rest on inference or missing evidence), run_manifest.json
(hashes of inputs, code and output), usage_report.md.

Pipeline: ingestion -> identity graph -> evidence index -> activity inference -> temporal state -> policy engine
-> remediation planner -> strict validator -> output.csv.
"""
import argparse, csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingestion
from common.constants import DS, CODE, OUT_DIR
from policy import intent
from investigation import World, Case, infer, explain_case
from investigation.provenance import write_jsonl
from planning import build_steps, emit, check_plan
from output import write_output, write_usage_report, case_row, build_review, write_review, write_manifest

def load_cases():
    hidden = [Case(r, False) for r in csv.DictReader(open(f'{DS}/deletion_requests.csv', encoding='utf-8'))]
    samp = [Case(r, True) for r in csv.DictReader(open(f'{DS}/sample_deletion_requests.csv', encoding='utf-8'))]
    return hidden, samp

def sample_truth():
    t = {}
    for r in csv.DictReader(open(f'{DS}/sample_output.csv', encoding='utf-8')):
        t[r['case_id']] = {s['resource_id'] for s in json.loads(r['steps_json'])}
    return t

def audit_case(w, c):
    """-> (status, steps, explain, flags). Never returns an empty COMPLETE/INCOMPLETE: a requester that cannot be
    verified, or a subject with no evidence at all, is not an authorised, verifiable deletion."""
    ex = {}
    if not c.deletion: return 'NOT_APPLICABLE', [], ex, set()
    if not c.uid: return 'NOT_APPLICABLE', [], ex, {'identity_unresolved'}
    try:
        st, steps = emit(*build_steps(w, c.req, c.rids, ex))
    except Exception as e:                      # degrade to the account/audit records instead of losing the row
        print(f'warning: {c.id} failed ({e!r}); retrying with account and audit records only', file=sys.stderr)
        ex = {}
        st, steps = emit(*build_steps(w, c.req, {r for r in c.rids if r.startswith(('account', 'audit_record'))}, ex))
    if not steps: return 'NOT_APPLICABLE', [], ex, {'no_resources_found'}
    return st, steps, ex, set()

def main(use_llm=None, write=True, explain=False, sample_truth_on=True):
    """use_llm: None = automatic (AI stages run whenever a model provider is reachable), False = deterministic only."""
    from llm import client
    use_llm = client.enabled() if use_llm is None else (use_llm and client.enabled())
    ingestion.set_use_llm(use_llm); intent.USE_LLM = use_llm
    w = World()
    hidden, samp = load_cases()
    # resources the supplied sample answers already attribute to sample cases are not candidates for other cases
    infer(w, hidden + samp, sample_truth() if sample_truth_on else None)
    rows, unsafe, results = [], [], []
    for c in sorted(hidden, key=lambda c: c.id):
        st, steps, ex, flags = audit_case(w, c)
        unsafe += [f'{c.id}: {m}' for m in check_plan(steps)]
        rows.append(case_row(c, (st, steps))); results.append((c, st, ex, flags))
    review = build_review(results)
    if unsafe: print('warning: canonical order violates a dependency:', unsafe[:5], file=sys.stderr)
    if write:
        _, warns = write_output(rows, [c.id for c in hidden])
        write_usage_report(len(rows), use_llm, ingestion.media_notes() + intent.NOTES)
        write_review(review, os.path.join(CODE, 'evaluation', 'review_queue.csv'))
        write_manifest(os.path.join(CODE, 'evaluation', 'run_manifest.json'), os.path.join(OUT_DIR, 'output.csv'),
                       'model-assisted' if use_llm else 'deterministic', len(rows), review)
        if explain: write_jsonl(os.path.join(CODE, 'evaluation', 'provenance.jsonl'), [explain_case(w, c) for c in sorted(hidden, key=lambda c: c.id)])
    else:
        from output import validate_rows
        _, warns = validate_rows(rows, [c.id for c in hidden])
    main.review = review
    return rows, warns

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--use-llm', action='store_true', help='kept for compatibility: model stages are on automatically when a provider is reachable')
    ap.add_argument('--no-llm', action='store_true', help='deterministic run only: skip the model-assisted stages'); ap.add_argument('--explain', action='store_true')
    ap.add_argument('--no-sample-truth', action='store_true', help='do not use the supplied sample answers to reserve resources (blind run)')
    a = ap.parse_args()
    from llm import client
    use = False if a.no_llm else None
    if use is None and not client.enabled(): print('no model provider (start Ollama or set ANTHROPIC_API_KEY): deterministic stages only')
    elif use is None: print(f'model provider: {client.provider()} / {client.model_name()}')
    rows, warns = main(use, explain=a.explain, sample_truth_on=not a.no_sample_truth)
    from collections import Counter
    print(len(rows), dict(Counter(r[1] for r in rows)), f'validated; {len(warns)} warnings; {len(main.review)} cases in the review queue')
