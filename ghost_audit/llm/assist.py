"""Model-assisted steps. Both are optional, cached, and validated; the deterministic path is the default."""
import json, os, re
from . import client, prompts

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache')
RID = re.compile(r'^(account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|legal_hold|marketing|object)_\d+$')
STATES = {'PRESENT', 'EXPOSED', 'CLEAN', 'ACTIVE', 'INACTIVE'}
VALID_FOR = {   # which states make sense for which resource kind
    'account': {'PRESENT'}, 'search': {'PRESENT'}, 'export': {'PRESENT'}, 'marketing': {'PRESENT'}, 'object': {'PRESENT'},
    'audit_record': {'PRESENT'}, 'legal_hold': {'PRESENT'}, 'support': {'PRESENT', 'EXPOSED', 'CLEAN'},
    'analytics': {'EXPOSED', 'CLEAN', 'PRESENT'}, 'tombstone': {'EXPOSED', 'CLEAN'},
    'data_flow': {'ACTIVE', 'INACTIVE'}, 'backup': {'ACTIVE', 'INACTIVE'}}

HITS = {'intent': 0, 'media': 0}

def _cache_load(name):
    try: return json.load(open(os.path.join(CACHE, name)))
    except Exception: return {}
def _cache_save(name, d):
    os.makedirs(CACHE, exist_ok=True)
    json.dump(d, open(os.path.join(CACHE, name), 'w'), indent=1, sort_keys=True)

def validate_media(obj, source_text=None):
    """Keep only well-formed, internally consistent resources; anything else is 'unresolved'."""
    out = []
    for r in (obj or {}).get('resources', []) if isinstance(obj, dict) else []:
        rid, st = str(r.get('resource_id', '')).strip(), r.get('state')
        m = RID.match(rid)
        if not m or st not in STATES or st not in VALID_FOR[m.group(1)]: continue
        ids = [str(x).strip().lower() for x in r.get('identifiers') or [] if x]
        if source_text is not None:                  # grounding: the id and every identifier must literally occur in the text
            low = source_text.lower()
            if rid.lower() not in low: continue
            ids = [i for i in ids if i in low]
        out.append(dict(rid=rid, state=st, ids=ids, note=str(r.get('evidence') or '')[:120]))
    return out

def extract_media(file_id, path, transport=None):
    cache = _cache_load(f'media_{client.provider()}.json')
    if file_id in cache: return cache[file_id]
    if not (client.enabled() and client.supports_vision()) and not transport: return None
    obj = client.call(prompts.MEDIA_SYSTEM, [client.file_block(path), dict(type='text', text=prompts.MEDIA_USER)],
                      f'media:{file_id}', transport=transport)
    facts = validate_media(obj)
    if transport is None: cache[file_id] = facts; _cache_save(f'media_{client.provider()}.json', cache)
    return facts

def mask_pii(text):
    """Remove direct identifiers before any text leaves the process: intent needs the wording, not the person."""
    t = re.sub(r'[\w.+\-]+@[\w\-]+(\.[\w\-]+)+', '[EMAIL]', text)
    t = re.sub(r'\b[0-9a-f]{64}\b', '[HASH]', t)
    return re.sub(r'\+?\d[\d\s().\-]{6,}\d', '[PHONE]', t)

def classify_intent(text, transport=None):
    """Second opinion on a request text. Returns True/False, or None when unavailable or unresolved."""
    if not client.enabled() and not transport: return None
    cname = f'intent_{client.provider()}_{client.model_name().replace(":", "_")}.json'
    cache = _cache_load(cname); key = str(hash_text(text))
    if key in cache: HITS['intent'] += 1; return cache[key]
    obj = client.call(prompts.INTENT_SYSTEM, [dict(type='text', text=prompts.INTENT_USER.format(text=mask_pii(text)))],
                      'intent', max_tokens=120, transport=transport)
    v = obj.get('deletion_requested') if isinstance(obj, dict) else None
    v = v if isinstance(v, bool) else None
    if transport is None and v is not None: cache[key] = v; _cache_save(cname, cache)
    return v

def hash_text(t):
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def extract_media_text(file_id, text, transport=None):
    """Model reads the text of an artifact (tesseract / PDF text layer) and proposes resources; grounded and validated."""
    cname = f'mediatext_{client.provider()}_{client.model_name().replace(":", "_")}.json'
    cache = _cache_load(cname)
    key = f'{file_id}:{hash_text(text)}'
    if key in cache: HITS['media'] += 1; return cache[key]
    if not text.strip() or (not client.enabled() and not transport): return None
    obj = client.call(prompts.MEDIA_TEXT_SYSTEM, [dict(type='text', text=prompts.MEDIA_TEXT_USER.format(text=text[:6000]))],
                      f'mediatext:{file_id}', max_tokens=900, transport=transport)
    facts = validate_media(obj, text)
    if transport is None and obj is not None: cache[key] = facts; _cache_save(cname, cache)
    return facts
