"""Content-integrity tests for the method templates (V1.1).  They do not need a database.
Run:  python -m unittest tests.test_templates   (or discover -s tests)"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import kb_seed, templates_data as T  # noqa: E402

STAGES = ["charter", "atp", "tech", "risk", "plan", "explore", "robust", "control", "report"]
SPECIAL = {("tech", "matrix"): "matrix", ("risk", "fmea"): "fmea", ("atp", "criteria"): "table",
           ("plan", "phases"): "table", ("control", "sst"): "table"}
CHAR_OPTIONS = ["准确度", "精密度-重复性", "精密度-中间精密度", "联合评价(总误差)", "线性/响应", "专属性", "定量下限", "稳健性/稳定性", "其他"]
TECHS = ["flow", "hplc", "bioassay", "qpcr", "elisa", "cell_based", "generic"]


def numkey(ch):
    return tuple(int(x) for x in ch.split("."))


class TestTemplates(unittest.TestCase):
    def test_URS111_seven_techniques_and_version(self):
        self.assertEqual([t["key"] for t in T.list_templates()], TECHS)
        for t in T.list_templates():
            self.assertEqual(t["version"], "1.1")
            self.assertTrue(t["changelog"])

    def test_URS111_stage_keys_and_special_sections(self):
        for k in TECHS:
            tpl = T.build_template(k)
            self.assertEqual([s["key"] for s in tpl["stages"]], STAGES, k)
            by = {s["key"]: s for s in tpl["stages"]}
            for (sk, seck), typ in SPECIAL.items():
                sec = next(x for x in by[sk]["sections"] if x["key"] == seck)
                self.assertEqual(sec["type"], typ, (k, sk, seck))
            gates = {s["key"]: (s["gate"] or {}).get("key") for s in tpl["stages"]}
            self.assertEqual(gates, {"charter": None, "atp": "G1", "tech": "G2", "risk": None, "plan": "GP", "explore": "G3",
                                     "robust": None, "control": "G4", "report": "G5"})
            self.assertEqual(by["plan"]["gate"]["covers"], ["charter", "atp", "tech", "risk"])

    def test_URS111_unique_keys_and_checklist_refs(self):
        for k in TECHS:
            tpl = T.build_template(k)
            for st in tpl["stages"]:
                keys = [s["key"] for s in st["sections"]]
                self.assertEqual(len(keys), len(set(keys)), (k, st["key"]))
                ck = [c["key"] for c in st["checklist"]]
                self.assertEqual(len(ck), len(set(ck)), (k, st["key"], ck))
                self.assertGreaterEqual(len(ck), 5)
            allck = [c["key"] for st in tpl["stages"] for c in st["checklist"]]
            self.assertEqual(len(allck), len(set(allck)), k)

    def test_URS111_text_sections_have_help_and_placeholder(self):
        for k in TECHS:
            tpl = T.build_template(k)
            for st in tpl["stages"]:
                for s in st["sections"]:
                    if s["type"] == "text":
                        self.assertTrue(s["help"], (k, st["key"], s["key"]))
                        self.assertTrue(s["placeholder"] or s.get("default"), (k, st["key"], s["key"]))

    def test_URS111_required_flags_balanced(self):
        for k in TECHS:
            tpl = T.build_template(k)
            tot = sum(len(s["sections"]) for s in tpl["stages"])
            req = sum(1 for s in tpl["stages"] for x in s["sections"] if x.get("required"))
            self.assertTrue(0.2 < req / tot < 0.5, (k, req, tot))
            for st in tpl["stages"]:
                self.assertTrue(any(x.get("required") for x in st["sections"]), (k, st["key"]))

    def test_URS111_chapter_numbers_stable_and_unique(self):
        struct = T.doc_structure()
        for k in TECHS:
            tpl = T.build_template(k)
            for kind in ("plan", "report"):
                nos = {c["no"] for c in struct[kind]}
                seen = {}
                for st in tpl["stages"]:
                    for s in st["sections"]:
                        ch = s["ch"].get(kind)
                        if not ch:
                            continue
                        self.assertIn(ch.split(".")[0], nos, (k, kind, s["key"], ch))
                        self.assertNotIn(ch, seen, (k, kind, ch, s["key"], seen.get(ch)))
                        seen[ch] = s["key"]
                # every chapter that is not purely automatic has at least one section
                used = {c.split(".")[0] for c in seen}
                for c in struct[kind]:
                    if not c["auto"] or c["auto"] == ["experiments"] or c["auto"] == ["gantt"]:
                        self.assertIn(c["no"], used, (k, kind, c))
                self.assertEqual(tpl["doc_structure"][kind][0]["no"], "1")
            # plan has the required 15 chapters
            self.assertEqual(len(struct["plan"]), 15)

    def test_URS111_tables_seed_rows_match_columns(self):
        for k in TECHS:
            tpl = T.build_template(k)
            for st in tpl["stages"]:
                for s in st["sections"]:
                    if s["type"] == "table":
                        keys = {c["key"] for c in s["columns"]}
                        for r in s["seed_rows"]:
                            self.assertEqual(set(r), keys, (k, st["key"], s["key"]))
                            for c in s["columns"]:
                                if c["type"] == "select" and r[c["key"]]:
                                    self.assertIn(r[c["key"]], c["options"], (k, st["key"], s["key"], c["key"], r[c["key"]]))
                        if s.get("required") and s.get("min_rows"):
                            # must be satisfiable (by seeds or by the user): nothing to assert, only sanity
                            self.assertGreaterEqual(s["min_rows"], 1)

    def test_URS111_presets_per_technique(self):
        for k in TECHS:
            tpl = T.build_template(k)
            by = {s["key"]: {x["key"]: x for x in s["sections"]} for s in tpl["stages"]}
            seed = tpl["seed"]
            self.assertGreaterEqual(len(seed["fmea"]), 10, k)
            for r in seed["fmea"]:
                for f in "SOD":
                    self.assertTrue(1 <= r[f] <= 10)
                self.assertTrue(r["control"].strip())
                self.assertTrue(r["mode"] and r["cause"] and r["effect"])
            self.assertGreaterEqual(len(seed["experiments"]), 8, k)
            codes = [e["code"] for e in seed["experiments"]]
            self.assertEqual(len(codes), len(set(codes)))
            for e in seed["experiments"]:
                self.assertIn(e["stage_key"], ("explore", "robust", "control", "report"))
                self.assertIn(T.SAMPLE_TAG, e["acceptance"], (k, e["code"]))
                self.assertTrue(e["design"].strip() and e["objective"].strip())
            text = " ".join(e["title"] + e["design"] + e["objective"] for e in seed["experiments"])
            for word in ("专属|特异", "精密度", "稳健", "稳定", "SST"):
                self.assertTrue(re.search(word, text), (k, word))
            self.assertTrue(re.search("线性|范围|响应", text), k)
            self.assertTrue(re.search("参比|对照品|标准品|WRM", text), k)
            self.assertTrue(re.search("准确度|回收", text), k)
            self.assertGreaterEqual(len(seed["atp_rows"]), 8, k)
            for r in seed["atp_rows"]:
                self.assertIn(r[0], CHAR_OPTIONS)
            self.assertGreaterEqual(len(seed["sst"]), 4, k)
            for sec in ("charter.glossary", "charter.refdocs", "tech.conditions", "tech.reagents", "plan.materials", "plan.instruments",
                        "atp.samples", "risk.ishikawa", "robust.factors", "robust.stability", "control.references",
                        "control.ecs", "report.validation_matrix"):
                st, key = sec.split(".")
                self.assertTrue(by[st][key]["seed_rows"], (k, sec))
            self.assertGreaterEqual(len(by["charter"]["glossary"]["seed_rows"]), 12, k)
            self.assertGreaterEqual(len(by["charter"]["refdocs"]["seed_rows"]), 8, k)
            self.assertGreaterEqual(len(by["tech"]["conditions"]["seed_rows"]), 5, k)

    def test_URS111_no_forbidden_precision_claims(self):
        """Regulatory references: no clause number for documents we could not check."""
        bad = re.compile(r"(USP\s*<\d+>[^；;）)]*§\s*\d|Ph\.Eur\.[^；;]*§\s*\d|ChP[^；;]*§\s*\d|中国药典[^；;]*§\s*\d)")
        for k in TECHS:
            tpl = T.build_template(k)
            for st in tpl["stages"]:
                for c in st["checklist"]:
                    self.assertIsNone(bad.search(c["ref"] or ""), (k, c["key"], c["ref"]))

    def test_URS111_kb_seed(self):
        items = kb_seed.SEED
        self.assertGreaterEqual(len(kb_seed.SEED_V11), 30)
        titles = [i["title"] for i in items]
        self.assertEqual(len(titles), len(set(titles)))
        for i in items:
            self.assertTrue(i["title"] and i["body"] and i["source"] is not None)
            self.assertIn(i["kind"], ("rule", "pitfall", "howto", "reference"))
            for t in i["techniques"]:
                self.assertIn(t, TECHS + ["all"])
            for s in i["stages"]:
                self.assertIn(s, STAGES)
        kinds = {i["kind"] for i in items}
        self.assertTrue({"howto", "pitfall", "rule"} <= kinds)
        tags = {t for i in kb_seed.SEED_V11 for t in i["tags"]}
        self.assertTrue({"写作指南", "常见缺陷", "检查清单依据"} <= tags)
        self.assertGreaterEqual(sum(1 for i in kb_seed.SEED_V11 if "常见缺陷" in i["tags"]), 8)
        self.assertGreaterEqual(sum(1 for i in kb_seed.SEED_V11 if "写作指南" in i["tags"]), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
