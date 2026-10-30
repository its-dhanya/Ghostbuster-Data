"""Is deletion actually requested? Rules decide (multilingual); the optional model gives a second opinion that may only
turn a 'deletion' verdict into 'non-deletion' when the text contains no deletion wording at all."""
import re

POS = re.compile(r"delet|erase|erasure|remov|clos(e|ing)|eliminat|elimina|borr(ar|e)|cerrar|cierre|suppr|effac|ferm(er|eture)|"
                 r"l(ö|oe)sch|entfern|schlie(ß|ss)en|exclus|exclu|apag|encerr|remo(ç|c)|삭제|탈퇴|해지|削除|消去|退会|解約|删除|刪除|注销|销户|"
                 r"cancel (my|the) account|wipe|forget me|permanent|deactivat", re.I)
NEG = re.compile(r"not asking for (deletion|erasure)|do not (close|delete)|don'?t (delete|close)|leave (the|my) (account|profile)|keep the account|"
                 r"still (use|need|want)|information request|not a request to (erase|delete)|without removing|stop the promotional|"
                 r"marketing lists only|continue using the service|replace it with the new one|download my account|"
                 r"copy of (last year|the information)|correct it|"
                 r"no (es|son) (una )?solicitud de (eliminaci|borrado)|sin (eliminar|borrar|cerrar)|no (cierren|eliminen|borren)|"
                 r"ne (pas )?(supprim|ferm)|sans (supprimer|fermer)|nicht (l(ö|oe)schen|schlie(ß|ss)en)|"
                 r"n(ã|a)o (exclu|apag|encerr)|삭제하지 마|削除しないで|不要删除|请勿删除", re.I)
OTHER = re.compile(r"\b(update|change|correct|replace|copy|download|portable|reset|access request|opt[- ]?out|unsubscribe|promotional|"
                   r"actualizar|corregir|modifier|corriger|aktualisieren|atualizar|corrigir|변경|수정|変更|修正|更新|修改)\b|information (held|you hold)", re.I)

NOTES = []
USE_LLM = False

def rule_intent(text):
    """Deletion unless the text asks for something else: explicit retention/negation, or no deletion wording at all
    combined with another request type (update, copy, access, opt-out ...)."""
    if NEG.search(text): return False
    return bool(POS.search(text)) or not OTHER.search(text)

def wants_deletion(text):
    r = rule_intent(text)
    if USE_LLM:
        from llm import assist
        v = assist.classify_intent(text)
        if v is not None and v != r:
            if r and not v and not POS.search(text):
                NOTES.append('model overrides rules to non-deletion: ' + text[:80]); return False
            NOTES.append(f'model disagrees (model={v}, rules={r}), rules kept: ' + text[:80])
    return r
