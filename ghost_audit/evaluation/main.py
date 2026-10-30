"""Evaluation harness.

  python3 ghost_audit/evaluation/main.py

1. Scores the pipeline on the 32 supplied sample cases (blind: sample answers are NOT used to infer anything).
2. Runs the hand-built synthetic cases in custom_cases.py.
Writes a metrics summary to stdout; evaluation_report.md records the numbers from the last run.
"""
import csv, json, os, sys
from compare import compare_case, render
from taxonomy import classify, summarize
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.constants import DS
from investigation import World, Case, infer
from planning import build_steps, emit

FIELDS = ['step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id']
KEY = lambda s: (s['operation'], s['system_id'], s['resource_id'])

def lcs(a, b):
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            m[i + 1][j + 1] = m[i][j] + 1 if a[i] == b[j] else max(m[i][j + 1], m[i + 1][j])
    return m[-1][-1]

DIFFS = []
TAX = {}

def score_samples(use_llm=False):
    import ingestion
    from policy import intent
    from llm import client
    ingestion.set_use_llm(use_llm and client.enabled()); intent.USE_LLM = use_llm and client.enabled()
    w = World()
    hidden = [Case(r, False) for r in csv.DictReader(open(f'{DS}/deletion_requests.csv', encoding='utf-8'))]
    samp = [Case(r, True) for r in csv.DictReader(open(f'{DS}/sample_deletion_requests.csv', encoding='utf-8'))]
    infer(w, hidden + samp)                       # blind: no sample truth
    exp = {r['case_id']: r for r in csv.DictReader(open(f'{DS}/sample_output.csv', encoding='utf-8'))}
    m = dict(cases=0, status_ok=0, seq_exact=0, tp=0, p=0, e=0, tp_ev=0, field=dict.fromkeys(FIELDS, 0), matched=0, lcs=0, total_e=0)
    rows = []
    for c in samp:
        if not c.deletion: st, steps = 'NOT_APPLICABLE', []
        else: st, steps = emit(*build_steps(w, c.req, c.rids))
        gold = json.loads(exp[c.id]['steps_json'])
        m['cases'] += 1; m['status_ok'] += st == exp[c.id]['deletion_status']
        m['seq_exact'] += steps == gold
        G = {KEY(s): s for s in gold}; Pp = {KEY(s): s for s in steps}
        m['tp'] += len(set(G) & set(Pp)); m['p'] += len(Pp); m['e'] += len(G)
        for k in set(G) & set(Pp):
            m['matched'] += 1
            for f in FIELDS: m['field'][f] += G[k][f] == Pp[k][f]
        m['tp_ev'] += sum(1 for k in set(G) & set(Pp) if G[k]['evidence_id'] == Pp[k]['evidence_id'])
        m['lcs'] += lcs([KEY(s) for s in gold], [KEY(s) for s in steps]); m['total_e'] += len(gold)
        rows.append((c.id, st == exp[c.id]['deletion_status'], steps == gold))
        if steps != gold or st != exp[c.id]['deletion_status']:
            d = compare_case(exp[c.id]['deletion_status'], gold, st, steps)
            DIFFS.append(render(c.id, d)); TAX[c.id] = classify(c.id, d)
    return m, rows

def report(m):
    prec = m['tp'] / m['p']; rec = m['tp'] / m['e']
    out = {
        'case-level status accuracy': f"{m['status_ok']}/{m['cases']} = {m['status_ok'] / m['cases']:.3f}",
        'step precision (operation+system+resource)': f'{prec:.3f}',
        'step recall': f'{rec:.3f}',
        'step F1': f'{2 * prec * rec / (prec + rec):.3f}',
        'sequence accuracy (exact steps_json equality)': f"{m['seq_exact']}/{m['cases']} = {m['seq_exact'] / m['cases']:.3f}",
        'ordered-step similarity (LCS / gold steps)': f"{m['lcs'] / m['total_e']:.3f}",
    }
    for f in FIELDS: out[f'field accuracy: {f} (on matched steps)'] = f"{m['field'][f] / m['matched']:.3f}"
    return out

if __name__ == '__main__':
    m, rows = score_samples('--llm' in sys.argv)
    print('mode:', 'AI-assisted stages on' if '--llm' in sys.argv else 'deterministic stages (add --llm for the AI-assisted run)')
    for k, v in report(m).items(): print(f'{k}: {v}')
    print('cases with non-exact sequence:', [r[0] for r in rows if not r[2]])
    print('error taxonomy (sample cases):'); print('\n'.join('  ' + x for x in summarize(TAX)))
    if '-v' in sys.argv: print('\n'.join(DIFFS))
    import custom_cases
    ok = custom_cases.run()
    sys.exit(0 if ok else 1)
