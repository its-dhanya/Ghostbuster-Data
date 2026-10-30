"""Resource discovery for each case.

1. Direct links: every observation that carries one of the subject's identifiers (current or historical email, hash,
   phone, user_id) inside the case's time frame (identifier look-back .. audit_at).
2. Activity inference, for records that carry no identifier by design (a deleted account answers 404, an anonymized
   row has no email, a redacted ticket has none): the deletion worker's activity events are matched to cases by
   (a) offset from `reported_at`, learned from identifier-linked data, (b) result vs `reported_status`,
   (c) shared evidence files, (d) one resource per case and kind. Same-day cases with identical signatures are a genuine
   tie; the pairing is then deterministic but arbitrary and flagged in the provenance as `tie`."""
from collections import defaultdict
from datetime import datetime, timedelta
from common.constants import SETTINGS, kind_of
from common.timeutil import norm_ts
from identity import resolve_explained
from policy import intent
from planning import build_steps

P = lambda s: datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
RES = SETTINGS['result_for_reported_status']
ACCOUNT_WIN = tuple(SETTINGS['account_window_minutes'])
ACCOUNT_WIN_WIDE = tuple(SETTINGS['account_window_wide_minutes'])
WIDE_CLEAN = tuple(SETTINGS['clean_window_wide_minutes'])
CLEAN_EVENTS = {k: (v['event'], v['system'], tuple(v['window'])) for k, v in SETTINGS['clean_event_windows_minutes'].items()}

class Case:
    def __init__(self, req, sample):
        req = dict(req)
        for k in ('requested_at', 'reported_at', 'audit_at'): req[k] = norm_ts(req[k])
        self.req = req; self.id = req['case_id']; self.sample = sample
        self.rep = P(req['reported_at'])
        self.rids = set(); self.inferred = set(); self.prov = {}; self.identity = None

def prepare(world, cases):
    for c in cases:
        c.uid, c.ids, c.identity = resolve_explained(c.req['email'], world.users, world.audit)
        c.deletion = intent.wants_deletion(c.req['request_text'])
        if c.deletion and c.uid and not intent.POS.search(c.req['request_text']):
            # weak wording: the privacy-intake classification of the subject's account decides
            if any(a['event_type'] == 'CLASSIFY_REQUEST' for r in world.linked_rids(c.ids) for a in world.act_by_rid.get(r, [])):
                c.deletion = False
        since = (P(c.req['requested_at']) - timedelta(days=SETTINGS['identifier_lookback_days'])).strftime('%Y-%m-%dT%H:%M:%SZ')
        c.since = since
        c.rids = set(world.linked_rids(c.ids, since, c.req['audit_at'])) if c.uid else set()
        c.prov = {r: {'method': 'identifier', 'links': world.link_evidence(c.ids, r, since, c.req['audit_at'])[:3]} for r in c.rids}
    owner = defaultdict(set)
    for c in cases:
        for r in c.rids: owner[r].add(c.id)
    return owner

def has_violation(world, c):
    f, _, _ = build_steps(world, c.req, c.rids)
    return bool(f)

def case_files(world, c):
    fs = set()
    for r in c.rids:
        for o in world.by_rid.get(r, []):
            if o['file_t'] <= c.req['audit_at']: fs.add(o['file_id'])
    return fs

def calibrate(world, elig):
    """Learn the activity-time windows from identifier-linked resources; keep the configured defaults when there is
    too little support."""
    global ACCOUNT_WIN, CLEAN_EVENTS
    def offs(pred):
        out = []
        for c in elig:
            for r in c.rids:
                for a in world.act_by_rid.get(r, []):
                    d = (P(a['event_time']) - c.rep).total_seconds() / 60
                    if pred(a, r) and -200 < d < 20: out.append(d)
        return out
    acc = [d for d in offs(lambda a, r: a['event_type'] == 'DELETE_RECORD' and a['target_system'] == 'account_service') if d < -20]
    if len(acc) >= 30: ACCOUNT_WIN = (min(acc) - 3, max(acc) + 3)
    new = {}
    for k, (et, ts, win) in CLEAN_EVENTS.items():
        v = offs(lambda a, r, et=et, ts=ts, k=k: a['event_type'] == et and a['target_system'] == ts and a['reported_result'] == 'SUCCESS' and world.kind(r) == k)
        new[k] = (et, ts, (min(v) - 2, max(v) + 2)) if len(v) >= 5 else (et, ts, win)
    CLEAN_EVENTS = new

