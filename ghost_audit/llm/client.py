"""Minimal model client (stdlib only) with usage tracking. Two providers:

  anthropic  needs ANTHROPIC_API_KEY (optional ANTHROPIC_BASE_URL, LLM_MODEL default claude-sonnet-5-5); text + vision/PDF
  ollama     local, no key: LLM_PROVIDER=ollama (optional OLLAMA_HOST default http://localhost:11434, LLM_MODEL default
             llama3:latest); text only - blocks that need vision are reported as unsupported and skipped

Provider choice: LLM_PROVIDER if set, else anthropic when a key exists, else none. Every call, including retries, is
recorded in USAGE with the provider-reported token counts. LLM_PRICE_IN / LLM_PRICE_OUT (USD per million tokens);
unset -> cost reported as unpriced (local models are free).
"""
import base64, json, os, time, urllib.request, urllib.error

DEFAULT_MODEL = 'claude-sonnet-5-5'

class Usage:
    def __init__(self): self.calls = []
    def record(self, provider, model, inp, out, ok, label):
        self.calls.append(dict(provider=provider, model=model, input_tokens=inp, output_tokens=out, ok=ok, label=label))
    def summary(self):
        per = {}
        for c in self.calls:
            m = per.setdefault((c['provider'], c['model']), dict(calls=0, failed=0, input_tokens=0, output_tokens=0))
            m['calls'] += 1; m['failed'] += (not c['ok']); m['input_tokens'] += c['input_tokens']; m['output_tokens'] += c['output_tokens']
        return per

USAGE = Usage()

_PROBE = {}
def ollama_up():
    """Is a local Ollama reachable? (1.5 s probe, cached for the process)"""
    if 'up' not in _PROBE:
        host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
        try: urllib.request.urlopen(host + '/api/tags', timeout=1.5).read(); _PROBE['up'] = True
        except Exception: _PROBE['up'] = False
    return _PROBE['up']

def provider():
    """LLM_PROVIDER=anthropic|ollama|none forces a choice; otherwise an API key wins, then a reachable local Ollama."""
    p = os.environ.get('LLM_PROVIDER', '').lower()
    if p in ('anthropic', 'ollama'): return p
    if p == 'none': return None
    if os.environ.get('ANTHROPIC_API_KEY'): return 'anthropic'
    return 'ollama' if ollama_up() else None

def enabled(): return provider() is not None

def model_name():
    default = 'llama3:latest' if provider() == 'ollama' else DEFAULT_MODEL
    return os.environ.get('LLM_MODEL', default)

def supports_vision(): return provider() == 'anthropic'

def _post(body, transport=None):
    if transport: return transport(body)
    base = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com').rstrip('/')
    req = urllib.request.Request(base + '/v1/messages', data=json.dumps(body).encode(), method='POST', headers={
        'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())

def _ollama(system, content, max_tokens, transport=None):
    text = '\n'.join(b.get('text', '') for b in content if b.get('type') == 'text')
    body = dict(model=os.environ.get('LLM_MODEL', 'llama3:latest'), stream=False, format='json',
                options=dict(temperature=0, num_predict=max_tokens),
                messages=[dict(role='system', content=system), dict(role='user', content=text)])
    if transport: resp = transport(body)
    else:
        host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
        req = urllib.request.Request(host + '/api/chat', data=json.dumps(body).encode(), method='POST', headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as r: resp = json.loads(r.read())
    return body['model'], resp['message']['content'], resp.get('prompt_eval_count', 0), resp.get('eval_count', 0)

def call(system, content, label, max_tokens=1200, transport=None, retries=2):
    """content: list of Messages API content blocks. Returns parsed JSON object or None (unresolved)."""
    if provider() == 'ollama' and not transport:
        if any(b.get('type') != 'text' for b in content): return None          # no vision model locally: unresolved
        for attempt in range(retries + 1):
            try:
                model, text, i, o = _ollama(system, content, max_tokens)
                USAGE.record('ollama', model, i, o, True, label); return parse_json(text)
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
                USAGE.record('ollama', os.environ.get('LLM_MODEL', 'llama3:latest'), 0, 0, False, label)
        return None
    model = model_name()
    body = dict(model=model, max_tokens=max_tokens, temperature=0, system=system, messages=[dict(role='user', content=content)])
    for attempt in range(retries + 1):
        try:
            resp = _post(body, transport)
            u = resp.get('usage', {})
            USAGE.record('anthropic', model, u.get('input_tokens', 0), u.get('output_tokens', 0), True, label)
            text = ''.join(b.get('text', '') for b in resp.get('content', []) if b.get('type') == 'text')
            return parse_json(text)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
            USAGE.record('anthropic', model, 0, 0, False, label)
            time.sleep(min(2 ** attempt, 8) if not transport else 0)
    return None

def parse_json(text):
    s = text.strip()
    a, b = s.find('{'), s.rfind('}')
    if a < 0 or b < a: raise ValueError('no json object')
    return json.loads(s[a:b + 1])

def file_block(path):
    ext = path.rsplit('.', 1)[-1].lower()
    data = base64.b64encode(open(path, 'rb').read()).decode()
    if ext == 'pdf': return dict(type='document', source=dict(type='base64', media_type='application/pdf', data=data))
    return dict(type='image', source=dict(type='base64', media_type='image/png', data=data))
