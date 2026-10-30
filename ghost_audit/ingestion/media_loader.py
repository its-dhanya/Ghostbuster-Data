"""PNG / PDF evidence. Facts come from (1) the human-verified transcription in media_facts.json, (2) optionally a
vision model (--use-llm), (3) a degraded tesseract fallback for unseen PNGs."""
import json, os, re
from common.constants import DS, CODE, EMAIL, REF, kind_of
from .normalizer import mk

def pdf_text(path):
    """Text of a PDF whose pages are plain content streams (ASCII85 and/or Flate, literal-string Tj/TJ). No third-party
    library; CID-encoded or scanned PDFs yield '' and fall through to the model path."""
    import base64, zlib
    try: b = open(path, 'rb').read()
    except OSError: return ''
    out = []
    for m in re.finditer(rb'<<([^>]*?)>>\s*stream\r?\n(.*?)endstream', b, re.S):
        hdr, body = m.group(1), m.group(2)
        try:
            if b'ASCII85Decode' in hdr:
                t = body.strip()
                if t.startswith(b'<~'): t = t[2:]
                if t.endswith(b'~>'): t = t[:-2]
                body = base64.a85decode(t)
            if b'FlateDecode' in hdr: body = zlib.decompress(body)
        except Exception: continue
        if b'BT' not in body: continue
        for seg in re.finditer(rb'BT(.*?)ET', body, re.S):
            line = ''
            for lit, arr in re.findall(rb'\(((?:[^()\\]|\\.)*)\)\s*Tj|\[(.*?)\]\s*TJ', seg.group(1), re.S):
                parts = [lit] if lit else re.findall(rb'\(((?:[^()\\]|\\.)*)\)', arr)
                line += ''.join(re.sub(rb'\\(.)', rb'\1', p).decode('latin1') for p in parts)
            if line.strip(): out.append(line.strip())
    return '\n'.join(out)

def facts_from_text(txt):
    ids = sorted({e.lower() for e in EMAIL.findall(txt)} | set(REF.findall(txt)))
    out = []
    for rid in sorted(set(re.findall(r'\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|marketing|object)_\d+\b', txt))):
        k = kind_of(rid)
        if k == 'data_flow': st = 'ACTIVE' if re.search(r'healthy|continuous|enabled', txt, re.I) else 'INACTIVE'
        elif k == 'backup': st = 'INACTIVE' if re.search(r'blocked|restore (denied|disabled)', txt, re.I) else 'ACTIVE'
        elif k in ('analytics', 'support', 'tombstone'): st = 'EXPOSED' if EMAIL.search(txt) else 'CLEAN'
        else: st = 'PRESENT'
        if k == 'support' and re.search(r'attachment|\.pdf|\.jpg|checksum', txt, re.I): st = 'PRESENT'     # an attachment object, not a message
        out.append(dict(rid=rid, state=st, ids=ids, note='text fallback'))
    return out

def source_text(path):
    """Machine-readable text of an artifact: PDF text layer, or tesseract for a PNG ('' when neither is possible)."""
    import shutil, subprocess
    low = path.lower()
    if low.endswith('.pdf'): return pdf_text(path)
    if not low.endswith('.png') or not shutil.which('tesseract'): return ''
    try: return subprocess.run(['tesseract', path, '-', '--psm', '4'], capture_output=True, text=True, timeout=60).stdout
    except Exception: return ''

def ocr_facts(path):
    """Degraded path for a file with no transcription and no model: rules over the extracted text."""
    return facts_from_text(source_text(path))

NO_TRANSCRIPTION = os.environ.get('GHOST_NO_TRANSCRIPTION') == '1'   # evaluate the AI/OCR pipeline without the human transcription
MEDIA_STATS = {'files': 0, 'transcribed': 0, 'ai_agree': 0, 'ai_conflict': 0, 'ai_novel_noted': 0, 'ai_applied': 0}

def _merge_ai(fid, text, verified):
    """Resolve transcription / text rules / model into the facts used by the audit.

    * A file with a human transcription is authoritative; the model and the rules only vote, and agreements,
      conflicts and novel resources are logged (never applied, so a hallucinated or decoy resource cannot reach a case).
    * A file without one (an unseen artifact, or GHOST_NO_TRANSCRIPTION=1) is read by the AI pipeline: a resource is
      accepted when its id is grounded in the text and the rules and the model agree on it (model alone if there is
      no other signal); state comes from the model when valid, else from the rules; identifiers come from the model
      only when grounded, or from the page when it names exactly one resource."""
    from llm import assist
    det = {f['rid']: f for f in facts_from_text(text)}
    model = {g['rid']: g for g in (assist.extract_media_text(fid, text) or [])} if USE_LLM else {}
    known = {f['rid']: f for f in verified}
    MEDIA_STATS['files'] += 1; MEDIA_STATS['transcribed'] += bool(verified)
    if verified:
        for rid, f in known.items():
            g = model.get(rid)
            if g is None: continue
            if g['state'] == f['state']: MEDIA_STATS['ai_agree'] += 1
            else:
                MEDIA_STATS['ai_conflict'] += 1
                MEDIA_NOTES.append(f"{fid}: {rid} transcription={f['state']} model={g['state']} - transcription kept")
        for rid in model:
            if rid not in known: MEDIA_STATS['ai_novel_noted'] += 1
        novel = sorted(r for r in model if r not in known)
        if novel: MEDIA_NOTES.append(f"{fid}: model also listed {', '.join(novel)} (not applied: file has a verified transcription)")
        return list(verified)
    out = []
    page_rids = sorted(det)
    for rid in sorted(set(det) | set(model)):
        g, d = model.get(rid), det.get(rid)
        if d is None and g is None: continue
        if d is None and not g: continue
        if d is not None and USE_LLM and model and g is None: continue          # rules saw it, model did not: not corroborated
        state = g['state'] if g else d['state']
        ids = list(g['ids']) if g and g['ids'] else (d['ids'] if len(page_rids) == 1 and d else [])
        out.append(dict(rid=rid, state=state, ids=ids, note='ai pipeline' if g else 'text rules'))
        MEDIA_STATS['ai_applied'] += 1
    return out

MEDIA_NOTES = []   # model-vs-transcription cross-check notes (filled only when the model-assisted path runs)
USE_LLM = False

def load_media(fid, meta):
    verified = [] if NO_TRANSCRIPTION else list(json.load(open(os.path.join(CODE, 'media_facts.json'))).get(fid, []))
    path = os.path.join(DS, meta['file_path'])
    text = source_text(path) if (USE_LLM or not verified) else ''
    facts = _merge_ai(fid, text, verified) if (USE_LLM or not verified) else verified
    out = []
    for f in facts:
        o = mk(fid, meta['captured_at'], f['rid'], {'_coll': 'media', 'note': f['note']}, 'media', None, f.get('ids', []))
        o['media_state'] = f['state']
        out.append(o)
    return out
