"""Compare the human transcription (media_facts.json) with what the offline fallbacks recover from the files
themselves (PDF text layer, tesseract for PNG). Agreement is evidence that the transcription is not just my reading.
  python3 ghost_audit/evaluation/media_crosscheck.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import csv
from common.constants import DS, CODE
from ingestion.media_loader import ocr_facts

facts = json.load(open(os.path.join(CODE, 'media_facts.json')))
tot = agree = 0
for r in csv.DictReader(open(os.path.join(DS, 'evidence_files.csv'), encoding='utf-8')):
    if not r['file_path'].lower().endswith(('.png', '.pdf')): continue
    mine = {f['rid']: f['state'] for f in facts.get(r['file_id'], [])}
    auto = {f['rid']: f['state'] for f in ocr_facts(os.path.join(DS, r['file_path']))}
    both = set(mine) & set(auto)
    ok = {k for k in both if mine[k] == auto[k]}
    tot += len(mine); agree += len(ok)
    print(f"{r['file_id']:<12} transcribed {sorted(mine)}  offline-recovered {sorted(auto)}  state-agree {sorted(ok)}")
print(f'resources recovered offline with the same state: {agree}/{tot}')
