"""Policy engine driven by deletion_rules.csv.

Each evidence resource kind maps to a data category; the category's required_action (DELETE / REDACT / ANONYMIZE /
RETAIN) decides the violating state, the finding, the remediation and the verification. Nothing here hardcodes which
data is deleted: changing a rule in the CSV changes the plan. Two operational objects are not data categories:
an active data flow (recreation risk -> disable) and a retained backup archive whose restore access can be blocked
(rule_14 RETAIN -> keep the archive, block the restore)."""
import csv, os
from collections import namedtuple
from common.constants import DS

Treatment = namedtuple('Treatment', 'category rule_id action violating finding remediation verification')

CATEGORY = {
    'account': 'USER_PROFILE', 'search': 'SEARCH_INDEX_ENTRY', 'export': 'USER_EXPORT', 'marketing': 'MARKETING_PROFILE',
    'object': 'SUPPORT_ATTACHMENT', 'analytics': 'ANALYTICS_PROFILE', 'tombstone': 'ACCOUNT_TOMBSTONE',
    'audit_record': 'SECURITY_AUDIT_LOG', 'legal_hold': 'LEGAL_HOLD_RECORD', 'backup': 'BACKUP_ARCHIVE',
}
BY_ACTION = {   # action -> (violating state, finding op, remediation op, verification op)
    'DELETE': ('PRESENT', 'REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT'),
    'REDACT': ('EXPOSED', 'REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'),
    'ANONYMIZE': ('EXPOSED', 'REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD', 'VERIFY_RECORD_ANONYMIZED'),
    'RETAIN': (None, None, None, 'VERIFY_RECORD_PRESENT'),
}
DEFAULT_RULES = {'USER_PROFILE': 'DELETE', 'SECONDARY_IDENTIFIER': 'DELETE', 'SEARCH_INDEX_ENTRY': 'DELETE', 'CACHE_ENTRY': 'DELETE',
                 'SUPPORT_MESSAGE': 'REDACT', 'SUPPORT_ATTACHMENT': 'DELETE', 'ANALYTICS_PROFILE': 'ANONYMIZE', 'PRODUCT_TELEMETRY': 'ANONYMIZE',
                 'USER_EXPORT': 'DELETE', 'MARKETING_PROFILE': 'DELETE', 'EMAIL_DELIVERY_LOG': 'REDACT', 'SECURITY_AUDIT_LOG': 'RETAIN',
                 'LEGAL_HOLD_RECORD': 'RETAIN', 'BACKUP_ARCHIVE': 'RETAIN', 'ACCOUNT_TOMBSTONE': 'REDACT'}

WARNINGS = []

class RuleEngine:
    def __init__(self, path=None):
        path = path or os.path.join(DS, 'deletion_rules.csv')
        self.rules = {}
        try:
            for r in csv.DictReader(open(path, encoding='utf-8')):
                self.rules[r['data_category']] = (r['rule_id'], r['required_action'].strip().upper(), r['condition'])
        except OSError:
            pass
        for cat, act in DEFAULT_RULES.items(): self.rules.setdefault(cat, ('builtin', act, ''))

    def treatment(self, kind, attachment=False):
        if kind == 'data_flow':
            return Treatment('DATA_FLOW', None, 'DISABLE', 'ACTIVE', 'REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW', 'VERIFY_DATA_FLOW_DISABLED')
        if kind == 'support': cat = 'SUPPORT_ATTACHMENT' if attachment else 'SUPPORT_MESSAGE'
        else: cat = CATEGORY.get(kind)
        if cat is None: return None
        rule_id, action, _ = self.rules[cat]
        if cat == 'BACKUP_ARCHIVE' and action == 'RETAIN':   # retained archive: the obligation is that restore is blocked
            return Treatment(cat, rule_id, 'BLOCK_RESTORE', 'ACTIVE', 'REPORT_RESTORE_RISK', 'BLOCK_RESTORE', 'VERIFY_RESTORE_BLOCKED')
        if action not in BY_ACTION:                        # unknown action in the rules file: never destroy data on a guess
            WARNINGS.append(f'{cat}: unknown required_action {action!r}, treated as RETAIN'); action = 'RETAIN'
        v, f, r, ver = BY_ACTION[action]
        return Treatment(cat, rule_id, action, v, f, r, ver)

ENGINE = RuleEngine()
def treatment(kind, attachment=False): return ENGINE.treatment(kind, attachment)