def score(c):
    return sum(1 for r in c.rids if kind_of(r) in CLEAN_EVENTS)


# ---------------------------------------------------------------- per-case timing signature
# All activity events of one case share a sub-minute jitter: second(event) = base(case) + constant(event kind), so
# the seconds of two events of the same case differ by a kind-specific constant (+-1). That constant is learned from
# identifier-linked cases and then scores which unattributed event belongs to which case.
import math
from itertools import combinations

def ev_label(a):
    return f"{a['event_type']}:{a['target_system']}:{'S' if a['reported_result'] == 'SUCCESS' else 'X'}"

def ev_coarse(a):
    return f"{a['event_type']}:{a['target_system']}"

def ev_sec(a): return P(a['event_time']).second

def known_events(world, c, window=(-135, 150)):
    out = []
    for r in c.rids:
        for a in world.act_by_rid.get(r, []):
            if a['event_type'] in ('LINK_RESOURCE_IDENTITY', 'CLASSIFY_REQUEST'): continue
            d = (P(a['event_time']) - c.rep).total_seconds() / 60
            if window[0] <= d <= window[1]: out.append(a)
    return out

class Signature:
    MIN_PAIRS = 8
    def __init__(self, world, cases):
        self.h = {}
        for c in cases:
            evs = known_events(world, c)
            for lab in (ev_label, ev_coarse):                      # fine (with result) and coarse labels
                by = {}
                for a in evs: by.setdefault(lab(a), a)          # one event per label and case
                for (la, a), (lb, b) in combinations(sorted(by.items()), 2):
                    d = (ev_sec(b) - ev_sec(a)) % 60
                    self.h.setdefault((la, lb), [0] * 60)[d] += 1
                    self.h.setdefault((lb, la), [0] * 60)[(-d) % 60] += 1

    def llr(self, cand, known):
        """log-likelihood ratio that `cand` and the case's `known` events share one jitter (0 when uninformative)"""
        la, sa = ev_label(cand), ev_sec(cand); total = 0.0
        for k in known:
            hist = self.h.get((ev_label(k), la))
            if not hist or sum(hist) < self.MIN_PAIRS: hist = self.h.get((ev_coarse(k), ev_coarse(cand)))   # coarser, more data
            if not hist or sum(hist) < self.MIN_PAIRS: continue
            d = (sa - ev_sec(k)) % 60
            near = hist[(d - 1) % 60] + hist[d] + hist[(d + 1) % 60]
            total += math.log(((near + 0.5) / (sum(hist) + 30)) / (3 / 60))
        return total

def assign(cases, events, weight):
    """maximum-weight one-to-one assignment (each case and event at most once) per connected component.
    weight(case, event) -> number or None (not a candidate). Exact DP for small components, greedy beyond."""
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    edges = {}
    for c in cases:
        for i, e in enumerate(events):
            w = weight(c, e)
            if w is not None:
                edges[(c.id, i)] = w; parent[find(('c', c.id))] = find(('e', i))
    comps = {}
    for (cid, i) in edges: comps.setdefault(find(('c', cid)), set()).add((cid, i))
    result = {}
    for comp in comps.values():
        cs = sorted({cid for cid, _ in comp}); es = sorted({i for _, i in comp})
        if len(es) <= 12:
            best = {}
            def solve(ci, mask):
                if ci == len(cs): return 0.0, ()
                key = (ci, mask)
                if key in best: return best[key]
                r = solve(ci + 1, mask)                              # leave this case unassigned
                for j, i in enumerate(es):
                    if mask >> j & 1 or (cs[ci], i) not in edges: continue
                    sub, pick = solve(ci + 1, mask | 1 << j)
                    val = 1e6 + edges[(cs[ci], i)] + sub
                    if val > r[0] + 1e-9: r = (val, ((cs[ci], i),) + pick)
                best[key] = r; return r
            for cid, i in solve(0, 0)[1]: result[cid] = i
        else:
            used = set()
            for (cid, i), w in sorted(edges.items(), key=lambda kv: -kv[1]):
                if (cid, i) in comp and cid not in result and i not in used: result[cid] = i; used.add(i)
    return result

