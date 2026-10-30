"""Rows -> validated output.csv, plus the usage report."""
import csv, json, os
from common.constants import CODE, OUT_DIR
from .validator import validate_rows

def case_row(case, steps_result):
    st, steps = steps_result
    return (case.id, st, json.dumps(steps, separators=(',', ':')))

def write_output(rows, expected_ids):
    errs, warns = validate_rows(rows, expected_ids)
    if errs: raise SystemExit('output validation failed:\n' + '\n'.join(errs[:20]))
    out = os.path.join(OUT_DIR, 'output.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['case_id', 'deletion_status', 'steps_json']); w.writerows(rows)
    return out, warns

def write_usage_report(n_requests, llm_mode, notes):
    from llm import client
    per = client.USAGE.summary()
    price_in, price_out = os.environ.get('LLM_PRICE_IN'), os.environ.get('LLM_PRICE_OUT')
    L = ['# Usage report - final full-dataset run', '',
         f'Run mode: **{"model-assisted (--use-llm)" if llm_mode else "deterministic, no model calls"}**; {n_requests} requests.', '']
    if not per:
        L += ['No model call was made in the run that produced `output.csv`.', '',
              '| Item | Value |', '| --- | --- |', '| Model providers / models | none |', '| Model calls | 0 |',
              '| Input / output tokens | 0 / 0 |', '| Total tokens, average per request | 0, 0 |',
              '| Estimated total cost, per request | $0.00, $0.00 |']
    else:
        L += ['| Provider | Model | Calls | Failed | Input tokens | Output tokens | Est. cost (USD) |', '| --- | --- | --- | --- | --- | --- | --- |']
        ti = to = tc = 0; cost_total = 0.0
        for (prov, model), m in sorted(per.items()):
            cost = (m['input_tokens'] * float(price_in) + m['output_tokens'] * float(price_out)) / 1e6 if price_in and price_out else None
            L.append(f"| {prov} | {model} | {m['calls']} | {m['failed']} | {m['input_tokens']} | {m['output_tokens']} | {'%.4f' % cost if cost is not None else 'unpriced (set LLM_PRICE_IN/OUT)'} |")
            ti += m['input_tokens']; to += m['output_tokens']; tc += m['calls']; cost_total += cost or 0
        L += ['', f'Overall: {tc} calls, {ti} input + {to} output = {ti + to} tokens; average {(ti + to) / n_requests:.1f} tokens per request; '
              + (f'estimated cost ${cost_total:.4f} (${cost_total / n_requests:.5f} per request).' if price_in and price_out else 'cost not estimated (no price configured).'),
              'Token counts are the provider-reported usage, including retries.']
    from llm import assist
    if assist.HITS['intent'] or assist.HITS['media']:
        L += ['', f"Replies reused from the local cache in this run (no model call, no tokens): {assist.HITS['intent']} intent, {assist.HITS['media']} artifact extractions. Their original token cost was recorded in the run that first produced them."]
    if notes: L += ['', '## Model cross-check notes', ''] + [f'* {n}' for n in notes]
    open(os.path.join(CODE, 'evaluation', 'usage_report.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
