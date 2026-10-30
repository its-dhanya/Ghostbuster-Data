from .identity_graph import IdentityGraph, load_identities

_GRAPHS = {}
def _graph(users, audit):
    key = (id(users), id(audit))
    if key not in _GRAPHS: _GRAPHS[key] = IdentityGraph(users, audit)
    return _GRAPHS[key]

def resolve(email, users, audit):
    """(user_id, identifiers). user_id is None when the address matches no user (no fuzzy matching)."""
    uid, ids, _ = resolve_explained(email, users, audit)
    return uid, ids

def resolve_explained(email, users, audit):
    g = _graph(users, audit)
    uid, why = g.owner_of_email(email)
    if uid is None: return None, set(), why
    ids, edges = g.identifiers(uid)
    return uid, ids, {'rationale': why, 'edges': edges}