def infer(world, cases, truth=None, blind=()):
    """truth: optional {case_id: resources} for the supplied sample cases; those cases are then fixed (their resources
    are owned) instead of being inferred, which removes them from other cases' candidate pools."""
    owner = prepare(world, cases)
    fixed = set()
    if truth:
        for c in cases:
            if c.id in truth and c.sample:
                for r in c.rids: owner[r].discard(c.id)
                c.rids = set(truth[c.id]); fixed.add(c.id)
                for r in c.rids: owner[r].add(c.id)
    for c in cases:                                   # evaluation helper: hide the directly linked account of these cases
        if c.id in blind:
            for r in [r for r in c.rids if kind_of(r) == 'account']:
                c.rids.discard(r); owner[r].discard(c.id)
    elig = [c for c in cases if c.deletion and c.uid and c.id not in fixed]
    calibrate(world, elig)
    for c in elig:
        c.viol = has_violation(world, c); c.files = case_files(world, c)
    def rfiles(rid):
        return {o['file_id'] for o in world.by_rid.get(rid, [])}
    sig = Signature(world, [c for c in cases if c.uid])
    # ---- accounts: exactly one deletion event per case
    ev_acc = sorted([a for a in world.acts if a['event_type'] == 'DELETE_RECORD' and a['target_system'] == 'account_service'
                     and not owner.get(a['resource_id'])], key=lambda a: (a['resource_id'], a['event_time']))
    need = sorted([c for c in elig if not any(kind_of(r) == 'account' for r in c.rids)], key=lambda c: c.id)
    for c in need: c.known = known_events(world, c)
    def acct_weight(c, a):
        off = (P(a['event_time']) - c.rep).total_seconds() / 60
        tight = ACCOUNT_WIN[0] <= off <= ACCOUNT_WIN[1]
        if not tight and not (ACCOUNT_WIN_WIDE[0] <= off <= ACCOUNT_WIN_WIDE[1]): return None
        rf = rfiles(a['resource_id'])
        return (0 if tight else -5000) + 100 * (a['reported_result'] == RES[c.req['reported_status']]) + 3 * sig.llr(a, c.known) + min(len(rf & c.files), 5)
    pairs = assign(need, ev_acc, acct_weight)
    for c in need:
        if c.id not in pairs: continue
        a = ev_acc[pairs[c.id]]
        n = sum(1 for x in ev_acc if acct_weight(c, x) is not None and acct_weight(c, x) > -4000)
        c.inferred.add(a['resource_id']); owner[a['resource_id']].add(c.id); c.known.append(a)
        c.prov[a['resource_id']] = {'method': 'activity', 'activity_id': a['activity_id'], 'event': a['event_type'],
                                    'offset_min': round((P(a['event_time']) - c.rep).total_seconds() / 60, 1),
                                    'candidates': n, 'tie': n > 1, 'signature_llr': round(sig.llr(a, c.known[:-1]), 2)}
    # ---- clean-kind resources (COMPLETE-looking cases only)
    for c in elig:
        if not hasattr(c, 'known'): c.known = known_events(world, c)
    for kind, (et, ts, win) in CLEAN_EVENTS.items():
        evs = sorted([a for a in world.acts if a['event_type'] == et and a['target_system'] == ts and a['reported_result'] == 'SUCCESS'
                      and not owner.get(a['resource_id'])], key=lambda a: (a['resource_id'], a['event_time']))
        cs_all = sorted([c for c in elig if not c.viol and not any(kind_of(r) == kind for r in c.rids)], key=lambda c: c.id)
        def clean_weight(c, a):
            off = (P(a['event_time']) - c.rep).total_seconds() / 60
            tight = win[0] <= off <= win[1]
            if not tight and not (WIDE_CLEAN[0] <= off <= WIDE_CLEAN[1]): return None
            rf = rfiles(a['resource_id'])
            if rf and c.files and not (rf & c.files): return None
            return (0 if tight else -5000) + 3 * sig.llr(a, c.known) + 0.01 * score(c) + (min(len(rf & c.files), 5) if rf else 0)
        pairs = assign(cs_all, evs, clean_weight)
        for c in cs_all:
            if c.id not in pairs: continue
            a = evs[pairs[c.id]]
            n = sum(1 for x in cs_all if clean_weight(x, a) is not None)
            c.inferred.add(a['resource_id']); owner[a['resource_id']].add(c.id); c.known.append(a)
            c.prov[a['resource_id']] = {'method': 'activity', 'activity_id': a['activity_id'], 'event': a['event_type'],
                                        'offset_min': round((P(a['event_time']) - c.rep).total_seconds() / 60, 1),
                                        'candidates': n, 'tie': n > 1, 'signature_llr': round(sig.llr(a, c.known[:-1]), 2)}
    for c in elig: c.rids |= c.inferred
    return elig
