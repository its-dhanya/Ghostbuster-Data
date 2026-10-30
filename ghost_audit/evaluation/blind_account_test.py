"""Robustness probe: hide the directly-linked account of a random quarter of the unlabeled cases and check how often
activity-based inference recovers it. Run: python3 ghost_audit/evaluation/blind_account_test.py"""
import csv, json, os, random, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.constants import DS, kind_of
from investigation import World, Case, infer, prepare
w = World()
def mk():
    return ([Case(r, False) for r in csv.DictReader(open(f'{DS}/deletion_requests.csv'))],
            [Case(r, True) for r in csv.DictReader(open(f'{DS}/sample_deletion_requests.csv'))])
truth = {r['case_id']: {s['resource_id'] for s in json.loads(r['steps_json'])} for r in csv.DictReader(open(f'{DS}/sample_output.csv'))}
h0, s0 = mk(); prepare(w, h0 + s0)
gold = {c.id: {r for r in c.rids if kind_of(r) == 'account'} for c in h0}
cand = [c for c in h0 if c.uid and c.deletion and gold[c.id] and any(a['event_type'] == 'DELETE_RECORD' and a['resource_id'] in gold[c.id] for a in w.acts)]
res = collections.Counter()
for seed in range(8):
    random.seed(seed); blind = {c.id for c in random.sample(cand, len(cand) // 4)}
    h, s = mk(); infer(w, h + s, truth, blind)
    for c in h:
        if c.id in blind: res['recovered' if {r for r in c.rids if kind_of(r) == 'account'} == gold[c.id] else 'wrong'] += 1
print(dict(res), 'accuracy %.3f' % (res['recovered'] / sum(res.values())))
