"""Identity graph: users, emails, phones and hashes as nodes; typed edges that carry their source and validity.

Edges (kind): HAS_EMAIL (current), PREVIOUSLY_USED (email / phone / hash value replaced by an audit event),
HAS_PHONE, HAS_HASH.  Every edge keeps `source` (users.csv row or audit_id), `valid_from`, `valid_to` and a
`confidence` (CONFIRMED = stable user_id snapshot, CORROBORATED = audit-log history). Users are never merged by
name or by fuzzy similarity: a value maps to a user only through an exact edge.
"""
import re
from collections import defaultdict

def _digits(v): return re.sub(r'\D', '', v or '')

class IdentityGraph:
    def __init__(self, users, audit):
        self.users = users
        self.edges = []                                   # dicts: user, kind, field, value, source, valid_from, valid_to, confidence
        self.by_value = defaultdict(list)
        for uid, r in users.items():
            self._edge(uid, 'HAS_EMAIL', 'email', r['email'].lower(), f'user_identities:{uid}', r['updated_at'], None, 'CONFIRMED')
            self._edge(uid, 'HAS_HASH', 'email_hash', r['email_hash'], f'user_identities:{uid}', r['updated_at'], None, 'CONFIRMED')
            self._edge(uid, 'HAS_PHONE', 'phone', _digits(r['phone']), f'user_identities:{uid}', r['updated_at'], None, 'CONFIRMED')
        for a in audit:
            f, old, new = a['field_name'], a['old_value'], a['new_value']
            if f == 'email':
                self._edge(a['user_id'], 'PREVIOUSLY_USED', 'email', old.lower(), a['audit_id'], None, a['event_time'], 'CORROBORATED')
                self._edge(a['user_id'], 'PREVIOUSLY_USED', 'email', new.lower(), a['audit_id'], a['event_time'], None, 'CORROBORATED')
            elif f == 'phone':
                self._edge(a['user_id'], 'PREVIOUSLY_USED', 'phone', _digits(old), a['audit_id'], None, a['event_time'], 'CORROBORATED')
            elif f == 'email_hash':
                self._edge(a['user_id'], 'PREVIOUSLY_USED', 'email_hash', old, a['audit_id'], None, a['event_time'], 'CORROBORATED')

    def _edge(self, user, kind, field, value, source, vfrom, vto, conf):
        if not value: return
        e = dict(user=user, kind=kind, field=field, value=value, source=source, valid_from=vfrom, valid_to=vto, confidence=conf)
        self.edges.append(e); self.by_value[(field, value)].append(e)

    def owner_of_email(self, email):
        """(user_id, rationale): current holder first; otherwise the most recent holder of a replaced address."""
        e = email.strip().lower()
        cur = [x for x in self.by_value.get(('email', e), []) if x['kind'] == 'HAS_EMAIL']
        if cur: return cur[0]['user'], f'current email of {cur[0]["user"]} ({cur[0]["source"]})'
        old = [x for x in self.by_value.get(('email', e), []) if x['kind'] == 'PREVIOUSLY_USED' and x['valid_to']]
        if old:
            x = sorted(old, key=lambda x: x['valid_to'])[-1]
            return x['user'], f'previously used by {x["user"]} until {x["valid_to"]} ({x["source"]})'
        return None, 'no matching identifier'

    def identifiers(self, uid):
        """Every identifier ever attached to the user, with the edges that justify each one."""
        ids = {uid}; why = {uid: ['stable user_id']}
        for x in self.edges:
            if x['user'] != uid: continue
            ids.add(x['value']); why.setdefault(x['value'], []).append(f'{x["kind"]} {x["field"]} <- {x["source"]}')
        return ids, why

def load_identities():
    import csv, os
    from common.constants import DS
    users = {r['user_id']: r for r in csv.DictReader(open(os.path.join(DS, 'user_identities.csv'), encoding='utf-8'))}
    audit = list(csv.DictReader(open(os.path.join(DS, 'user_audit_log.csv'), encoding='utf-8')))
    return users, audit
