"""Chinese -> English translation of generated documents (the same dictionaries as the English user interface, plus
app/doc_en.json for the fixed text of the document generator).

translate(text): exact match, then %s/%d patterns, then fragments (only when at least 80 % of the Chinese characters are
covered - so that user-written content such as a method name is never half-translated).
localize(doc): translates every run of a python-docx Document (body, tables, headers, footers).  Content written by the
users and template body text without a dictionary entry stays as it is."""
import json
import os
import re

CJK = re.compile(r"[一-鿿]")
_HERE = os.path.dirname(os.path.abspath(__file__))
_state = {}


def _load_js_object(path, var):
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    i = s.index(var)
    j = s.index("=", i) + 1
    body = s[j:].strip().rstrip(";")
    body = re.sub(r"(?m)^(\s*)(exact|pat)\s*:", r'\1"\2":', body)
    body = re.sub(r"([{,])\s*(exact|pat)\s*:", r'\1"\2":', body)
    return json.loads(body)


def _tables():
    if _state:
        return _state
    exact, pats, frag = {}, [], {}
    gen = _load_js_object(os.path.join(_HERE, "static", "i18n_en.js"), "window.MF_I18N_EN")
    exact.update(gen.get("exact", {}))
    pats.extend(gen.get("pat", []))
    for k, v in gen.get("frag", []):
        frag[k] = v
    try:
        exact.update(_load_js_object(os.path.join(_HERE, "static", "i18n_tpl_en.js"), "window.MF_I18N_TPL").get("exact", {}))
    except Exception:
        pass
    try:
        extra = _load_js_object(os.path.join(_HERE, "static", "i18n_extra_en.js"), "window.MF_I18N_EXTRA")
        exact.update(extra.get("exact", {}))
        pats = extra.get("pat", []) + pats
    except Exception:
        pass
    doc_path = os.path.join(_HERE, "doc_en.json")
    if os.path.exists(doc_path):
        with open(doc_path, encoding="utf-8") as fh:
            d = json.load(fh)
        exact.update(d.get("exact", {}))
        pats = d.get("pat", []) + pats
        for k, v in d.get("frag", []):
            frag[k] = v
    for k, v in exact.items():
        if len(k) >= 2 and CJK.search(k) and k not in frag:
            frag[k] = v
    keys = sorted(frag, key=lambda x: -len(x))
    _state.update(exact=exact, pats=[(re.compile(p[0]), p[1]) for p in pats],
                  frag=frag, frag_re=re.compile("|".join(re.escape(k) for k in keys)) if keys else None)
    return _state


def translate(s):
    if not s or not CJK.search(s):
        return s
    t = _tables()
    core = s.strip()
    if not core:
        return s
    lead, trail = s[:len(s) - len(s.lstrip())], s[len(s.rstrip()):]
    if core in t["exact"]:
        return lead + t["exact"][core] + trail
    for rx, rep in t["pats"]:
        m = rx.match(core)
        if m:
            return lead + re.sub(r"\$(\d)", lambda mm: translate(m.group(int(mm.group(1))) or ""), rep) + trail
    if not t["frag_re"]:
        return s
    res = t["frag_re"].sub(lambda m: t["frag"][m.group(0)], s)
    before, after = len(CJK.findall(s)), len(CJK.findall(res))
    return s if (before - after) < before * 0.8 else res


def _paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    for tb in doc.tables:
        yield from _table_paragraphs(tb)
    for sec in doc.sections:
        for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
            try:
                for p in part.paragraphs:
                    yield p
                for tb in part.tables:
                    yield from _table_paragraphs(tb)
            except Exception:
                continue


def _table_paragraphs(tb):
    for row in tb.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                yield p
            for inner in cell.tables:
                yield from _table_paragraphs(inner)


def localize(doc):
    """Translate all runs in place; returns the number of runs changed."""
    n = 0
    for p in _paragraphs(doc):         # (merged cells appear several times: translating twice is harmless)
        for r in p.runs:
            if r.text and CJK.search(r.text):
                t = translate(r.text)
                if t != r.text:
                    r.text = t
                    n += 1
    return n
