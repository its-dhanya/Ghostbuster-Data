"""Negative evidence: "not found" only proves absence when the system was actually inspected.

CONFIRMED   an explicit negative observation (404, NOT_FOUND, miss, row count 0) of that very resource;
COVERED     no observation of the resource, but a snapshot that inspected the owning system exists at or before the
            cutoff (bundle section, snapshot_scope row, account table), so absence is supported by omission;
UNRESOLVED  neither - the audit can only assume absence from the deletion activity (a claim)."""
from collections import defaultdict

class CoverageTracker:
    def __init__(self, entries, file_times):
        self.cover = defaultdict(list)
        for system, fid, t in entries:
            if fid in file_times: self.cover[system].append((t, file_times[fid], fid))

    def latest(self, system, audit_at):
        c = [x for x in self.cover.get(system, []) if x[0] <= audit_at and x[1] <= audit_at]
        return max(c)[2] if c else ''

    def absence(self, system, audit_at, explicit_negative):
        if explicit_negative: return 'CONFIRMED', explicit_negative['file_id']
        f = self.latest(system, audit_at)
        return ('COVERED', f) if f else ('UNRESOLVED', '')
