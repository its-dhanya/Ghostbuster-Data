"""The indexed evidence store: every file is ingested once; lookups are by identifier, resource, system or file."""
import csv, os
from collections import defaultdict
import ingestion
from common.constants import DS, kind_of, system_of
from common.timeutil import norm_ts
from identity import load_identities
from ingestion import COVERAGE, load_links
from .resource_classifier import state_of
from .temporal_engine import state_at as _state_at
from .coverage import CoverageTracker

class World:
    def __init__(self, parts=None):
        """parts: optional (obs, meta, users, audit, acts) for synthetic evaluation worlds"""
        if parts:
            self.obs, self.meta, self.users, self.audit, self.acts = parts
            self.meta = dict(self.meta)
        else:
            self.obs, self.meta = ingestion.load_all()
            self.users, self.audit = load_identities()
            self.acts = list(csv.DictReader(open(os.path.join(DS, 'system_activity.csv'), encoding='utf-8')))
        for a in self.acts: a['event_time'] = norm_ts(a['event_time'])
        for m in self.meta.values(): m['captured_at'] = norm_ts(m['captured_at'])
        self.act_by_rid = defaultdict(list)
        for a in self.acts: self.act_by_rid[a['resource_id']].append(a)
        self.obs += load_links(self.acts)
        for o in self.obs: o['state'] = state_of(o)
        self.by_rid = defaultdict(list)                      # resource_id -> observations
        for o in self.obs: self.by_rid[o['rid']].append(o)
        self.by_id = defaultdict(list)                       # identifier  -> observations
        for o in self.obs:
            for i in o['ids']: self.by_id[i].append(o)
        self.coverage = CoverageTracker(COVERAGE, {fid: m['captured_at'] for fid, m in self.meta.items()})
        self.marketing = set()                               # analytics_* ids that are really marketing profiles
        for o in self.obs:
            if kind_of(o['rid']) == 'analytics' and (o['fields'].get('event') or '').startswith('contact_'): self.marketing.add(o['rid'])
        for a in self.acts:
            if a['event_type'] == 'DELETE_RECORD' and a['target_system'] == 'analytics_platform': self.marketing.add(a['resource_id'])

    def kind(self, rid):
        return 'marketing' if rid in self.marketing else kind_of(rid)

    def sys(self, rid):
        return 'analytics_platform' if rid in self.marketing else system_of(rid)

    def coverage_at(self, system, audit_at):
        return self.coverage.latest(system, audit_at)

    def linked_rids(self, ids, since='', until='9'):
        rids = set()
        for i in ids:
            for o in self.by_id.get(i, []):
                if since <= o['t'] <= until: rids.add(o['rid'])
        return rids

    def link_evidence(self, ids, rid, since='', until='9'):
        """why does `rid` belong to this identifier set: [(identifier, file_id, time)]"""
        out = []
        for i in ids:
            for o in self.by_id.get(i, []):
                if o['rid'] == rid and since <= o['t'] <= until: out.append((i, o['file_id'], o['t']))
        return sorted(out, key=lambda x: x[2])

    def state_at(self, rid, audit_at):
        return _state_at(self.by_rid.get(rid, []), audit_at)
