"""V0.4 tests: results with criteria, calculators, registry, run records, deviations, audit-trail reviews, inspection pack,
comments, search, method revisions, password policy, change reason, background documents, outgoing notifications.
Names carry URS ids 150-169 (docs/URS_需求与测试追溯.md)."""
import datetime as dt
import io
import json
import shutil
import tempfile
import time
import unittest
import zipfile
from unittest import mock

import test_workflow as tw
from test_workflow import PW, client, confirm_prefill, fill_required, login, make_project, sign, approve_stage  # noqa: E402

from app import auth, config, db, notifier  # noqa: E402

TMP04 = tempfile.mkdtemp(prefix="mf_v04_")


def setUpModule():
    tw.TMP = TMP04
    tw.setUpModule()
    config.override("pdf_enabled", False)


def tearDownModule():
    shutil.rmtree(TMP04, ignore_errors=True)


def plan_approved():
    a, mid, ids = make_project()
    for k, w in (("charter", False), ("atp", False), ("tech", False), ("risk", False), ("plan", True)):
        approve_stage(mid, k, a, with_approver=w)
    return a, mid, ids


class TestResultsAndCalc(unittest.TestCase):
    def test_URS150_result_rows_get_an_automatic_verdict(self):
        a, mid = plan_approved()[:2]
        e = a.get("/api/methods/%d/experiments" % mid).json()[0]
        a.post("/api/experiments/%d/status" % e["id"], json={"status": "running"})
        cur = a.get("/api/experiments/%d" % e["id"]).json()
        rows = [{"metric": "SI", "value": "46", "criterion": "≥5", "verdict": "符合"},
                {"metric": "背景", "value": "2.5%", "criterion": "≤2%", "verdict": "符合"},          # human says pass, machine says fail
                {"metric": "效率", "value": "98%", "criterion": "90–110%", "verdict": "符合"},
                {"metric": "外观", "value": "合格", "criterion": "见方案", "verdict": "符合"}]
        r = a.put("/api/experiments/%d" % e["id"], json={"version": cur["version"], "results": rows, "conclusion": "x"})
        self.assertEqual(r.status_code, 200, r.text)
        got = {x["metric"]: x.get("auto") for x in a.get("/api/experiments/%d" % e["id"]).json()["results"]}
        self.assertEqual(got, {"SI": "符合", "背景": "不符合", "效率": "符合", "外观": None})
        a.post("/api/experiments/%d/status" % e["id"], json={"status": "done"})
        ck = a.get("/api/methods/%d/stages/explore/checks" % mid).json()
        self.assertTrue(any("自动判定为“不符合”" in w and "背景" in w for w in ck["warns"]), ck["warns"])
        # a user-supplied "auto" is never trusted
        cur = a.get("/api/experiments/%d" % e["id"]).json()
        # (locked after done? the stage is still editable) set a forged value and read it back
        r = a.put("/api/experiments/%d" % e["id"], json={"version": cur["version"], "results": [{"metric": "m", "value": "1", "criterion": "≥5", "auto": "符合"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(a.get("/api/experiments/%d" % e["id"]).json()["results"][0]["auto"], "不符合")

    def test_URS151_calculator_endpoint(self):
        a = login("alice")
        r = a.post("/api/calc/linearity", json={"x": [1, 2, 3, 4], "y": [2, 4.1, 5.9, 8.0]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([x["value"] for x in r.json()["rows"] if x["metric"] == "slope"][0], 1.98)
        self.assertEqual(a.post("/api/calc/nope", json={}).status_code, 400)
        self.assertEqual(a.post("/api/calc/linearity", json={"x": [1, 2], "y": [1, 2]}).status_code, 400)
        self.assertEqual(a.post("/api/calc/summary", json={"values": ["a"]}).status_code, 400)
        self.assertEqual(client().post("/api/calc/summary", json={"values": [1]}).status_code, 401)


class TestRegistryRunsDeviations(unittest.TestCase):
    def test_URS152_registry_and_run_records(self):
        a, mid = plan_approved()[:2]
        rita = login("rita")
        # registry: authors maintain, a reviewer-only user cannot
        self.assertEqual(rita.post("/api/materials", json={"name": "x"}).status_code, 403)
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        soon = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        far = (dt.date.today() + dt.timedelta(days=400)).isoformat()
        m_bad = a.post("/api/materials", json={"name": "抗体 CD19", "kind": "reagent", "lot": "L-1", "expiry_at": yesterday, "critical": True}).json()["id"]
        m_ok = a.post("/api/materials", json={"name": "缓冲液", "lot": "B-9", "expiry_at": far}).json()["id"]
        m_soon = a.post("/api/materials", json={"name": "参比品", "kind": "reference", "lot": "R-2", "expiry_at": soon}).json()["id"]
        eq = a.post("/api/equipment", json={"name": "流式仪 A", "model": "X", "calibration_due": yesterday}).json()["id"]
        al = a.get("/api/registry/alerts").json()
        self.assertIn(m_bad, [x["id"] for x in al["materials"]])
        self.assertIn(m_soon, [x["id"] for x in al["materials"]])
        self.assertNotIn(m_ok, [x["id"] for x in al["materials"]])
        self.assertEqual([x["state"] for x in al["equipment"] if x["id"] == eq], ["overdue"])
        self.assertEqual(a.post("/api/materials", json={"name": "", "kind": "reagent"}).status_code, 400)
        self.assertEqual(a.post("/api/materials", json={"name": "z", "kind": "bogus"}).status_code, 400)
        # a run with an expired reagent and an uncalibrated instrument is allowed but carries the warnings
        ex = a.get("/api/methods/%d/experiments" % mid).json()[0]
        r = a.post("/api/methods/%d/runs" % mid, json={"experiment_id": ex["id"], "run_date": dt.date.today().isoformat(), "materials": [m_bad, m_ok], "equipment": [eq], "summary": "第一次运行"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        run = a.get("/api/methods/%d/runs?experiment_id=%d" % (mid, ex["id"])).json()[0]
        self.assertEqual(run["code"], "RUN-001")
        self.assertEqual(len(run["warnings"]), 2, run["warnings"])
        self.assertTrue(any("过期" in w for w in run["warnings"]) and any("校准" in w for w in run["warnings"]))
        self.assertEqual(a.post("/api/methods/%d/runs" % mid, json={"materials": [999999]}).status_code, 400)
        # second-person verification: not the analyst / recorder; then the run is frozen
        self.assertEqual(a.post("/api/runs/%d/verify" % rid).status_code, 403)
        self.assertEqual(login("bob").post("/api/runs/%d/verify" % rid).status_code, 403)         # not on the method team
        self.assertEqual(rita.post("/api/runs/%d/verify" % rid).status_code, 200)
        self.assertEqual(rita.post("/api/runs/%d/verify" % rid).status_code, 409)
        self.assertEqual(a.put("/api/runs/%d" % rid, json={"version": run["version"], "summary": "改"}).status_code, 409)
        # unknown experiment of another method
        a2, mid2, _ = make_project(title="另一方法")
        foreign = a2.get("/api/methods/%d/experiments" % mid2).json()[0]["id"]
        self.assertEqual(a.post("/api/methods/%d/runs" % mid, json={"experiment_id": foreign}).status_code, 404)

    def test_URS153_deviations_block_gates_and_closing_is_a_signature(self):
        a, mid, ids = make_project()
        quinn, rita = login("quinn"), login("rita")
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        r = a.post("/api/methods/%d/deviations" % mid, json={"title": "试剂批号变更", "description": "改用新批", "classification": "major", "stage_key": "atp"})
        self.assertEqual(r.status_code, 200, r.text)
        did = r.json()["id"]
        # an open major deviation blocks the step it belongs to
        ck = a.get("/api/methods/%d/stages/atp/checks" % mid).json()
        self.assertTrue(any("DEV-001" in b for b in ck["blocks"]), ck)
        self.assertEqual(a.post("/api/methods/%d/stages/atp/submit" % mid, json={}).status_code, 422)
        # closing: not by the opener, needs the root cause and action, an approver for major, and the password
        dev = a.get("/api/methods/%d/deviations" % mid).json()[0]
        self.assertEqual(a.post("/api/deviations/%d/close" % did, json={"password": PW, "note": "ok"}).status_code, 403)       # opener
        self.assertEqual(rita.post("/api/deviations/%d/close" % did, json={"password": PW, "note": "ok"}).status_code, 403)     # major: approver only
        self.assertEqual(quinn.post("/api/deviations/%d/close" % did, json={"password": PW, "note": "ok"}).status_code, 422)    # nothing investigated yet
        self.assertEqual(a.put("/api/deviations/%d" % did, json={"version": dev["version"], "root_cause": "供应商换批", "action": "桥接实验", "status": "investigating"}).status_code, 200)
        self.assertEqual(quinn.post("/api/deviations/%d/close" % did, json={"password": "wrong-password-1", "note": "ok"}).status_code, 403)
        self.assertEqual(quinn.post("/api/deviations/%d/close" % did, json={"password": PW, "note": "已桥接，关闭"}).status_code, 200)
        self.assertEqual(a.get("/api/methods/%d/deviations" % mid).json()[0]["status"], "closed")
        self.assertEqual(a.put("/api/deviations/%d" % did, json={"version": 99, "title": "x"}).status_code, 409)             # closed: no edits
        self.assertFalse(any("DEV-001" in b for b in a.get("/api/methods/%d/stages/atp/checks" % mid).json()["blocks"]))
        # a minor open deviation only warns
        a.post("/api/methods/%d/deviations" % mid, json={"title": "轻微", "classification": "minor", "stage_key": "atp"})
        ck = a.get("/api/methods/%d/stages/atp/checks" % mid).json()
        self.assertTrue(any("DEV-002" in w for w in ck["warns"]) and not any("DEV-002" in b for b in ck["blocks"]))
        # reopen needs a reason
        self.assertEqual(quinn.post("/api/deviations/%d/reopen" % did, json={"password": PW, "reason": ""}).status_code, 400)
        self.assertEqual(quinn.post("/api/deviations/%d/reopen" % did, json={"password": PW, "reason": "复发"}).status_code, 200)
        self.assertEqual(login("bob").get("/api/methods/%d/deviations" % mid).status_code, 403)


class TestCompliance(unittest.TestCase):
    def test_URS154_audit_trail_review(self):
        admin, a = login("admin"), login("alice")
        today = dt.datetime.utcnow().date().isoformat()        # audit timestamps are UTC
        body = {"scope": "all", "period_from": today, "period_to": today, "conclusion": "no_issue", "password": PW}
        self.assertEqual(a.post("/api/audit-reviews", json=body).status_code, 403)
        self.assertEqual(admin.post("/api/audit-reviews", json=dict(body, password="wrong-password-1")).status_code, 403)
        self.assertEqual(admin.post("/api/audit-reviews", json=dict(body, period_to="2000-01-01")).status_code, 400)
        self.assertEqual(admin.post("/api/audit-reviews", json=dict(body, conclusion="issues_found")).status_code, 400)       # findings required
        r = admin.post("/api/audit-reviews", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        got = admin.get("/api/audit-reviews").json()
        self.assertTrue(got["items"][0]["chain_ok"])
        self.assertGreater(got["items"][0]["entries_checked"], 0)
        self.assertFalse(got["status"]["overdue"])
        self.assertEqual(got["status"]["days_since"], 0)

    def test_URS155_inspection_pack(self):
        a, mid = plan_approved()[:2]
        self.assertEqual(a.post("/api/methods/%d/attachments?filename=raw.fcs&stage_key=explore" % mid, content=b"FCS" * 100).status_code, 200)
        r = a.get("/api/methods/%d/dossier" % mid)
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        for need in ("README.txt", "method.json", "experiments.csv", "runs.csv", "deviations.csv", "signatures.csv", "audit_trail.csv", "attachments_manifest.csv"):
            self.assertIn(need, names)
        self.assertTrue(any(n.startswith("attachments/") and n.endswith("raw.fcs") for n in names))
        manifest = z.read("attachments_manifest.csv").decode("utf-8-sig")
        self.assertIn("raw.fcs", manifest)
        self.assertIn("yes", manifest)
        self.assertIn("stage.sign", z.read("audit_trail.csv").decode("utf-8-sig"))
        self.assertGreater(len(z.read("signatures.csv").decode("utf-8-sig").splitlines()), 2)
        # without files only the manifests
        z2 = zipfile.ZipFile(io.BytesIO(a.get("/api/methods/%d/dossier?files=0" % mid).content))
        self.assertFalse(any(n.startswith("attachments/") for n in z2.namelist()))
        self.assertEqual(login("bob").get("/api/methods/%d/dossier" % mid).status_code, 403)
        self.assertEqual(client().get("/api/methods/%d/dossier" % mid).status_code, 401)

    def test_URS156_comments_and_mentions(self):
        a, mid, ids = make_project()
        rita = login("rita")
        base = "/api/methods/%d/stages/atp/comments" % mid
        r = rita.post(base, json={"section_key": "criteria", "body": "请补充依据 @alice 和 @nobody"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(rita.post(base, json={"body": ""}).status_code, 400)
        self.assertEqual(login("bob").post(base, json={"body": "x"}).status_code, 403)
        n = a.get("/api/notifications").json()["items"]
        self.assertTrue(any(i["kind"] == "mention" for i in n), n)
        lst = a.get(base).json()
        self.assertEqual((lst[0]["section_key"], lst[0]["user_name"], lst[0]["resolved"]), ("criteria", "丽塔(复核)", False))
        self.assertEqual(login("bob").post("/api/comments/%d/resolve" % lst[0]["id"], json={}).status_code, 403)
        self.assertEqual(a.post("/api/comments/%d/resolve" % lst[0]["id"], json={}).status_code, 200)
        self.assertTrue(a.get(base).json()[0]["resolved"])
        self.assertEqual(a.post("/api/methods/%d/stages/nope/comments" % mid, json={"body": "x"}).status_code, 404)

    def test_URS157_global_search_respects_visibility(self):
        a, mid, ids = make_project(title="独特搜索词XYZ方法")
        r = a.get("/api/search?q=XYZ").json()
        self.assertTrue([x for x in r["methods"] if x["id"] == mid], r)
        self.assertFalse([x for x in login("bob").get("/api/search?q=XYZ").json()["methods"] if x["id"] == mid])      # not a member
        self.assertEqual(a.get("/api/search?q=a").status_code, 400)                                                       # too short
        self.assertTrue(a.get("/api/search?q=ICH").json()["links"])
        self.assertEqual(client().get("/api/search?q=XYZ").status_code, 401)

    def test_URS158_method_revision(self):
        a, mid, ids = make_project()
        self.assertEqual(a.post("/api/methods/%d/revise" % mid, json={"note": "x"}).status_code, 409)           # nothing approved yet
        approve_stage(mid, "charter", a)
        self.assertEqual(a.post("/api/methods/%d/revise" % mid, json={"note": ""}).status_code, 400)
        self.assertEqual(login("rita").post("/api/methods/%d/revise" % mid, json={"note": "x"}).status_code, 403)
        r = a.post("/api/methods/%d/revise" % mid, json={"note": "变更判据", "version": "V1.1"})
        self.assertEqual(r.status_code, 200, r.text)
        new = a.get("/api/methods/%d" % r.json()["id"]).json()
        self.assertEqual((new["method_version"], new["revision_of_info"]["id"], new["revision_note"]), ("V1.1", mid, "变更判据"))
        old = a.get("/api/methods/%d" % mid).json()
        self.assertEqual([x["id"] for x in old["revisions"]], [new["id"]])
        self.assertEqual(old["stages"][0]["status"], "completed")                                                # the old method is untouched
        self.assertEqual(new["stages"][0]["status"], "not_started")


class TestPasswordPolicyAndReason(unittest.TestCase):
    def test_URS159_password_history_and_expiry(self):
        admin = login("admin")
        r = admin.post("/api/users", json={"username": "pwuser", "display_name": "PW", "password": PW, "roles": ["author"], "email": "pw@example.org"})
        self.assertEqual(r.status_code, 200, r.text)
        with db.tx() as conn:
            conn.execute("UPDATE users SET must_change=0 WHERE username='pwuser'")
        u = login("pwuser")
        self.assertEqual(u.get("/api/me").json()["user"]["email"], "pw@example.org")
        p2, p3 = "Another2026pw", "Third2026passw"
        self.assertEqual(u.post("/api/me/password", json={"old": PW, "new": p2}).status_code, 200)
        u = login("pwuser", p2)
        self.assertEqual(u.post("/api/me/password", json={"old": p2, "new": PW}).status_code, 400)             # PW is in the history
        self.assertEqual(u.post("/api/me/password", json={"old": p2, "new": p3}).status_code, 200)
        with mock.patch.dict(config._cfg, {"password_history": 0}):
            u = login("pwuser", p3)
            self.assertEqual(u.post("/api/me/password", json={"old": p3, "new": PW}).status_code, 200)         # history off: allowed again
        # expiry: an old password forces a change at login
        with db.tx() as conn:
            conn.execute("UPDATE users SET pw_changed_at='2000-01-01T00:00:00Z' WHERE username='pwuser'")
        with mock.patch.dict(config._cfg, {"password_max_days": 90}):
            c = client()
            self.assertTrue(c.post("/api/login", json={"username": "pwuser", "password": PW}).json()["user"]["must_change"])
        self.assertEqual(admin.patch("/api/users/%d" % u.get("/api/me").json()["user"]["id"], json={"email": "not-an-email"}).status_code, 400)

    def test_URS160_change_reason_when_enabled(self):
        a, mid, _ = make_project()
        rita = login("rita")
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        a.post("/api/methods/%d/stages/atp/submit" % mid, json={})
        sign(rita, mid, "atp", "reject", "补充")
        url = "/api/methods/%d/stages/atp" % mid
        with mock.patch.dict(config._cfg, {"require_change_reason": True}):
            st = a.get(url).json()
            r = a.put(url, json={"version": st["version"], "sections": {"use": "新用途"}})
            self.assertEqual(r.status_code, 400, r.text)
            r = a.put(url, json={"version": st["version"], "sections": {"use": "新用途"}, "reason": "按复核意见补充"})
            self.assertEqual(r.status_code, 200, r.text)
        with db.read() as conn:
            row = conn.execute("SELECT reason FROM audit_log WHERE action='stage.save' AND method_id=? ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
        self.assertEqual(row["reason"], "按复核意见补充")
        st = a.get(url).json()                                                                                     # default (off): no reason needed
        self.assertEqual(a.put(url, json={"version": st["version"], "sections": {"use": "再改"}}).status_code, 200)


class TestAsyncDocsAndNotifier(unittest.TestCase):
    def test_URS161_background_document_generation(self):
        a, mid = plan_approved()[:2]
        r = a.post("/api/methods/%d/docs" % mid, json={"kind": "plan", "async": True})
        self.assertEqual(r.status_code, 200, r.text)
        jid = r.json()["job_id"]
        for _ in range(120):
            j = a.get("/api/jobs/%s" % jid).json()
            if j["status"] != "running":
                break
            time.sleep(0.5)
        self.assertEqual(j["status"], "done", j)
        self.assertEqual(j["result"]["docs"][0]["format"], "docx")
        self.assertEqual(login("bob").get("/api/jobs/%s" % jid).status_code, 404)                                  # somebody else's job
        self.assertEqual(a.get("/api/jobs/nope").status_code, 404)
        r = a.post("/api/methods/%d/docs" % mid, json={"kind": "bogus", "async": True})
        jid = r.json()["job_id"]
        for _ in range(60):
            j = a.get("/api/jobs/%s" % jid).json()
            if j["status"] != "running":
                break
            time.sleep(0.2)
        self.assertEqual(j["status"], "error")

    def test_URS163_english_document_export_translates_fixed_text(self):
        import io
        import re
        from docx import Document
        cjk = re.compile("[一-鿿]")
        a, mid = plan_approved()[:2]

        def headings(lang):
            r = a.post("/api/methods/%d/docs" % mid, json={"kind": "plan", "lang": lang})
            self.assertEqual(r.status_code, 200, r.text)
            d = next(x for x in r.json()["docs"] if x["format"] == "docx")
            doc = Document(io.BytesIO(a.get("/api/docs/%d/download" % d["id"]).content))
            return [p.text for p in doc.paragraphs if p.style.name.startswith("Heading") and p.text.strip()]
        en, zh = headings("en"), headings("zh")
        self.assertTrue(en and zh)
        self.assertEqual([h for h in en if cjk.search(h)], [], "English export left Chinese headings")
        self.assertTrue(any(cjk.search(h) for h in zh))                                                            # the default stays Chinese

    def test_URS162_outgoing_notifications(self):
        calls = {"mail": [], "hook": []}
        with mock.patch.dict(config._cfg, {"smtp_host": "smtp.invalid", "webhook_url": "https://hook.invalid/x", "webhook_kind": "wecom", "public_url": "http://lab:8780"}), \
                mock.patch.object(notifier, "send_mail", side_effect=lambda to, subj, text: calls["mail"].append((to, subj, text))), \
                mock.patch.object(notifier, "send_webhook", side_effect=lambda text: calls["hook"].append(text)):
            admin = login("admin")
            admin.patch("/api/users/%d" % [u for u in admin.get("/api/users").json() if u["username"] == "rita"][0]["id"], json={"email": "rita@example.org"})
            a, mid, _ = make_project()
            approve_stage(mid, "charter", a)
            fill_required(a, mid, "atp")
            a.post("/api/methods/%d/stages/atp/submit" % mid, json={})           # -> rita (reviewer) gets a message
            with db.read() as conn:
                rid = [u["id"] for u in admin.get("/api/users").json() if u["username"] == "rita"][0]
                nid = conn.execute("SELECT id FROM notifications WHERE kind='review_requested' AND user_id=? ORDER BY id DESC LIMIT 1", (rid,)).fetchone()["id"]
            self.assertTrue(notifier.deliver(nid))
        self.assertEqual(calls["mail"][0][0], "rita@example.org")
        self.assertIn("http://lab:8780/#/m/%d/stage/atp" % mid, calls["mail"][0][2])
        self.assertIn("待您复核", calls["hook"][0])
        self.assertEqual(notifier.webhook_payload("t\nb")["text"] if False else notifier.webhook_payload("t")["title"], "t")
        with mock.patch.dict(config._cfg, {"webhook_kind": "feishu"}):
            self.assertEqual(notifier.webhook_payload("x")["msg_type"], "text")
        self.assertFalse(notifier.deliver(99999999))                              # a row that does not exist (rolled back) sends nothing
        self.assertEqual(login("alice").post("/api/admin/notify-test").status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
