"""V0.3 tests: notifications, revision diff, bulk experiment actions, rescheduling, dashboard next steps,
resource links, in-place schema upgrade 3 -> 4.  Names carry URS ids 140-149 (docs/URS_需求与测试追溯.md)."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import test_workflow as tw
from test_workflow import PW, client, confirm_prefill, fill_required, login, make_project, sign, approve_stage  # noqa: E402

from app import config, db, kb_links  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


TMP03 = tempfile.mkdtemp(prefix="mf_v03_")


def setUpModule():
    tw.TMP = TMP03
    tw.setUpModule()          # own database + the standard users (alice, bob, rita, quinn, rob, admin)
    config.override("pdf_enabled", False)


def tearDownModule():
    shutil.rmtree(TMP03, ignore_errors=True)


class TestNotifications(unittest.TestCase):
    def test_URS140_notifications_follow_the_review_flow(self):
        a, mid, _ = make_project()
        rita, quinn = login("rita"), login("quinn")
        base = "/api/methods/%d/stages/" % mid
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        self.assertEqual(a.post(base + "atp/submit", json={}).status_code, 200)
        n = rita.get("/api/notifications").json()
        self.assertTrue(n["unread"] >= 1)
        self.assertTrue(any(i["kind"] == "review_requested" and i["stage_key"] == "atp" for i in n["items"]), n)
        # the actor does not notify herself
        self.assertFalse(any(i["kind"] == "review_requested" for i in a.get("/api/notifications").json()["items"]))
        # reject -> the author is told
        self.assertEqual(sign(rita, mid, "atp", "reject", "判据缺依据").status_code, 200)
        an = a.get("/api/notifications").json()
        self.assertTrue(any(i["kind"] == "returned" and "判据缺依据" in i["body"] for i in an["items"]), an)
        # mark as read
        ids = [i["id"] for i in rita.get("/api/notifications").json()["items"]]
        r = rita.post("/api/notifications/read", json={"ids": ids})
        self.assertEqual(r.json()["unread"], 0)
        self.assertEqual(rita.post("/api/notifications/read", json={}).status_code, 400)
        # two-step gate: after the reviewer signs, the approver is asked
        fill_required(a, mid, "atp")
        a.post(base + "atp/submit", json={})
        sign(rita, mid, "atp")                       # G1 is reviewer-only -> approved -> authors informed
        self.assertTrue(any(i["kind"] == "approved" for i in a.get("/api/notifications").json()["items"]))
        approve_stage(mid, "tech", a)
        approve_stage(mid, "risk", a)
        fill_required(a, mid, "plan")
        a.post(base + "plan/submit", json={})
        sign(rita, mid, "plan")
        self.assertTrue(any(i["kind"] == "review_requested" and i["stage_key"] == "plan" for i in quinn.get("/api/notifications?unread=1").json()["items"]))
        # a user only sees their own notifications
        self.assertFalse(any(i["stage_key"] == "plan" for i in login("bob").get("/api/notifications").json()["items"]))


class TestDiff(unittest.TestCase):
    def test_URS141_revision_diff_shows_what_changed(self):
        a, mid, _ = make_project()
        rita = login("rita")
        base = "/api/methods/%d/stages/atp" % mid
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        a.post(base + "/submit", json={})
        d = a.get(base + "/diff").json()
        self.assertIsNone(d["from"])                                 # first submission: nothing to compare
        sign(rita, mid, "atp", "reject", "请补充")
        st = a.get(base).json()
        a.put(base, json={"version": st["version"], "sections": {"use": "改后的预期用途"}})
        a.post(base + "/submit", json={})
        d = a.get(base + "/diff").json()
        self.assertEqual((d["from"], d["to"]), (1, 2))
        self.assertIn("use", [c["key"] for c in d["changes"]])
        ch = [c for c in d["changes"] if c["key"] == "use"][0]
        self.assertEqual(ch["new"], "改后的预期用途")
        self.assertEqual(login("bob").get(base + "/diff").status_code, 403)   # not a member -> no access


class TestBulkAndSchedule(unittest.TestCase):
    def _plan_approved(self):
        a, mid, _ = make_project()
        for k, w in (("charter", False), ("atp", False), ("tech", False), ("risk", False), ("plan", True)):
            approve_stage(mid, k, a, with_approver=w)
        return a, mid

    def test_URS142_bulk_start_and_cancel_experiments(self):
        a, mid = self._plan_approved()
        ex = a.get("/api/methods/%d/experiments" % mid).json()
        ids = [e["id"] for e in ex[:4]]
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": ids, "action": "start"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sorted(r.json()["done"]), sorted(ids))
        # cancel needs a reason: the experiments that fail are reported per experiment, the rest proceed
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": ids, "action": "cancel", "reason": ""})
        self.assertEqual(len(r.json()["failed"]), 4)
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": ids[:2], "action": "cancel", "reason": "范围调整"})
        self.assertEqual(len(r.json()["done"]), 2)
        # another method's experiment id is rejected, junk input is a clean 400
        a2, mid2, _ = make_project(title="另一个")
        foreign = a2.get("/api/methods/%d/experiments" % mid2).json()[0]["id"]
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": [foreign], "action": "start"})
        self.assertEqual(len(r.json()["failed"]), 1)
        self.assertEqual(a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": "x", "action": "start"}).status_code, 400)
        self.assertEqual(a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": ids, "action": "delete"}).status_code, 400)
        self.assertEqual(login("bob").post("/api/methods/%d/experiments/bulk" % mid, json={"ids": ids, "action": "start"}).status_code, 403)

    def test_URS148_plan_cannot_be_submitted_with_example_criteria_and_they_can_be_confirmed_in_bulk(self):
        a, mid, _ = make_project("qpcr", title="qPCR-示例值")
        for k in ("charter", "atp", "tech", "risk"):
            approve_stage(mid, k, a)
        fill_required(a, mid, "plan")            # helper confirms the sections but leaves the experiments' marks alone
        ex = a.get("/api/methods/%d/experiments" % mid).json()
        # undo the helper's scrub of experiments for this test: re-add a marker to one experiment
        e0 = ex[0]
        cur = a.get("/api/experiments/%d" % e0["id"]).json()
        self.assertEqual(a.put("/api/experiments/%d" % e0["id"], json={"version": cur["version"], "acceptance": "SI≥5（示例值，须按ATP确认）"}).status_code, 200)
        ck = a.get("/api/methods/%d/stages/plan/checks" % mid).json()
        self.assertTrue(any("示例值" in b and e0["code"] in b for b in ck["blocks"]), ck)
        self.assertEqual(a.post("/api/methods/%d/stages/plan/submit" % mid, json={}).status_code, 422)
        # the user states that the criteria were checked: bulk confirm removes the marker
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": [e0["id"]], "action": "confirm_examples"})
        self.assertEqual(r.json()["done"], [e0["id"]], r.text)
        self.assertNotIn("示例值", a.get("/api/experiments/%d" % e0["id"]).json()["acceptance"])
        r = a.post("/api/methods/%d/experiments/bulk" % mid, json={"ids": [e0["id"]], "action": "confirm_examples"})
        self.assertEqual(len(r.json()["failed"]), 1)                            # nothing left to confirm
        ck = a.get("/api/methods/%d/stages/plan/checks" % mid).json()
        self.assertFalse(any("示例值" in b for b in ck["blocks"]), ck)

    def test_URS143_reschedule_moves_open_stages_only(self):
        a, mid, _ = make_project()
        approve_stage(mid, "charter", a)
        before = {s["key"]: (s["planned_start"], s["planned_end"]) for s in a.get("/api/methods/%d" % mid).json()["stages"]}
        r = a.post("/api/methods/%d/reschedule" % mid, json={"from_stage": "atp", "start_date": "2027-03-01"})
        self.assertEqual(r.status_code, 200, r.text)
        after = {s["key"]: (s["planned_start"], s["planned_end"]) for s in a.get("/api/methods/%d" % mid).json()["stages"]}
        self.assertEqual(after["charter"], before["charter"])             # completed step unchanged
        self.assertEqual(after["atp"][0], "2027-03-01")
        self.assertEqual(after["atp"][1], "2027-03-14")                   # 2 weeks
        self.assertEqual(after["tech"][0], "2027-03-15")                  # next step starts the day after
        self.assertEqual(a.post("/api/methods/%d/reschedule" % mid, json={"from_stage": "nope", "start_date": "2027-03-01"}).status_code, 400)
        self.assertEqual(a.post("/api/methods/%d/reschedule" % mid, json={"from_stage": "atp", "start_date": "kein"}).status_code, 400)
        self.assertEqual(login("rita").post("/api/methods/%d/reschedule" % mid, json={"from_stage": "atp", "start_date": "2027-03-01"}).status_code, 403)


class TestDashboard(unittest.TestCase):
    def test_URS144_dashboard_lists_the_next_step_and_hides_blocked_experiments(self):
        a, mid, _ = make_project()
        d = a.get("/api/dashboard").json()
        mine = [x for x in d["my_stages"] if x["method_id"] == mid]
        self.assertEqual([x["stage_key"] for x in mine], ["charter"])            # only the open step, not the blocked ones
        self.assertEqual(mine[0]["status_label"], "可以开始")
        self.assertEqual([x for x in d["my_experiments"] if x["method_id"] == mid], [])   # plan not approved: experiments cannot start
        approve_stage(mid, "charter", a)
        d = a.get("/api/dashboard").json()
        self.assertIn("atp", [x["stage_key"] for x in d["my_stages"] if x["method_id"] == mid])
        for k, w in (("atp", False), ("tech", False), ("risk", False), ("plan", True)):
            approve_stage(mid, k, a, with_approver=w)
        d = a.get("/api/dashboard").json()
        self.assertTrue([x for x in d["my_experiments"] if x["method_id"] == mid])


class TestLinks(unittest.TestCase):
    def test_URS145_resource_links_library(self):
        admin = login("admin")
        rows = admin.get("/api/kb/links").json()
        self.assertGreater(len(rows), 40)
        self.assertEqual(len({r["url"] for r in rows}), len(rows))
        cats = {c["key"] for c in admin.get("/api/kb/link-categories").json()}
        self.assertTrue({r["category"] for r in rows} <= cats)
        # create (author may), duplicate refused, bad input refused
        a = login("alice")
        body = {"category": "tools", "title": "测试链接", "title_en": "Test link", "url": "https://example.org/x", "org": "Example", "tags": ["a", "b"]}
        r = a.post("/api/kb/links", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        lid = r.json()["id"]
        self.assertEqual(a.post("/api/kb/links", json=body).status_code, 409)
        self.assertEqual(a.post("/api/kb/links", json=dict(body, url="javascript:alert(1)")).status_code, 400)
        self.assertEqual(a.post("/api/kb/links", json=dict(body, url="https://example.org/y", category="zzz")).status_code, 400)
        self.assertEqual(a.post("/api/kb/links", json=dict(body, url="https://example.org/y", title="")).status_code, 400)
        # only admin / approver edit or deactivate
        self.assertEqual(a.put("/api/kb/links/%d" % lid, json=dict(body, title="改")).status_code, 403)
        self.assertEqual(admin.put("/api/kb/links/%d" % lid, json=dict(body, title="改名后", url="https://example.org/z")).status_code, 200)
        got = [x for x in admin.get("/api/kb/links?q=改名后").json()]
        self.assertEqual(got[0]["url"], "https://example.org/z")
        self.assertIsNone(got[0]["status_code"])                                  # URL changed -> old check result cleared
        self.assertEqual(admin.delete("/api/kb/links/%d" % lid).status_code, 200)
        self.assertFalse([x for x in a.get("/api/kb/links?q=改名后").json()])      # deactivated: hidden ...
        self.assertTrue([x for x in admin.get("/api/kb/links?q=改名后&all=1").json()])   # ... but kept for admins
        self.assertEqual(admin.delete("/api/kb/links/%d?restore=1" % lid).status_code, 200)
        self.assertTrue([x for x in a.get("/api/kb/links?q=改名后").json()])

    def test_URS146_link_check_refuses_non_public_hosts_and_records_results(self):
        code, note = kb_links.check_url("http://127.0.0.1:9/")
        self.assertIsNone(code)
        self.assertIn("公网", note)
        self.assertIsNone(kb_links.check_url("file:///etc/passwd")[0])
        # the admin endpoint stores what the checker returned (checker stubbed: no internet needed)
        from unittest import mock
        admin = login("admin")
        rows = admin.get("/api/kb/links").json()[:3]
        with mock.patch.object(kb_links, "check_url", side_effect=[(200, ""), (404, "Not Found"), (None, "URLError")]):
            r = admin.post("/api/admin/kb-links/check", json={"ids": [x["id"] for x in rows]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["checked"], r.json()["ok"], r.json()["failed"]), (3, 1, 2))
        after = {x["id"]: x for x in admin.get("/api/kb/links").json()}
        self.assertEqual(sorted(after[x["id"]]["status_code"] or 0 for x in rows), [0, 200, 404])
        self.assertEqual(login("alice").post("/api/admin/kb-links/check", json={}).status_code, 403)


class TestUpgrade(unittest.TestCase):
    def test_URS147_schema_3_upgrades_in_place_to_current_with_a_backup(self):
        d = tempfile.mkdtemp(prefix="mf_up_")
        code = (
            "import os, sqlite3, sys\n"
            "sys.path.insert(0, %r)\n"
            "from app import db, config\n"
            "db.init_db()\n"
            "c = sqlite3.connect(str(config.DB_PATH))\n"
            "c.execute('DROP TABLE notifications'); c.execute('DROP TABLE kb_links'); c.execute('PRAGMA user_version=3'); c.commit(); c.close()\n"
            "db.init_db()\n"
            "c = sqlite3.connect(str(config.DB_PATH))\n"
            "print(c.execute('PRAGMA user_version').fetchone()[0], len([r for r in c.execute(\"select name from sqlite_master where name in ('notifications','kb_links')\")]),"
            " len(list(config.BACKUPS.glob('premigrate_v3_*.db'))))\n" % ROOT)
        env = dict(os.environ, METHODFLOW_DATA=d)
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.split(), [str(5), "2", "1"], out.stdout + out.stderr)
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
