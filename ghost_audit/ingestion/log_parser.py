import re, json
KV = re.compile(r'(?<![\w])([A-Za-z_][\w]*)(?:=|:\s?)("(?:[^"\\]|\\.)*"|[^\s,]+)')
def parse_line(line):
    line=line.rstrip('\n')
    m=re.match(r'(\d{4}-\d\d-\d\dT[\d:]+Z)\s+(.*)',line)
    if not m: return None
    ts,rest=m.groups()
    d={'_ts':ts}
    s=rest.strip()
    if s.startswith('{'):
        try:
            for k,v in json.loads(s).items(): d[k]=str(v) if v is not None else None
            if 'severity' in d: d['level']=d.pop('severity')
            return d
        except Exception: pass
    # cloud runtime: message="..." with escaped quotes
    mm=re.search(r'message="((?:[^"\\]|\\.)*)"',s)
    if mm:
        inner=mm.group(1).replace('\\"','"')
        s=s[:mm.start()]+' '+inner
    for k,v in KV.findall(s):
        if len(v)>1 and v[0]=='"' and v[-1]=='"': v=v[1:-1]
        if v=='null': v=None
        d.setdefault(k,v)
    # pipe / bracket dialects: [LEVEL] [service] [trace] event:
    b=re.match(r'\[(\w+)\] \[(\w+)\] \[([\w-]+)\] (\w+):',s)
    if b: d['level'],d['service'],d['trace_id'],d['event']=b.groups()
    p=[x.strip() for x in re.sub(r'^\|\s*','',s).split(' | ')]
    if len(p)>=5 and p[0] in ('DEBUG','INFO','WARN','ERROR'):
        d['level'],d['service'],d['trace_id'],d['event']=p[0],p[1],p[2],p[3]
    sy=re.match(r'<\d+>1 \S+ (\w+) ([\w-]+) ',s)
    if sy: d['service']=sy.group(1); d['trace_id']=sy.group(2)
    return d
