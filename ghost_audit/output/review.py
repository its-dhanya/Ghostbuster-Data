"""Human-review queue and run manifest.

output.csv must contain only the three contract statuses, so uncertainty cannot be expressed there. Anything the
audit could not establish from evidence is written to a side file instead: review_queue.csv lists the cases whose
verdict rests on an inference or on missing evidence and says why; run_manifest.json fixes what was audited
(hashes of every input file, of the code and of the output) so a verdict can be traced to the exact evidence."""
import csv, hashlib, json, os, sys, platform
from datetime import datetime, timezone
from common.constants import DS, CODE, OUT_DIR

REASONS = {
    'identity_unresolved': ('HIGH', 'request email matches no current or historical identity; deletion is not authorised, row emitted as NOT_APPLICABLE'),
    'no_resources_found': ('HIGH', 'no record of the subject was found in any evidence; an empty plan cannot prove deletion, row emitted as NOT_APPLICABLE'),
    'ambiguous_attribution': ('LOW', 'a record without identifiers was attributed to this case by timing evidence only, and a competing case existed'),
    'absence_by_coverage_only': ('MEDIUM', 'COMPLETE rests on a snapshot that inspected the system but never listed the record (absence by omission)'),
    'retention_unconfirmed': ('MEDIUM', 'no security audit record for the subject appears in any evidence file; the required retained record could not be verified'),
    'unhandled_resource_kind': ('MEDIUM', 'linked resource of a kind the policy table does not cover was not audited'),
}

def build_review(results):
    """results: iterable of (case, status, explain_dict, flags_set)"""
    rows = []
    for c, status, ex, flags in results:
        reasons = set(flags)
        if not c.deletion: continue
        for rid, p in c.prov.items():
            if p.get('tie') and p.get('signature_llr', 0) < 3 and rid in ex: reasons.add('ambiguous_attribution')
        if status == 'COMPLETE':
            if any(d.get('confidence') in ('COVERED', 'UNRESOLVED') for k, d in ex.items() if not k.startswith('_') and d['kind'] in ('account', 'search', 'export')):
                reasons.add('absence_by_coverage_only')
        if c.uid and not any(k.startswith('audit_record') for k in c.rids): reasons.add('retention_unconfirmed')
        if ex.get('_unhandled'): reasons.add('unhandled_resource_kind')
        if reasons:
            order = {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
            sev = max((REASONS[r][0] for r in reasons), key=order.get)
            rows.append((c.id, status, sev, ';'.join(sorted(reasons))))
    return rows

def write_review(rows, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['case_id', 'deletion_status', 'severity', 'reasons']); w.writerows(sorted(rows))

def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()

def write_manifest(path, output_path, mode, n_cases, review_rows):
    inputs = {}
    for root, _, files in os.walk(DS):
        for fn in sorted(files): inputs[os.path.relpath(os.path.join(root, fn), DS)] = _sha(os.path.join(root, fn))
    code = {}
    for root, dirs, files in os.walk(CODE):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'cache')]
        for fn in sorted(files):
            if fn.endswith(('.py', '.json')) and 'evaluation' not in root.split(os.sep)[-1:]: code[os.path.relpath(os.path.join(root, fn), CODE)] = _sha(os.path.join(root, fn))
    m = {'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'python': platform.python_version(), 'mode': mode,
         'cases': n_cases, 'output_sha256': _sha(output_path), 'review_queue_cases': len(review_rows),
         'inputs_sha256': inputs, 'code_sha256': code}
    json.dump(m, open(path, 'w', encoding='utf-8'), indent=1, sort_keys=True)
    return m
