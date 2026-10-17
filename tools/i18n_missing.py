"""List Chinese UI string literals in app/static/*.js that have no English translation yet
(neither in i18n_en.js nor in i18n_extra_en.js).  Run:  python tools/i18n_missing.py [--json]
Add the translations to app/static/i18n_extra_en.js."""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CJK = re.compile(r"[一-鿿]")
STATIC = os.path.join(ROOT, "app", "static")


def load_js_object(path, var):
    s = open(path, encoding="utf-8").read()
    i = s.index(var)
    j = s.index("=", i) + 1
    body = s[j:].strip().rstrip(";")
    return json.loads(body) if body.startswith("{") and "'" not in body[:5] else None


def known():
    ex = set()
    gen = load_js_object(os.path.join(STATIC, "i18n_en.js"), "window.MF_I18N_EN")
    ex.update(gen["exact"].keys())
    frag = {f[0].strip() for f in gen["frag"]}
    pats = [re.compile(p[0]) for p in gen["pat"]]
    extra_path = os.path.join(STATIC, "i18n_extra_en.js")
    extra = open(extra_path, encoding="utf-8").read()
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*"', extra):
        ex.add(json.loads('"' + m.group(1) + '"'))
    return ex, frag, pats


def main():
    ex, frag, pats = known()
    out = {}
    for f in sorted(glob.glob(os.path.join(STATIC, "*.js"))):
        if os.path.basename(f).startswith("i18n"):
            continue
        s = open(f, encoding="utf-8").read()
        for m in re.finditer(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"", s):
            t = m.group(1) if m.group(1) is not None else m.group(2)
            if not t or not CJK.search(t):
                continue
            t = t.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")
            k = t.strip()
            if k in ex or k in frag or any(p.match(k) for p in pats):
                continue
            out.setdefault(k, os.path.basename(f))
    if "--json" in sys.argv:
        print(json.dumps(sorted(out), ensure_ascii=False, indent=1))
    else:
        for k, f in sorted(out.items(), key=lambda kv: (kv[1], kv[0])):
            print("%s\t%s" % (f, k))
        print(len(out), "untranslated")


if __name__ == "__main__":
    main()
