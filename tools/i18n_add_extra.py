"""Merge hand-written translations ("<Chinese><TAB><English>" per line in a text file) into
app/static/i18n_extra_en.js.  Prints the keys that are not in the current list of untranslated UI strings (typos).
Run:  python tools/i18n_add_extra.py <translations.txt>"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "app", "static", "i18n_extra_en.js")


def load_extra():
    s = open(PATH, encoding="utf-8").read()
    body = s[s.index("=", s.index("window.MF_I18N_EXTRA")) + 1:].strip().rstrip(";")
    body = re.sub(r"(?m)^(\s*)(exact|pat)\s*:", r'\1"\2":', body)
    body = re.sub(r"([{,])\s*(exact|pat)\s*:", r'\1"\2":', body)
    return json.loads(body)


def main(src):
    extra = load_extra()
    missing = set(json.loads(subprocess.check_output([sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "i18n_missing.py"), "--json"], cwd=ROOT).decode("utf-8")))
    added = unknown = 0
    for line in open(src, encoding="utf-8").read().splitlines():
        if not line.strip() or "\t" not in line:
            continue
        zh, _, en = line.partition("\t")
        zh, en = zh.strip(), en.strip()
        if zh not in missing and zh not in extra["exact"]:
            print("NOT IN MISSING LIST:", zh[:60])
            unknown += 1
        extra["exact"][zh] = en
        added += 1
    head = open(PATH, encoding="utf-8").read().split("window.MF_I18N_EXTRA")[0]
    body = "window.MF_I18N_EXTRA = {\n  exact: {\n" + ",\n".join("    %s: %s" % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False)) for k, v in sorted(extra["exact"].items())) + "\n  },\n  pat: " + json.dumps(extra.get("pat", []), ensure_ascii=False) + "\n};\n"
    open(PATH, "w", encoding="utf-8").write(head + body)
    print("merged", added, "entries;", unknown, "not in the missing list; total", len(extra["exact"]))


if __name__ == "__main__":
    main(sys.argv[1])
