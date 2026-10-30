"""Temporal state reconstruction: the state of a resource at the audit cutoff.

Only observations whose file was captured AND whose own timestamp are at or before `audit_at` count; later evidence
(a record that reappears after the audit) never changes the answer. The latest supported observation wins, and when
two observations share a timestamp the violating one wins, so a drifted replica is not hidden by a clean primary.
Reported results (workflow status, activity result) are claims: they are never used as state."""

BAD_STATES = ('PRESENT', 'EXPOSED', 'ACTIVE')      # existence / exposure / recreation risk

def state_at(observations, audit_at):
    best = None
    for o in observations:
        if o['state'] is None: continue
        if o['file_t'] > audit_at or o['t'] > audit_at: continue
        key = (o['t'], o['file_t'], o['state'] in BAD_STATES)
        if best is None or key >= best[0]: best = (key, o)
    return best[1] if best else None
