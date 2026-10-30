"""Turn raw observations into canonical resource states.

PRESENT / ABSENT           - record exists or not
EXPOSED / CLEAN            - record exists but still holds (or no longer holds) direct identifiers
ACTIVE / INACTIVE          - data flow running, backup restorable
"""
from common.constants import kind_of

def truthy(v):
    return str(v).strip().lower() in ('true', '1', 'yes', 'enabled', 'allow', 'allowed')

DIRECT = ('email', 'phone', 'email_hash', 'name', 'full_name', 'user_id', 'customer_reference', 'requester_email',
          'requester_name', 'requester_phone', 'owner_email', 'owner_phone')

def direct_ids_present(f, keys=DIRECT):
    return any(f.get(k) not in (None, '', 'null') for k in keys)

LEDGER = {'FOUND': 'PRESENT', 'NOT_FOUND': 'ABSENT', 'IDENTIFIABLE': 'EXPOSED', 'ANONYMIZED': 'CLEAN',
          'REDACTED': 'CLEAN', 'ACTIVE': 'ACTIVE', 'DISABLED': 'INACTIVE', 'BLOCKED': 'INACTIVE'}

def is_attachment(o):
    f = o['fields']
    return (o.get('media_state') == 'PRESENT' and kind_of(o['rid']) == 'support' or f.get('_coll') in ('ticket_attachments', 'attachment_pii_scan', 'attachment_scan', 'contact_query_completed', 'deletion_marker_check') or
            f.get('record_type') == 'SUPPORT_ATTACHMENT' or 'file' in f and kind_of(o['rid']) == 'support' or
            'file_name' in f and kind_of(o['rid']) == 'support')

def state_of(o):
    if o.get('media_state'): return o['media_state']
    if o['role'] == 'link': return None
    k = kind_of(o['rid']); f = o['fields']; coll = f.get('_coll'); role = o['role']
    if 'result' in f and f.get('record_type') and f['result'] in LEDGER:      # ledger / handover / history shape
        return LEDGER[f['result']]
    ev = f.get('event') or coll or ''
    if k == 'account':
        if 'status_code' in f: return 'PRESENT' if int(f['status_code']) == 200 else 'ABSENT'
        if 'http_status' in f: return 'PRESENT' if str(f['http_status']) == '200' else 'ABSENT'
        if 'rows' in f: return 'PRESENT' if str(f['rows']) not in ('0', '') else 'ABSENT'
        if coll == 'profile_lookups': return 'PRESENT'
        return 'PRESENT'
    if k == 'search':
        if '_hit' in f: return 'PRESENT' if f['_hit'] else 'ABSENT'
        if 'result' in f: return 'PRESENT' if f['result'] in ('hit', 'FOUND') else 'ABSENT'
        return 'PRESENT'
    if k == 'export':
        for key in ('available', 'download_available'):
            if key in f: return 'PRESENT' if truthy(f[key]) else 'ABSENT'
        return 'PRESENT'
    if k == 'support':
        if is_attachment(o): return 'PRESENT'
        if 'message_text' in f:
            return 'CLEAN' if '[REDACTED]' in (f['message_text'] or '') else 'EXPOSED'
        if ev == 'message_pii_scan': return 'EXPOSED'
        if ev == 'contact_query_completed': return 'PRESENT' if str(f.get('rows')) != '0' else 'ABSENT'
        if ev == 'deletion_marker_check': return 'ABSENT' if truthy(f.get('marker_found')) else 'PRESENT'
        if 'requester_email' in f or 'requester_name' in f or 'requester_phone' in f:
            return 'EXPOSED' if direct_ids_present(f, ('requester_email', 'requester_name', 'requester_phone')) else 'CLEAN'
        if 'message_excerpt' in f: return 'CLEAN'
        return None
    if k == 'analytics':
        if ev in ('contact_lookup_completed', 'contact_query_completed'):
            return 'PRESENT' if str(f.get('rows')) != '0' else 'ABSENT'
        if 'direct_identifiers' in f:
            return 'EXPOSED' if str(f['direct_identifiers']) not in ('0', '') else 'CLEAN'
        if ev == 'analytics_identity_scan': return 'EXPOSED'
        return 'EXPOSED' if direct_ids_present(f, ('email', 'phone', 'email_hash', 'user_id', 'customer_reference')) else 'CLEAN'
    if k == 'data_flow':
        if 'enabled' in f: return 'ACTIVE' if truthy(f['enabled']) else 'INACTIVE'
        return None
    if k == 'backup':
        if 'restore_allowed' in f: return 'ACTIVE' if truthy(f['restore_allowed']) else 'INACTIVE'
        if 'eligible' in f: return 'ACTIVE' if truthy(f['eligible']) else 'INACTIVE'
        if 'decision' in f: return 'ACTIVE' if truthy(f['decision']) else 'INACTIVE'
        return None
    if k == 'tombstone':
        return 'EXPOSED' if direct_ids_present(f, ('name', 'email', 'phone', 'email_hash')) else 'CLEAN'
    if k in ('audit_record', 'legal_hold'):
        return 'PRESENT'
    return 'PRESENT'
