"""Evidence ingestion: every evidence file is parsed once into observations."""
import csv, os
from common.constants import DS
from common.timeutil import norm_ts
from . import media_loader
from .json_loader import load_json
from .sqlite_loader import load_sql
from .text_loader import load_txt, load_links
from .log_loader import load_log
from .media_loader import load_media
from .normalizer import COVERAGE

def set_use_llm(flag): media_loader.USE_LLM = flag
def media_notes(): return media_loader.MEDIA_NOTES

def load_all():
    files = list(csv.DictReader(open(os.path.join(DS, 'evidence_files.csv'), encoding='utf-8')))
    obs = []; meta = {}
    for r in files:
        p = os.path.join(DS, r['file_path']); ext = p.rsplit('.', 1)[-1].lower()
        r['captured_at'] = norm_ts(r['captured_at']); meta[r['file_id']] = r
        try:
            if ext == 'json': o = load_json(r['file_id'], p)
            elif ext == 'sql': o = load_sql(r['file_id'], p)
            elif ext == 'txt': o = load_txt(r['file_id'], p)
            elif ext == 'log': o = load_log(r['file_id'], p)
            elif ext in ('png', 'pdf'): o = load_media(r['file_id'], r)
            else: o = []
        except Exception as e:                       # one unreadable file must not stop the audit
            print('warning: could not ingest', r['file_id'], repr(e)); o = []
        for x in o:
            x['file_t'] = r['captured_at']; x['t'] = norm_ts(x['t']) or r['captured_at']
        obs += o
    return obs, meta
