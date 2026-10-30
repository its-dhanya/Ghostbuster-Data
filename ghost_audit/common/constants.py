"""Paths, identifier patterns, resource-id conventions, configuration."""
import json, os, re

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(CODE)
DS = os.environ.get('GHOST_DATASET_DIR') or os.path.join(ROOT, 'dataset')   # override to audit another export
OUT_DIR = os.environ.get('GHOST_OUTPUT_DIR') or ROOT

EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
REF = re.compile(r'\buser_\d+\b')
HASH = re.compile(r'\b[0-9a-f]{64}\b')

PREFIX_SYSTEM = {
    'account': 'account_service', 'search': 'search_service', 'analytics': 'analytics_platform',
    'support': 'support_platform', 'export': 'export_service', 'data_flow': 'integration_service',
    'backup': 'backup_service', 'audit_record': 'security_service', 'tombstone': 'identity_service',
    'legal_hold': 'legal_service', 'marketing': 'marketing_platform', 'object': 'object_storage',
}

def kind_of(rid):
    m = re.match(r'([a-z_]+?)_\d', rid or '')
    return m.group(1) if m else None

def system_of(rid):
    return PREFIX_SYSTEM.get(kind_of(rid))

def load_config(name):
    return json.load(open(os.path.join(CODE, 'config', name), encoding='utf-8'))

SETTINGS = load_config('settings.json')
_ops = load_config('operation_order.json')['operations']
OP_ORDER = [o['op'] for o in _ops]
OP_STATE = {o['op']: o['state'] for o in _ops}
OP_PHASE = {o['op']: o['phase'] for o in _ops}
PHASE_RANK = {'FINDING': 0, 'REMEDIATION': 1, 'VERIFICATION': 2}
