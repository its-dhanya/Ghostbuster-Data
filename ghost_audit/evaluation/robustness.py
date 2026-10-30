"""Robustness suite: the pipeline must give the same answer when the export is re-ordered, must survive noise and
missing media, and must keep working on a different export of the dataset (GHOST_DATASET_DIR).

  python3 ghost_audit/evaluation/robustness.py
"""
import csv, os, random, shutil, subprocess, sys, tempfile, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); CODE = os.path.dirname(HERE); ROOT = os.path.dirname(CODE)

def run(dataset, out_dir, env_extra=None):
    env = dict(os.environ, GHOST_DATASET_DIR=dataset, GHOST_OUTPUT_DIR=out_dir, PYTHONHASHSEED=str(random.randint(1, 999)))
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, os.path.join(CODE, 'main.py'), '--no-llm'], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

def digest(path): return hashlib.md5(open(path, 'rb').read()).hexdigest()

def shuffled_copy(src, dst, seed):
    shutil.copytree(src, dst)
    rnd = random.Random(seed)
    for name in ('deletion_requests.csv', 'system_activity.csv', 'evidence_files.csv', 'user_identities.csv', 'user_audit_log.csv'):
        p = os.path.join(dst, name)
        with open(p, newline='', encoding='utf-8') as f: rows = list(csv.reader(f))
        head, body = rows[0], rows[1:]; rnd.shuffle(body)
        with open(p, 'w', newline='', encoding='utf-8') as f: csv.writer(f).writerows([head] + body)

def main():
    ds = os.path.join(ROOT, 'dataset'); results = []
    tmp = tempfile.mkdtemp()
    try:
        base_out = os.path.join(tmp, 'base'); os.makedirs(base_out)
        rc, msg = run(ds, base_out); base = digest(os.path.join(base_out, 'output.csv'))
        results.append(('baseline run', rc == 0))
        for seed in (1, 2):
            d = os.path.join(tmp, f'shuf{seed}'); o = os.path.join(tmp, f'o{seed}'); os.makedirs(o)
            shuffled_copy(ds, d, seed); rc, msg = run(d, o)
            results.append((f'row order shuffled (seed {seed}) gives identical output', rc == 0 and digest(os.path.join(o, 'output.csv')) == base))
        # noise: append unparseable lines to every log, and a junk row to the activity stream
        d = os.path.join(tmp, 'noise'); o = os.path.join(tmp, 'on'); os.makedirs(o); shutil.copytree(ds, d)
        for root, _, files in os.walk(os.path.join(d, 'evidence', 'logs')):
            for fn in files:
                with open(os.path.join(root, fn), 'a', encoding='utf-8') as f: f.write('\n%%% not a log line %%%\n2026-13-99T99:99:99Z ???\n')
        rc, msg = run(d, o)
        results.append(('garbage log lines are ignored', rc == 0 and digest(os.path.join(o, 'output.csv')) == base))
        # no media at all: manifest rows for PNG/PDF removed -> must still run and validate
        d = os.path.join(tmp, 'nomedia'); o = os.path.join(tmp, 'om'); os.makedirs(o); shutil.copytree(ds, d)
        p = os.path.join(d, 'evidence_files.csv')
        rows = [r for r in csv.reader(open(p, encoding='utf-8')) if not r[1].endswith(('.png', '.pdf'))]
        csv.writer(open(p, 'w', newline='', encoding='utf-8')).writerows(rows)
        rc, msg = run(d, o)
        results.append(('runs and validates without any image/PDF evidence', rc == 0 and os.path.exists(os.path.join(o, 'output.csv'))))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = True
    for name, r in results: print(('PASS ' if r else 'FAIL ') + name); ok &= r
    return ok

if __name__ == '__main__': sys.exit(0 if main() else 1)
