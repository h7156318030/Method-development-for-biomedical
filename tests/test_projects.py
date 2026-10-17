"""Tests for the project / method split (data model v2), the template seeds and the knowledge-base sync.
URS-100 ... URS-110, see docs/URS_需求与测试追溯.md.  Run:  python -m unittest discover -s tests -v"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import test_workflow as tw                       # sets METHODFLOW_DATA and imports the app (shared helpers)
from test_workflow import DEFAULT_TEAM, PW, client, fill_required, login, make_project, project_id_of, sign, approve_stage  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import audit, auth, config, db, kb_seed, main, templates_data, workflow  # noqa: E402

PTMP = tempfile.mkdtemp(prefix="mf_proj_")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = {}
USERS = [("alice", ["author"]), ("bob", ["author"]), ("carol", ["author"]), ("dora", ["author", "reviewer"]),
         ("rita", ["reviewer"]), ("rob", ["reviewer"]), ("quinn", ["approver"]), ("vic", ["viewer"]), ("pat", ["reviewer"])]


def setUpModule():
    config.set_data(PTMP)
    config.override("pdf_enabled", False)      # PDF output has its own tests (test_docgen.py); here it would only slow things down
    auth.reset_limits()
    db.init_db()
    main._seed_kb()
    c = client()
    r = c.post("/api/setup", json={"username": "admin", "display_name": "管理员", "password": PW})
    assert r.status_code == 200, r.text
    for u, roles in USERS:
        r = c.post("/api/users", json={"username": u, "display_name": u.capitalize(), "password": PW, "roles": roles})
        assert r.status_code == 200, r.text
    with db.tx() as conn:
        conn.execute("UPDATE users SET must_change=0")
    for u in c.get("/api/users").json():
        IDS[u["username"]] = u["id"]


def tearDownModule():
    shutil.rmtree(PTMP, ignore_errors=True)


# ====================================================================== helpers
def raw(sql, args=()):
    con = sqlite3.connect(str(config.DB_PATH), timeout=15)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def pm(*pairs):
    """[(username, project role)] -> API member list."""
    return [{"user_id": IDS[n], "role": r} for n, r in pairs]


def mm(*pairs):
    """[(username, method role)] -> API member list."""
    return [{"user_id": IDS[n], "role": r} for n, r in pairs]


def new_project(c, name="P", members=(), **kw):
    r = c.post("/api/projects", json=dict(name=name, members=pm(*members), **kw))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def new_method(c, pid, name="M", template="flow", members=(), **kw):
    r = c.post("/api/projects/%d/methods" % pid, json=dict(name=name, template_key=template, members=mm(*members), **kw))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ====================================================================== projects
class TestProjects(unittest.TestCase):
    def test_URS100_project_crud_team_and_codes(self):
        alice, vic, rita, bob, carol, admin = login("alice"), login("vic"), login("rita"), login("bob"), login("carol"), login("admin")
        # creating a project needs the global role author (or admin)
        for c in (vic, rita):
            self.assertEqual(c.post("/api/projects", json={"name": "x"}).status_code, 403)
        r = alice.post("/api/projects", json={"name": "XX-CAR-T 方法包", "product": "XX-CAR-T", "indication": "r/r B-ALL", "phase": "I 期",
                                              "description": "管线层面的分析方法包", "planned_start": "2026-01-05", "planned_end": "2026-12-31",
                                              "members": pm(("rita", "member"), ("vic", "viewer"), ("bob", "member"))})
        self.assertEqual(r.status_code, 200, r.text)
        pid = r.json()["id"]
        d = alice.get("/api/projects/%d" % pid).json()
        self.assertRegex(d["code"], r"^PRJ-\d{4}-\d{3}$")
        self.assertEqual((d["name"], d["product"], d["indication"], d["phase"], d["description"], d["status"]),
                         ("XX-CAR-T 方法包", "XX-CAR-T", "r/r B-ALL", "I 期", "管线层面的分析方法包", "active"))
        self.assertEqual((d["planned_start"], d["planned_end"], d["status_label"]), ("2026-01-05", "2026-12-31", "进行中"))
        self.assertEqual(d["my_roles"], ["owner"])
        self.assertEqual({m["username"]: m["role"] for m in d["members"]}, {"alice": "owner", "rita": "member", "vic": "viewer", "bob": "member"})
        self.assertTrue(d["permissions"]["can_edit"] and d["permissions"]["can_manage_members"] and d["permissions"]["can_create_method"])
        self.assertEqual((d["method_count"], d["progress"], d["overdue"], d["stale"]), (0, 0, [], []))
        # the code sequence moves on
        pid2 = new_project(alice, "第二个项目")
        c2 = alice.get("/api/projects/%d" % pid2).json()["code"]
        self.assertEqual(int(c2[-3:]), int(d["code"][-3:]) + 1)
        self.assertEqual(c2[:8], d["code"][:8])
        # visibility: members and admins only
        self.assertEqual(carol.get("/api/projects/%d" % pid).status_code, 403)
        self.assertEqual(rita.get("/api/projects/%d" % pid).status_code, 200)
        self.assertEqual(vic.get("/api/projects/%d" % pid).status_code, 200)
        self.assertEqual(admin.get("/api/projects/%d" % pid).status_code, 200)
        self.assertEqual(rita.get("/api/projects/%d" % pid).json()["permissions"]["can_edit"], False)
        self.assertIn(pid, [p["id"] for p in rita.get("/api/projects").json()])
        self.assertNotIn(pid, [p["id"] for p in carol.get("/api/projects").json()])
        self.assertIn(pid, [p["id"] for p in admin.get("/api/projects").json()])
        self.assertEqual([p["id"] for p in alice.get("/api/projects?q=XX-CAR-T").json()], [pid])
        self.assertEqual([p["id"] for p in alice.get("/api/projects?q=" + d["code"]).json()], [pid])
        self.assertEqual(alice.get("/api/projects?status=archived").json(), [])
        row = next(p for p in alice.get("/api/projects").json() if p["id"] == pid)
        self.assertGreaterEqual(set(row), {"id", "code", "name", "product", "indication", "phase", "status", "status_label", "owner_id", "owner_name",
                                           "my_roles", "method_count", "progress", "overdue", "stale", "planned_start", "planned_end"})
        # only the project owner edits the project
        url = "/api/projects/%d" % pid
        for c in (rita, vic, bob):
            self.assertEqual(c.patch(url, json={"product": "other"}).status_code, 403)
        self.assertEqual(carol.patch(url, json={"product": "other"}).status_code, 403)
        self.assertEqual(alice.patch(url, json={"indication": "DLBCL", "phase": "II 期", "description": "新说明", "planned_end": "2027-03-01"}).status_code, 200)
        d = alice.get(url).json()
        self.assertEqual((d["indication"], d["phase"], d["description"], d["planned_end"]), ("DLBCL", "II 期", "新说明", "2027-03-01"))

    def test_URS100_project_team_rules(self):
        alice, bob = login("alice"), login("bob")
        pid = new_project(alice, "T", members=[("rita", "member"), ("bob", "member")])
        url = "/api/projects/%d/members" % pid
        base = pm(("alice", "owner"), ("rita", "member"), ("bob", "member"))
        self.assertEqual(bob.put(url, json={"members": base}).status_code, 403)                    # a member is not the owner
        self.assertEqual(alice.put(url, json={"members": pm(("rita", "owner"))}).status_code, 400)  # global reviewer cannot own a project
        self.assertEqual(alice.put(url, json={"members": pm(("bob", "owner"))}).status_code, 200)   # ... an author can (and alice is dropped)
        self.assertEqual(alice.get("/api/projects/%d" % pid).status_code, 403)
        self.assertEqual(bob.put(url, json={"members": pm(("rita", "member"), ("bob", "member"))}).status_code, 400)   # no owner left in that list
        self.assertEqual(bob.put(url, json={"members": []}).status_code, 400)
        self.assertEqual(bob.put(url, json={"members": pm(("alice", "owner"), ("bob", "owner"), ("rita", "viewer"), ("rita", "member"))}).status_code, 200)
        team = {m["username"]: m["role"] for m in bob.get("/api/projects/%d" % pid).json()["members"]}
        self.assertEqual(team, {"alice": "owner", "bob": "owner", "rita": "member"})                # one role per person: the highest wins
        for bad in ("abc", [1], [{"role": "owner"}], [{"user_id": "x", "role": "owner"}], [{"user_id": IDS["rita"], "role": "king"}],
                    [{"user_id": 99999, "role": "member"}], [{"user_id": True, "role": "member"}], [{"user_id": IDS["rita"], "role": "reviewer"}]):
            self.assertEqual(alice.put(url, json={"members": bad}).status_code, 400, bad)
        # nobody who is still on a method team can be taken out of the project
        mid = new_method(alice, pid, "M", members=[("rita", "reviewer")])
        r = alice.put(url, json={"members": pm(("alice", "owner"), ("bob", "member"))})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn(alice.get("/api/methods/%d" % mid).json()["code"], r.json()["error"])
        self.assertEqual(alice.put("/api/methods/%d/members" % mid, json={"members": mm(("alice", "owner"), ("alice", "author"))}).status_code, 200)
        self.assertEqual(alice.put(url, json={"members": pm(("alice", "owner"), ("bob", "member"))}).status_code, 200)

    def test_URS100_project_status_rules(self):
        alice = login("alice")
        pid = new_project(alice, "S")
        mid = new_method(alice, pid, "SM")
        url = "/api/projects/%d" % pid
        r = alice.patch(url, json={"status": "completed"})
        self.assertEqual(r.status_code, 422, r.text)                                  # an active method is still running
        self.assertEqual(alice.patch("/api/methods/%d" % mid, json={"status": "cancelled"}).status_code, 200)
        self.assertEqual(alice.patch(url, json={"status": "completed"}).status_code, 200)
        self.assertEqual(alice.get(url).json()["status_label"], "完成")
        self.assertEqual(alice.patch(url, json={"status": "active"}).status_code, 400)
        self.assertEqual(alice.patch(url, json={"status": "active", "reason": "补做", "password": PW}).status_code, 200)
        self.assertEqual(alice.patch(url, json={"status": "paused"}).status_code, 200)
        self.assertEqual(alice.get(url).json()["status_label"], "暂停")

    def test_URS110_project_audit_aggregates_its_methods_and_records_both_keys(self):
        alice, admin = login("alice"), login("admin")
        p1, p2 = new_project(alice, "A1"), new_project(alice, "A2")
        m1, m2, m3 = new_method(alice, p1, "m1"), new_method(alice, p1, "m2"), new_method(alice, p2, "m3")
        ver = alice.get("/api/methods/%d/stages/charter" % m1).json()["version"]
        self.assertEqual(alice.put("/api/methods/%d/stages/charter" % m1, json={"version": ver, "sections": {"background": "x"}}).status_code, 200)
        rows = alice.get("/api/projects/%d/audit" % p1).json()
        actions = [(r["action"], r["method_id"]) for r in rows]
        self.assertIn(("project.create", None), actions)
        self.assertIn(("method.create", m1), actions)
        self.assertIn(("method.create", m2), actions)
        self.assertIn(("stage.save", m1), actions)
        self.assertNotIn(m3, [r["method_id"] for r in rows])                          # the other project's method is not in here
        self.assertTrue(all(r["project_id"] == p1 for r in rows))
        self.assertEqual({r["method_code"] for r in rows if r["method_id"] == m1}, {alice.get("/api/methods/%d" % m1).json()["code"]})
        only = alice.get("/api/methods/%d/audit" % m1).json()
        self.assertTrue(only and all(r["method_id"] == m1 and r["project_id"] == p1 for r in only))
        # the same visibility rules as everything else
        self.assertEqual(login("bob").get("/api/projects/%d/audit" % p1).status_code, 403)
        self.assertEqual(login("bob").get("/api/methods/%d/audit" % m1).status_code, 403)
        self.assertEqual(admin.get("/api/projects/%d/audit" % p1).status_code, 200)
        # global records carry both keys and the whole chain (HMAC over project_id AND method_id) verifies
        glob = admin.get("/api/audit?limit=2000").json()
        self.assertTrue(any(r["action"] == "project.create" and r["project_id"] == p1 and r["method_id"] is None for r in glob))
        self.assertTrue(any(r["action"] == "stage.save" and r["method_id"] == m1 and r["project_id"] == p1 for r in glob))
        self.assertTrue(admin.get("/api/audit/verify").json()["ok"])
        # the method key is covered by the hash: rewriting it is detected
        con = sqlite3.connect(str(config.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            for n in db.TRIGGER_NAMES:
                con.execute("DROP TRIGGER IF EXISTS %s" % n)
            con.execute("UPDATE audit_log SET method_id=? WHERE action='stage.save' AND method_id=?", (m3, m1))
            con.commit()
            res = audit.verify_chain(con)
            self.assertFalse(res["ok"])
            con.execute("UPDATE audit_log SET method_id=? WHERE action='stage.save' AND method_id=?", (m1, m3))
            con.commit()
            self.assertTrue(audit.verify_chain(con)["ok"])
        finally:
            con.close()
            db.init_db()                                                              # puts the triggers back


# ====================================================================== methods
class TestMethods(unittest.TestCase):
    def test_URS101_method_creation_requires_project_membership_and_author_role(self):
        alice, bob, carol, rita, vic, admin = (login(n) for n in ("alice", "bob", "carol", "rita", "vic", "admin"))
        pid = new_project(alice, "C1", members=[("carol", "viewer"), ("rita", "member"), ("vic", "member"), ("dora", "member")])
        url = "/api/projects/%d/methods" % pid
        body = {"name": "CD19/CD22 双靶点 CAR 流式检测法", "template_key": "flow", "analyte": "CAR+ %", "matrix": "全血", "intended_use": "放行检测",
                "phase": "I 期", "planned_start": "2026-02-02"}
        self.assertEqual(bob.post(url, json=body).status_code, 403)                  # global author, but not in the project
        self.assertEqual(carol.post(url, json=body).status_code, 403)                # global author, but only a project viewer
        self.assertEqual(rita.post(url, json=body).status_code, 403)                 # project member, but not a global author
        self.assertEqual(vic.post(url, json=body).status_code, 403)
        self.assertEqual(admin.post(url, json=body).status_code, 403)                # admin must be in the project too
        self.assertEqual(login("dora").post(url, json=body).status_code, 200)        # author + project member
        r = alice.post(url, json=dict(body, name="owner 创建的方法"))
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["id"]
        d = alice.get("/api/methods/%d" % mid).json()
        self.assertRegex(d["code"], r"^AM-\d{4}-\d{3}$")
        self.assertEqual((d["name"], d["template_key"], d["technique"], d["analyte"], d["matrix"], d["intended_use"], d["phase"], d["planned_start"]),
                         ("owner 创建的方法", "flow", "flow", "CAR+ %", "全血", "放行检测", "I 期", "2026-02-02"))
        self.assertEqual((d["method_version"], d["lifecycle"], d["status"], d["template_version"]), ("V0.1", "development", "active", "1.1"))
        self.assertEqual(d["project"]["id"], pid)
        self.assertEqual(sorted(d["project"]), ["code", "id", "name", "status"])
        self.assertEqual(sorted(d["my_roles"]), ["author", "owner"])                  # the creator leads the new method
        self.assertEqual(d["my_project_roles"], ["owner"])
        self.assertEqual(len(d["stages"]), 9)
        # the AM sequence is global (across projects)
        pid2 = new_project(alice, "C2")
        d2 = alice.get("/api/methods/%d" % new_method(alice, pid2, "第二项目的方法")).json()
        self.assertEqual(int(d2["code"][-3:]), int(d["code"][-3:]) + 1)
        # the second project's own listing
        self.assertEqual([m["name"] for m in alice.get("/api/projects/%d/methods" % pid2).json()], ["第二项目的方法"])
        # validation
        for bad in ({}, {"name": ""}, {"name": 5}, {"name": "x", "template_key": "nope"}, {"name": "x", "template_key": ["flow"]},
                    {"name": "x", "planned_start": "garbage"}, {"name": "x" * 300}, {"name": "x", "members": "abc"},
                    {"name": "x", "method_version": ["V"]}):
            self.assertEqual(alice.post(url, json=bad).status_code, 400, bad)
        self.assertEqual(alice.post("/api/projects/99999/methods", json=body).status_code, 403)   # unknown project: not a member of anything
        self.assertEqual(admin.post("/api/projects/99999/methods", json=body).status_code, 404)
        # `technique` is accepted as an alias of `template_key`; the default template is the generic one
        self.assertEqual(alice.get("/api/methods/%d" % alice.post(url, json={"name": "alias", "technique": "hplc"}).json()["id"]).json()["template_key"], "hplc")
        self.assertEqual(alice.get("/api/methods/%d" % alice.post(url, json={"name": "default"}).json()["id"]).json()["template_key"], "generic")
        # a non-active project takes no new methods
        self.assertEqual(alice.patch("/api/projects/%d" % pid, json={"status": "paused"}).status_code, 200)
        self.assertEqual(alice.post(url, json=body).status_code, 409)

    def test_URS102_view_is_inherited_from_the_project_but_edit_and_sign_are_not(self):
        a, mid, ids = make_project(team=["rita", "quinn", "rob", "carol", "vic"])      # carol / vic: project members, NOT on the method team
        carol, vic, bob, rita = login("carol"), login("vic"), login("bob"), login("rita")
        base = "/api/methods/%d" % mid
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        self.assertEqual(a.post(base + "/stages/atp/submit", json={}).status_code, 200)       # atp is now waiting for review
        exp = a.get(base + "/experiments").json()[0]
        for c in (carol, vic):                                                                # any project role may READ
            self.assertEqual(c.get(base).status_code, 200)
            self.assertEqual(c.get(base + "/stages/atp").status_code, 200)
            self.assertEqual(c.get(base + "/stages/atp/checks").status_code, 200)
            self.assertEqual(c.get(base + "/experiments").status_code, 200)
            self.assertEqual(c.get("/api/experiments/%d" % exp["id"]).status_code, 200)
            self.assertEqual(c.get(base + "/audit").status_code, 200)
            self.assertEqual(c.get(base + "/kb").status_code, 200)
            self.assertEqual(c.get(base + "/docs").status_code, 200)
            self.assertEqual(c.get(base + "/export").status_code, 200)
            self.assertIn(mid, [m["id"] for m in c.get("/api/methods").json()])
            self.assertIn(mid, [m["id"] for m in c.get("/api/projects/%d/methods" % project_id_of(a, mid)).json()])
            self.assertIn(mid, [m["id"] for m in c.get("/api/dashboard").json()["methods"]])
            d = c.get(base).json()
            self.assertEqual(d["my_roles"], [])
            self.assertEqual(d["my_project_roles"], ["member"] if c is carol else ["member"])
            self.assertFalse(d["permissions"]["can_edit_content"] or d["permissions"]["can_manage_members"] or d["permissions"]["can_change_lifecycle"])
        # ... but never edit, submit, upload, sign, generate, change the team or the lifecycle
        st = a.get(base + "/stages/charter").json()
        for c in (carol, vic):
            self.assertEqual(c.put(base + "/stages/tech", json={"version": 1, "sections": {"decision": "x"}}).status_code, 403)
            self.assertEqual(c.post(base + "/stages/tech/submit", json={}).status_code, 403)
            self.assertEqual(c.post(base + "/experiments", json={"title": "z"}).status_code, 403)
            self.assertEqual(c.put("/api/experiments/%d" % exp["id"], json={"version": 1, "conclusion": "x"}).status_code, 403)
            self.assertEqual(c.post(base + "/attachments", params={"filename": "a.txt"}, content=b"x").status_code, 403)
            self.assertEqual(c.post(base + "/docs", json={"kind": "plan"}).status_code, 403)
            self.assertEqual(c.put(base + "/members", json={"members": mm(("carol", "owner"))}).status_code, 403)
            self.assertEqual(c.patch(base, json={"phase": "x"}).status_code, 403)
            self.assertEqual(c.post(base + "/lifecycle", json={"lifecycle": "validation", "reason": "r", "password": PW}).status_code, 403)
            self.assertEqual(c.post(base + "/stages/charter/reopen", json={"reason": "r", "password": PW}).status_code, 403)
            self.assertEqual(c.post(base + "/lessons", json={"title": "t", "body": "b"}).status_code, 403)
        s = sign(carol, mid, "atp")
        self.assertEqual(s.status_code, 403, s.text)                                          # a project member cannot sign a gate of the method
        self.assertEqual(sign(vic, mid, "atp").status_code, 403)
        self.assertEqual(carol.get(base + "/stages/atp").json()["can_sign_as"], None)
        self.assertEqual(a.get(base + "/stages/atp").json()["reviews"], [])
        self.assertEqual(sign(rita, mid, "atp").status_code, 200)                              # the method's own reviewer can
        # outsiders see nothing at all
        self.assertEqual(bob.get(base).status_code, 403)
        self.assertEqual(bob.get(base + "/stages/atp").status_code, 403)
        self.assertEqual(bob.get(base + "/export").status_code, 403)
        self.assertNotIn(mid, [m["id"] for m in bob.get("/api/methods").json()])
        self.assertNotIn(mid, [m["id"] for m in bob.get("/api/dashboard").json()["methods"]])
        self.assertEqual(login("admin").get(base).status_code, 200)

    def test_URS103_method_team_members_must_belong_to_the_project(self):
        alice, carol, rita = login("alice"), login("carol"), login("rita")
        pid = new_project(alice, "TM", members=[("carol", "member"), ("rita", "member"), ("quinn", "member")])
        url = "/api/projects/%d/methods" % pid
        # creation: a non-project member (bob), also as reviewer / approver, is refused
        for bad in (mm(("bob", "author")), mm(("pat", "reviewer")), mm(("vic", "viewer"))):
            r = alice.post(url, json={"name": "x", "members": bad})
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("项目", r.json()["error"])
        # admin is exempt (read-only observers, auditors)
        r = alice.post(url, json={"name": "with admin", "members": mm(("admin", "viewer"), ("rita", "reviewer"))})
        self.assertEqual(r.status_code, 200, r.text)
        # carol creates a method: she leads it; alice (project owner) is not on its team but may adjust the team
        mid = new_method(carol, pid, "carol's", members=[("rita", "reviewer")])
        d = carol.get("/api/methods/%d" % mid).json()
        self.assertEqual(sorted(d["my_roles"]), ["author", "owner"])
        murl = "/api/methods/%d/members" % mid
        base = mm(("carol", "owner"), ("carol", "author"), ("rita", "reviewer"))
        self.assertEqual(alice.get("/api/methods/%d" % mid).json()["my_roles"], [])
        self.assertEqual(alice.put(murl, json={"members": base + mm(("bob", "author"))}).status_code, 400)       # bob is not in the project
        self.assertEqual(alice.put(murl, json={"members": base + mm(("quinn", "approver"))}).status_code, 200)    # project owner adjusts
        self.assertEqual(alice.patch("/api/methods/%d" % mid, json={"phase": "x"}).status_code, 403)             # ... but does not edit the method
        self.assertEqual(alice.put("/api/methods/%d/stages/charter" % mid, json={"version": 1, "sections": {"background": "x"}}).status_code, 403)
        self.assertEqual(rita.put(murl, json={"members": base}).status_code, 403)                                # a reviewer does not manage the team
        self.assertEqual(carol.put(murl, json={"members": base}).status_code, 200)                              # the method owner does
        # the list REPLACES the team and must keep a method owner
        self.assertEqual(carol.put(murl, json={"members": mm(("rita", "reviewer"))}).status_code, 400)
        self.assertEqual(alice.put(murl, json={"members": mm(("rita", "reviewer"), ("quinn", "approver"))}).status_code, 400)
        # a project member who is on a method team cannot be removed from the project
        self.assertEqual(alice.put("/api/projects/%d/members" % pid, json={"members": pm(("alice", "owner"))}).status_code, 409)

    def test_URS104_clone_a_method_into_the_same_or_another_project(self):
        config.override("enforce_stage_order", False); self.addCleanup(config.override, "enforce_stage_order", True)
        a, mid, ids = make_project()
        pid = project_id_of(a, mid)
        base = "/api/methods/%d" % mid
        approve_stage(mid, "charter", a)                                                # a signed / completed source must not leak signatures
        ver = a.get(base + "/stages/risk").json()["version"]
        rows = a.get(base + "/stages/risk").json()["data"]["sections"]["fmea"]
        self.assertEqual(a.put(base + "/stages/risk", json={"version": ver, "sections": {"fmea": rows[:3]},
                                                            "checklist": {"r1": {"status": "done", "note": "n"}}}).status_code, 200)
        r = a.post(base + "/clone", json={})
        self.assertEqual(r.status_code, 200, r.text)
        c1 = r.json()["id"]
        d1 = a.get("/api/methods/%d" % c1).json()
        src = a.get(base).json()
        self.assertEqual((d1["project_id"], d1["name"], d1["template_key"], d1["analyte"], d1["matrix"]), (pid, src["name"] + "（副本）", "flow", src["analyte"], src["matrix"]))
        self.assertNotEqual(d1["code"], src["code"])
        self.assertEqual((d1["status"], d1["lifecycle"], d1["method_version"]), ("active", "development", "V0.1"))
        self.assertEqual({(m["username"], m["role"]) for m in d1["members"]}, {("alice", "owner"), ("alice", "author")})   # only the creator, no signers
        self.assertEqual([s["status"] for s in d1["stages"]], ["not_started"] * 9)
        self.assertEqual(d1["bad_signatures"], [])
        charter = a.get("/api/methods/%d/stages/charter" % c1).json()
        self.assertEqual(charter["reviews"], [])
        self.assertTrue(all(v["status"] == "todo" for v in charter["data"]["checklist"].values()))
        risk = a.get("/api/methods/%d/stages/risk" % c1).json()
        self.assertEqual(len(risk["data"]["sections"]["fmea"]), 3)                      # the content is copied
        self.assertTrue(all(v["status"] == "todo" for v in risk["data"]["checklist"].values()))   # the checklist starts fresh
        self.assertEqual(len(a.get("/api/methods/%d/experiments" % c1).json()), len(a.get(base + "/experiments").json()))
        self.assertTrue(any(x["action"] == "method.clone" and x["details"]["from"] == src["code"] for x in a.get("/api/methods/%d/audit" % c1).json()))
        # explicit title; another project of which alice is a member
        carol = login("carol")
        pidb = new_project(carol, "目标项目", members=[("alice", "member")])
        r = a.post(base + "/clone", json={"title": "克隆到别的项目", "project_id": pidb})
        self.assertEqual(r.status_code, 200, r.text)
        d2 = a.get("/api/methods/%d" % r.json()["id"]).json()
        self.assertEqual((d2["project_id"], d2["name"], d2["project"]["id"]), (pidb, "克隆到别的项目", pidb))
        self.assertEqual(carol.get("/api/methods/%d" % d2["id"]).status_code, 200)       # the target project's owner can read it
        self.assertEqual(carol.put("/api/methods/%d/stages/charter" % d2["id"], json={"version": 1, "sections": {"background": "x"}}).status_code, 403)
        # the target must accept new methods from the caller, exactly like a normal creation
        pidv = new_project(carol, "只读成员", members=[("alice", "viewer")])
        pidn = new_project(carol, "无关项目")
        pidp = new_project(carol, "暂停项目", members=[("alice", "member")])
        carol.patch("/api/projects/%d" % pidp, json={"status": "paused"})
        for target, code in ((pidv, 403), (pidn, 403), (pidp, 409), (99999, 404)):
            self.assertEqual(a.post(base + "/clone", json={"project_id": target}).status_code, code, target)
        # the source must be readable; bad input
        self.assertEqual(login("bob").post(base + "/clone", json={}).status_code, 403)
        self.assertEqual(login("rita").post(base + "/clone", json={}).status_code, 403)           # a global reviewer cannot create methods
        for bad in ({"title": 5}, {"project_id": "x"}, {"project_id": True}, {"title": "x" * 400}):
            self.assertEqual(a.post(base + "/clone", json=bad).status_code, 400, bad)
        # a project member without a seat in the source method may clone it (view is inherited)
        dora = login("dora")
        self.assertEqual(dora.post(base + "/clone", json={"title": "dora 的副本"}).status_code, 200)

    def test_URS105_lifecycle_change_is_audited_and_needs_reason_and_password(self):
        a, mid, ids = make_project()
        base = "/api/methods/%d" % mid
        self.assertEqual((a.get(base).json()["lifecycle"], a.get(base).json()["lifecycle_label"]), ("development", "开发"))
        body = {"lifecycle": "validation", "reason": "开发报告已批准，转入验证", "password": PW}
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, reason="")).status_code, 400)
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, reason="   ")).status_code, 400)
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, password="wrong-pass-9")).status_code, 403)
        self.assertEqual(a.post(base + "/lifecycle", json={"lifecycle": "validation", "reason": "r"}).status_code, 403)    # no password
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, lifecycle="bogus")).status_code, 400)
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, lifecycle="development")).status_code, 400)          # unchanged
        self.assertEqual(a.get(base).json()["lifecycle"], "development")
        # only the method owner / approver; not an editor-only, reviewer, project member or outsider
        for who, code in (("rita", 403), ("carol", 403), ("bob", 403), ("vic", 403)):
            self.assertEqual(login(who).post(base + "/lifecycle", json=body).status_code, code, who)
        self.assertEqual(a.post(base + "/lifecycle", json=body).status_code, 200)
        d = a.get(base).json()
        self.assertEqual((d["lifecycle"], d["lifecycle_label"]), ("validation", "验证"))
        row = [x for x in a.get(base + "/audit").json() if x["action"] == "method.lifecycle"]
        self.assertEqual(len(row), 1)
        self.assertEqual((row[0]["details"], row[0]["reason"], row[0]["username"]), ({"from": "development", "to": "validation"}, body["reason"], "alice"))
        self.assertEqual((row[0]["method_id"], row[0]["project_id"]), (mid, project_id_of(a, mid)))
        # the approver may as well
        self.assertEqual(login("quinn").post(base + "/lifecycle", json=dict(body, lifecycle="transfer", reason="验证完成")).status_code, 200)
        self.assertEqual(a.get(base).json()["lifecycle"], "transfer")
        # it is not an ordinary field
        self.assertEqual(a.patch(base, json={"lifecycle": "routine"}).status_code, 400)
        self.assertEqual(a.patch(base, json={"lifecycle": "transfer", "phase": "x"}).status_code, 200)       # unchanged value: ignored
        # allowed in every development status (a completed development is exactly when a method moves on)
        r = a.patch(base, json={"status": "completed"})
        self.assertEqual(r.status_code, 422, r.text)                                   # stages are still open
        self.assertEqual(a.patch(base, json={"status": "archived"}).status_code, 200)
        self.assertEqual(a.post(base + "/lifecycle", json=dict(body, lifecycle="retired", reason="停用")).status_code, 200)
        self.assertEqual([m["id"] for m in a.get("/api/methods?lifecycle=retired").json() if m["id"] == mid], [mid])
        self.assertEqual([m["id"] for m in a.get("/api/methods?lifecycle=routine").json() if m["id"] == mid], [])
        self.assertTrue(login("admin").get("/api/audit/verify").json()["ok"])

    def test_URS107_dashboard_and_method_list_shapes_and_filters(self):
        a, mid, ids = make_project(title="Shape 流式", team=["rita", "quinn", "rob", "carol"])
        pid = project_id_of(a, mid)
        rita = login("rita")
        pcode = a.get("/api/projects/%d" % pid).json()["code"]
        mcode = a.get("/api/methods/%d" % mid).json()["code"]
        approve_stage(mid, "charter", a)
        fill_required(a, mid, "atp")
        self.assertEqual(a.post("/api/methods/%d/stages/atp/submit" % mid, json={}).status_code, 200)
        # ---- dashboard
        d = a.get("/api/dashboard").json()
        self.assertEqual(sorted(d), ["methods", "my_experiments", "my_stages", "projects", "to_review"])
        pr = next(p for p in d["projects"] if p["id"] == pid)
        self.assertGreaterEqual(set(pr), {"id", "code", "name", "product", "status", "my_roles", "method_count", "progress", "overdue", "stale"})
        self.assertEqual((pr["code"], pr["product"], pr["status"], pr["my_roles"], pr["method_count"]), (pcode, "CAR-T", "active", ["owner"], 1))
        self.assertTrue(0 < pr["progress"] <= 100)
        mt = next(m for m in d["methods"] if m["id"] == mid)
        self.assertGreaterEqual(set(mt), {"id", "code", "name", "project_id", "project_code", "project_name", "technique", "lifecycle", "status", "progress",
                                          "current_stage", "overdue", "stale", "my_roles"})
        self.assertEqual((mt["code"], mt["name"], mt["project_id"], mt["project_code"], mt["project_name"], mt["technique"], mt["lifecycle"], mt["status"]),
                         (mcode, "Shape 流式", pid, pcode, "项目-Shape 流式", "flow", "development", "active"))
        self.assertEqual(sorted(mt["my_roles"]), ["author", "owner"])
        self.assertEqual(sorted(mt["current_stage"]), ["key", "status", "title"])
        self.assertEqual(mt["current_stage"]["key"], "atp")
        ms = next(s for s in d["my_stages"] if s["stage_key"] == "atp")
        self.assertEqual((ms["method_id"], ms["method_code"], ms["method"], ms["project_code"], ms["status"]), (mid, mcode, "Shape 流式", pcode, "in_review"))
        self.assertGreaterEqual(set(ms), {"method_id", "method_code", "method", "project_code", "stage_key", "stage", "status", "status_label", "planned_end", "overdue"})
        tr = next(t for t in rita.get("/api/dashboard").json()["to_review"] if t["stage_key"] == "atp")
        self.assertEqual((tr["method_id"], tr["method_code"], tr["method"], tr["project_code"], tr["role"], tr["role_label"]),
                         (mid, mcode, "Shape 流式", pcode, "reviewer", "复核人"))
        with db.tx() as conn:       # experiments appear on the dashboard only once the plan is approved: set that state directly
            conn.execute("UPDATE stages SET status='approved' WHERE method_id=? AND key='plan'", (mid,))
        ex = a.get("/api/dashboard").json()["my_experiments"][0]
        with db.tx() as conn:
            conn.execute("UPDATE stages SET status='not_started' WHERE method_id=? AND key='plan'", (mid,))   # restore
        self.assertGreaterEqual(set(ex), {"id", "method_id", "code", "method_code", "method", "project_code", "title", "status", "status_label", "planned_end", "overdue"})
        # a project member without a seat sees the method but no tasks
        carol = login("carol").get("/api/dashboard").json()
        self.assertIn(mid, [m["id"] for m in carol["methods"]])
        self.assertEqual([t for t in carol["to_review"] if t["method_id"] == mid], [])
        self.assertEqual(next(m for m in carol["methods"] if m["id"] == mid)["my_roles"], [])
        # ---- GET /api/methods and its filters
        pid2 = new_project(a, "另一个项目")
        m2 = new_method(a, pid2, "HPLC 纯度法", template="hplc", analyte="主峰纯度")
        lst = a.get("/api/methods").json()
        self.assertEqual({mid, m2} - {m["id"] for m in lst}, set())
        row = next(m for m in lst if m["id"] == m2)
        self.assertGreaterEqual(set(row), {"id", "code", "name", "project_id", "project_code", "project_name", "technique", "technique_label", "template_version",
                                           "analyte", "matrix", "intended_use", "phase", "method_version", "lifecycle", "lifecycle_label", "status", "status_label",
                                           "planned_start", "planned_end", "owner_id", "owner_name", "my_roles", "my_project_roles", "progress", "current_stage",
                                           "overdue", "stale", "updated_at"})

        def ids_(qs):
            return {m["id"] for m in a.get("/api/methods" + qs).json()}
        self.assertEqual(ids_("?project_id=%d" % pid2), {m2})
        self.assertEqual(ids_("?technique=hplc") & {mid, m2}, {m2})
        self.assertEqual(ids_("?q=纯度") & {mid, m2}, {m2})
        self.assertEqual(ids_("?q=" + mcode) & {mid, m2}, {mid})
        self.assertEqual(ids_("?q=" + pcode) & {mid, m2}, {mid})                       # the project's code finds its methods
        self.assertEqual(ids_("?q=另一个项目") & {mid, m2}, {m2})                       # ... and its name
        self.assertEqual(ids_("?q=shape") & {mid, m2}, {mid})                          # case-insensitive
        self.assertEqual(ids_("?status=archived") & {mid, m2}, set())
        self.assertEqual(ids_("?status=active") & {mid, m2}, {mid, m2})
        self.assertEqual(ids_("?lifecycle=development") & {mid, m2}, {mid, m2})
        self.assertEqual(ids_("?lifecycle=retired") & {mid, m2}, set())
        self.assertEqual(ids_("?project_id=%d&technique=hplc&status=active&lifecycle=development&q=HPLC" % pid2), {m2})
        self.assertEqual(ids_("?project_id=%d&technique=flow" % pid2), set())
        # ---- the project's method table
        rows = a.get("/api/projects/%d/methods" % pid).json()
        self.assertEqual([r["id"] for r in rows], [mid])
        self.assertTrue(rows[0]["signatures_ok"])
        self.assertEqual(rows[0]["current_stage"]["key"], "atp")
        # ---- project row counts
        self.assertEqual(next(p for p in a.get("/api/projects").json() if p["id"] == pid2)["method_count"], 1)

    def test_URS107_method_detail_carries_project_and_permissions(self):
        a, mid, ids = make_project()
        d = a.get("/api/methods/%d" % mid).json()
        self.assertGreaterEqual(set(d), {"id", "code", "name", "project_id", "project", "technique", "technique_label", "template_key", "template_version", "analyte",
                                         "matrix", "intended_use", "phase", "method_version", "lifecycle", "lifecycle_label", "status", "status_label", "planned_start",
                                         "planned_end", "owner_id", "owner_name", "meta", "summary", "stages", "members", "my_roles", "my_project_roles",
                                         "permissions", "signatures_ok", "bad_signatures"})
        self.assertEqual(sorted(d["permissions"]), ["can_change_lifecycle", "can_edit_content", "can_edit_info", "can_generate_docs", "can_manage_members"])
        self.assertTrue(all(d["permissions"].values()))
        self.assertEqual(sorted(d["summary"]), ["current_stage", "overdue", "progress", "stale"])
        self.assertGreaterEqual(set(d["members"][0]), {"user_id", "role", "role_label", "display_name", "username", "active"})
        s = a.get("/api/methods/%d/stages/charter" % mid).json()
        self.assertEqual(s["method"]["id"], mid)
        self.assertEqual(s["project"]["id"], d["project_id"])
        self.assertEqual(s["method_id"], mid)
        rita = login("rita").get("/api/methods/%d" % mid).json()
        self.assertEqual(rita["permissions"], {"can_edit_info": False, "can_manage_members": False, "can_change_lifecycle": False,
                                               "can_generate_docs": True, "can_edit_content": False})


# ====================================================================== templates, seeds, warnings, KB
class TestTemplatesInMethods(unittest.TestCase):
    def test_URS108_template_seeds_reach_new_methods(self):
        """E1: every table starts with its `seed_rows`, every text with its `default`; FMEA / experiments / SST seeds as before."""
        a = login("alice")
        pid = new_project(a, "Seeds")
        r = a.get("/api/templates")
        self.assertEqual(r.status_code, 200)
        listing = r.json()
        self.assertEqual([t["key"] for t in listing], ["flow", "hplc", "bioassay", "qpcr", "elisa", "cell_based", "generic"])
        for t in listing:
            self.assertTrue(t["changelog"] and t["stats"] and t["version"] == "1.1", t["key"])
        for tk in [t["key"] for t in listing]:
            tpl = templates_data.build_template(tk)
            mid = new_method(a, pid, "seed-" + tk, template=tk)
            n_rows = n_text = 0
            for sd in tpl["stages"]:
                st = a.get("/api/methods/%d/stages/%s" % (mid, sd["key"])).json()
                secs = st["data"]["sections"]
                for sec in sd["sections"]:
                    if sec["type"] == "table" and sec.get("seed_rows"):
                        self.assertEqual(secs.get(sec["key"]), sec["seed_rows"], (tk, sd["key"], sec["key"]))
                        n_rows += len(sec["seed_rows"])
                    if sec["type"] == "text" and sec.get("default"):
                        self.assertEqual(secs.get(sec["key"]), sec["default"], (tk, sd["key"], sec["key"]))
                        n_text += 1
            self.assertGreater(n_rows, 60, tk)
            self.assertEqual(n_text, 2, tk)
            fmea = a.get("/api/methods/%d/stages/risk" % mid).json()["data"]["sections"]["fmea"]
            self.assertEqual(len(fmea), len(tpl["seed"]["fmea"]))
            self.assertGreaterEqual(len(fmea), 10)
            exps = a.get("/api/methods/%d/experiments" % mid).json()
            self.assertEqual([e["code"] for e in exps], [e["code"] for e in tpl["seed"]["experiments"]])
            self.assertGreaterEqual(len(exps), 8)
            self.assertTrue(all(templates_data.SAMPLE_TAG in e["acceptance"] for e in exps))
            plan = a.get("/api/methods/%d/stages/plan" % mid).json()["data"]["sections"]
            self.assertEqual(len(plan["phases"]), len(exps))
            self.assertEqual(len(a.get("/api/methods/%d/stages/control" % mid).json()["data"]["sections"]["sst"]), len(tpl["seed"]["sst"]))
            self.assertEqual(len(a.get("/api/methods/%d/stages/atp" % mid).json()["data"]["sections"]["criteria"]), len(tpl["seed"]["atp_rows"]))

    def test_URS108_unconfirmed_example_values_warn_but_do_not_block(self):
        config.override("enforce_stage_order", False); self.addCleanup(config.override, "enforce_stage_order", True)
        """E2: plan / report gates warn while '示例值，须按ATP确认' is still in stage data or in experiment acceptance criteria."""
        a, mid, ids = make_project()
        base = "/api/methods/%d" % mid
        mark = "示例值"
        plan = a.get(base + "/stages/plan/checks").json()
        warn = [w for w in plan["warns"] if mark in w]
        self.assertEqual(len(warn), 1, plan["warns"])
        n_tpl = len(templates_data.build_template("flow")["seed"]["experiments"])
        self.assertIn("实验接受标准 %d 个" % n_tpl, warn[0])
        self.assertRegex(warn[0], r"开发方案与实验设计 \d+ 处")
        self.assertFalse([b for b in plan["blocks"] if mark in b and "实验" not in b])          # sections only warn; unconfirmed experiment criteria block (they freeze at approval)
        self.assertTrue([w for w in a.get(base + "/stages/atp/checks").json()["warns"] if mark in w])     # every step warns (V0.3)
        # confirm the plan table: only the experiments still carry the tag
        st = a.get(base + "/stages/plan").json()
        rows = tw._scrub(st["data"]["sections"]["phases"])
        self.assertEqual(a.put(base + "/stages/plan", json={"version": st["version"], "sections": {"phases": rows}}).status_code, 200)
        warn = [w for w in a.get(base + "/stages/plan/checks").json()["warns"] if mark in w]
        self.assertEqual(len(warn), 1)
        self.assertIn("实验接受标准 %d 个" % n_tpl, warn[0])
        self.assertNotIn("开发方案与实验设计", warn[0])
        # confirm the experiments as well (bulk "confirm example values"): none of them is mentioned any more
        ids_ = [e["id"] for e in a.get(base + "/experiments").json()]
        r = a.post(base + "/experiments/bulk", json={"ids": ids_, "action": "confirm_examples"})
        self.assertEqual(len(r.json()["done"]), len(ids_), r.text)
        warn = [w for w in a.get(base + "/stages/plan/checks").json()["warns"] if mark in w]
        self.assertIn("实验接受标准 0 个", warn[0])                               # (the covered ATP step still has its own marks)
        # the report stage warns about its own unconfirmed text, and the submission check does not block because of it
        rep = a.get(base + "/stages/report").json()
        self.assertEqual(a.put(base + "/stages/report", json={"version": rep["version"], "sections": {"summary": "草稿：" + mark}}).status_code, 200)
        chk = a.get(base + "/stages/report/checks").json()
        self.assertEqual(len([w for w in chk["warns"] if mark in w]), 1)
        self.assertFalse([b for b in chk["blocks"] if mark in b])
        # a cancelled experiment does not count
        a2, mid2, _ = make_project(title="warn2")
        first = a2.get("/api/methods/%d/experiments" % mid2).json()[0]
        self.assertEqual(a2.post("/api/experiments/%d/status" % first["id"], json={"status": "cancelled", "reason": "不做"}).status_code, 200)
        warn2 = [w for w in a2.get("/api/methods/%d/stages/plan/checks" % mid2).json()["warns"] if mark in w][0]
        self.assertIn("实验接受标准 %d 个" % (n_tpl - 1), warn2)


class TestKnowledgeBaseSync(unittest.TestCase):
    def test_URS109_kb_sync_adds_missing_builtin_items_and_never_overwrites(self):
        admin, alice = login("admin"), login("alice")
        total = len(kb_seed.SEED)
        self.assertEqual(raw("SELECT COUNT(*) FROM kb_items WHERE builtin=1")[0][0], total)
        titles = [i["title"] for i in kb_seed.SEED]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertGreaterEqual(total, 100)
        # ordinary users cannot sync; an up-to-date database changes nothing
        self.assertEqual(alice.post("/api/admin/kb-sync").status_code, 403)
        r = admin.post("/api/admin/kb-sync")
        self.assertEqual((r.status_code, r.json()), (200, {"added": 0, "existing": total, "total": total}))
        # a database made by an older release: some built-in items are missing (here: deleted from the table)
        lost = titles[:3]
        for t in lost:
            raw("DELETE FROM kb_items WHERE title=?", (t,))
        # ... one built-in item was deactivated by an administrator, one user item re-uses another built-in title and was edited
        gone_title, mine_title = titles[10], titles[11]
        gone_id = raw("SELECT id FROM kb_items WHERE title=?", (gone_title,))[0][0]
        self.assertEqual(admin.delete("/api/kb/%d" % gone_id).status_code, 200)
        raw("UPDATE kb_items SET body='我改过的内容', builtin=0, created_by=? WHERE title=?", (IDS["alice"], mine_title))
        n_before = raw("SELECT COUNT(*) FROM kb_items")[0][0]
        r = admin.post("/api/admin/kb-sync")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"added": 3, "existing": total - 3, "total": total})
        self.assertEqual(raw("SELECT COUNT(*) FROM kb_items")[0][0], n_before + 3)
        for t in lost:
            row = raw("SELECT builtin, active FROM kb_items WHERE title=?", (t,))
            self.assertEqual([(x["builtin"], x["active"]) for x in row], [(1, 1)])
        row = raw("SELECT body, active FROM kb_items WHERE title=?", (mine_title,))
        self.assertEqual([(x["body"], x["active"]) for x in row], [("我改过的内容", 1)])                  # an edited item is left alone
        row = raw("SELECT active FROM kb_items WHERE title=?", (gone_title,))
        self.assertEqual([x["active"] for x in row], [0])                                                # a deactivated item stays deactivated (no duplicate)
        # idempotent
        self.assertEqual(admin.post("/api/admin/kb-sync").json()["added"], 0)
        self.assertEqual(raw("SELECT COUNT(*) FROM kb_items")[0][0], n_before + 3)
        # user-created items are never matched / touched
        self.assertEqual(alice.post("/api/kb", json={"title": "我自己的经验", "body": "b"}).status_code, 200)
        self.assertEqual(admin.post("/api/admin/kb-sync").json()["added"], 0)
        # the start-up seeding does the same thing (and audits what it added)
        raw("DELETE FROM kb_items WHERE title=?", (titles[20],))
        res = main._seed_kb()
        self.assertEqual(res["added"], 1)
        self.assertEqual(main._seed_kb()["added"], 0)
        acts = [x for x in admin.get("/api/audit?limit=2000").json() if x["action"] == "kb.sync"]
        self.assertTrue(any(x["details"].get("added") == 3 and x["username"] == "admin" for x in acts))
        self.assertTrue(any(x["details"].get("added") == 1 and x["username"] == "system" for x in acts))
        self.assertTrue(admin.get("/api/audit/verify").json()["ok"])
        # the new items are served: one of the new writing guides is visible to a flow method
        a, mid, _ = make_project()
        items = a.get("/api/methods/%d/kb?stage=charter" % mid).json()
        self.assertTrue(any("写作指南" in i["tags"] for i in items))


# ====================================================================== old databases
V1_DDL = """
CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, roles TEXT NOT NULL DEFAULT '[]',
  pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, failed_count INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
  must_change INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
  last_seen TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE projects(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, title TEXT NOT NULL, product TEXT, attribute TEXT,
  technique TEXT NOT NULL, template_key TEXT NOT NULL, template_version TEXT, intended_use TEXT, phase TEXT,
  status TEXT NOT NULL DEFAULT 'active', planned_start TEXT, planned_end TEXT, owner_id INTEGER REFERENCES users(id),
  created_by INTEGER, created_at TEXT, updated_at TEXT, meta TEXT NOT NULL DEFAULT '{}');
CREATE TABLE project_members(project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id), role TEXT NOT NULL, PRIMARY KEY(project_id, user_id, role));
CREATE TABLE stages(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  key TEXT NOT NULL, ord INTEGER NOT NULL, def TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_started',
  revision INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, stale INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}', editors TEXT NOT NULL DEFAULT '[]', planned_start TEXT, planned_end TEXT,
  actual_start TEXT, actual_end TEXT, submitted_at TEXT, updated_at TEXT, UNIQUE(project_id, key));
CREATE TABLE stage_revisions(id INTEGER PRIMARY KEY, stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL, data TEXT NOT NULL, data_hash TEXT NOT NULL, created_by INTEGER, created_at TEXT, reason TEXT);
CREATE TABLE reviews(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL, role TEXT NOT NULL, user_id INTEGER NOT NULL, decision TEXT NOT NULL, comment TEXT,
  signed_at TEXT NOT NULL, data_hash TEXT NOT NULL, meaning TEXT);
CREATE TABLE experiments(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stage_key TEXT, code TEXT NOT NULL, title TEXT NOT NULL, objective TEXT, design TEXT, acceptance TEXT,
  planned_start TEXT, planned_end TEXT, actual_start TEXT, actual_end TEXT, status TEXT NOT NULL DEFAULT 'planned',
  owner_id INTEGER, results TEXT NOT NULL DEFAULT '[]', conclusion TEXT, deviations TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT, updated_at TEXT, UNIQUE(project_id, code));
CREATE TABLE attachments(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stage_key TEXT, experiment_id INTEGER, filename TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL,
  description TEXT, uploaded_by INTEGER, uploaded_at TEXT, deleted INTEGER NOT NULL DEFAULT 0, deleted_by INTEGER,
  deleted_at TEXT, delete_reason TEXT);
CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id INTEGER, username TEXT, action TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT, project_id INTEGER, details TEXT NOT NULL DEFAULT '{}', reason TEXT,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE kb_items(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]', techniques TEXT NOT NULL DEFAULT '[]', stages TEXT NOT NULL DEFAULT '[]', source TEXT,
  origin_project_id INTEGER, active INTEGER NOT NULL DEFAULT 1, created_by INTEGER, created_at TEXT, updated_at TEXT);
CREATE TABLE generated_docs(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL, version_label TEXT, status_label TEXT, data_hash TEXT,
  created_by INTEGER, created_at TEXT, summary TEXT);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
"""


def _sdef(key, gate=None):
    return {"key": key, "title": key, "gate": gate, "checklist": [], "sections": [], "requires": []}


class TestOldDatabases(unittest.TestCase):
    """URS-106: a database of the old single-level model is refused with a clear message, and tools/migrate_v1_to_v2.py
    converts it (each old project becomes a method of an automatically created project of the same name)."""

    def _fixture(self, ver):
        """Writes an old-model data directory (user_version `ver` = 1 or 2) and returns its path."""
        tmp = tempfile.mkdtemp(prefix="mf_old%d_" % ver, dir=PTMP)
        con = sqlite3.connect(os.path.join(tmp, "methodflow.db"), isolation_level=None)
        con.row_factory = sqlite3.Row
        con.executescript(V1_DDL)
        if ver == 2:
            for stmt in ("ALTER TABLE stages ADD COLUMN contributors TEXT NOT NULL DEFAULT '[]'",
                         "ALTER TABLE stage_revisions ADD COLUMN hv INTEGER NOT NULL DEFAULT 1",
                         "ALTER TABLE experiments ADD COLUMN added_after_plan INTEGER NOT NULL DEFAULT 0",
                         "ALTER TABLE audit_log ADD COLUMN hv INTEGER NOT NULL DEFAULT 1"):
                con.execute(stmt)
        con.execute("PRAGMA user_version=%d" % ver)
        pwh = auth.hash_password(PW)
        con.execute("INSERT INTO users(id,username,display_name,roles,pw_hash,created_at) VALUES(1,'old','Old','[\"admin\",\"author\"]',?,'2026-01-01T00:00:00Z')", (pwh,))
        con.execute("INSERT INTO users(id,username,display_name,roles,pw_hash,created_at) VALUES(2,'rev','Rev','[\"reviewer\"]',?,'2026-01-01T00:00:00Z')", (pwh,))
        con.execute("INSERT INTO projects(id,code,title,product,attribute,technique,template_key,template_version,intended_use,phase,status,planned_start,planned_end,"
                    "owner_id,created_by,created_at,updated_at,meta) VALUES(1,'MD-2026-001','Old Assay','ProdX','CD19','flow','flow','1.0','QC','II','active',"
                    "'2026-01-01','2026-06-01',1,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','{\"template_label\":\"流式\"}')")
        for u, role in ((1, "owner"), (1, "author"), (2, "reviewer")):
            con.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(1,?,?)", (u, role))
        cdata = {"sections": {"background": "legacy background"}, "checklist": {}}
        pdata = {"sections": {"use": "legacy"}, "checklist": {}}
        gate = {"key": "GP", "name": "GP", "roles": ["reviewer"], "covers": ["charter"] if ver == 2 else []}
        con.execute("INSERT INTO stages(id,project_id,key,ord,def,status,revision,version,data,editors,updated_at) VALUES(1,1,'plan',2,?,'approved',1,3,?,'[1]','2026-01-02T00:00:00Z')",
                    (json.dumps(_sdef("plan", gate)), json.dumps(pdata)))
        con.execute("INSERT INTO experiments(project_id,stage_key,code,title,created_at) VALUES(1,'explore','P0','before','2026-01-02T12:00:00Z')")
        con.execute("INSERT INTO experiments(project_id,stage_key,code,title,created_at) VALUES(1,'explore','P9','after','2026-02-01T00:00:00Z')")
        con.execute("INSERT INTO experiments(project_id,stage_key,code,title,created_at) VALUES(1,'explore','P8','plan row','2026-01-02T00:00:00Z')")
        meta = {"title": "Old Assay", "product": "ProdX", "attribute": "CD19", "intended_use": "QC"}
        if ver == 1:
            h_plan = db.sha256(db.canon({"stage": "plan", "revision": 1, "data": pdata, "covers": {}}))          # the version-1 formula
            con.execute("INSERT INTO stage_revisions(stage_id,revision,data,data_hash,created_by,created_at) VALUES(1,1,?,?,1,'2026-01-02T00:00:00Z')", (json.dumps(pdata), h_plan))
        else:
            cdata_s = json.dumps(cdata)
            con.execute("INSERT INTO stages(id,project_id,key,ord,def,status,revision,version,data,editors,contributors,updated_at) VALUES(2,1,'charter',1,?,'completed',1,2,?,'[1]','[1]','2026-01-01T12:00:00Z')",
                        (json.dumps(_sdef("charter")), cdata_s))
            con.execute("UPDATE stages SET contributors='[1]' WHERE id=1")
            empty_x = {"exps": [], "atts": []}
            h_ch = db.sha256(db.canon({"stage": "charter", "revision": 1, "data": cdata, "covers": {}, "hv": 2, "x": empty_x, "project": meta}))
            exps = [{"code": c, "title": t, "objective": "", "design": "", "acceptance": ""} for c, t in (("P0", "before"), ("P8", "plan row"))]
            cov = {"charter": {"rev": 1, "h": db.sha256(cdata_s), "x": db.sha256(db.canon(empty_x))}}
            h_plan = db.sha256(db.canon({"stage": "plan", "revision": 1, "data": pdata, "covers": cov, "hv": 2,
                                         "x": {"exps": exps, "atts": []}, "project": meta}))
            con.execute("INSERT INTO stage_revisions(stage_id,revision,data,data_hash,created_by,created_at,hv) VALUES(2,1,?,?,1,'2026-01-01T12:00:00Z',2)", (json.dumps(cdata), h_ch))
            con.execute("INSERT INTO stage_revisions(stage_id,revision,data,data_hash,created_by,created_at,hv) VALUES(1,1,?,?,1,'2026-01-02T00:00:00Z',2)", (json.dumps(pdata), h_plan))
            con.execute("UPDATE experiments SET added_after_plan=1 WHERE code='P9'")
        con.execute("INSERT INTO reviews(project_id,stage_id,revision,role,user_id,decision,comment,signed_at,data_hash,meaning) VALUES(1,1,1,'reviewer',2,'approve','','2026-01-03T00:00:00Z',?,'m')", (h_plan,))
        prev = audit.GENESIS
        key = None
        if ver == 2:
            key = os.urandom(32)
            with open(os.path.join(tmp, ".audit_key"), "w", encoding="ascii") as f:
                f.write(key.hex())
        for i in range(3):
            body = {"ts": "2026-01-0%dT00:00:00Z" % (i + 1), "user_id": 1, "username": "old", "action": "x%d" % i, "entity_type": None,
                    "entity_id": None, "project_id": 1 if i else None, "details": {}, "reason": None}
            h = audit._chain_hash(ver, key, prev, db.canon(body))
            if ver == 2:
                con.execute("INSERT INTO audit_log(ts,user_id,username,action,project_id,details,prev_hash,hash,hv) VALUES(?,1,'old',?,?,'{}',?,?,2)",
                            (body["ts"], body["action"], body["project_id"], prev, h))
            else:
                con.execute("INSERT INTO audit_log(ts,user_id,username,action,project_id,details,prev_hash,hash) VALUES(?,1,'old',?,?,'{}',?,?)",
                            (body["ts"], body["action"], body["project_id"], prev, h))
            prev = h
        con.close()
        return tmp

    def test_URS106_old_databases_are_refused_with_a_clear_message(self):
        saved = config.DATA
        try:
            for ver in (1, 2):
                tmp = self._fixture(ver)
                config.set_data(tmp)
                with self.assertRaises(db.OldSchemaError) as cm:
                    db.init_db()
                msg = str(cm.exception)
                self.assertIn("migrate_v1_to_v2", msg)
                self.assertIn("备份", msg)
                self.assertIn("user_version=%d" % ver, msg)
                self.assertTrue(isinstance(cm.exception, RuntimeError))
                chk = sqlite3.connect(os.path.join(tmp, "methodflow.db"))
                self.assertEqual(chk.execute("PRAGMA user_version").fetchone()[0], ver)                     # nothing was changed
                self.assertNotIn("methods", {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")})
                self.assertEqual(chk.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 3)
                chk.close()
                if ver == 1:
                    self.assertFalse(os.path.exists(os.path.join(tmp, ".audit_key")))                      # not even a key was created
                # the web application refuses to start on it, too
                auth.reset_limits()
                with self.assertRaises(db.OldSchemaError):
                    with TestClient(main.app):
                        pass
                with self.assertRaises(SystemExit) as se:                 # `python run.py` stops with a readable message instead
                    main.run()
                self.assertEqual(se.exception.code, 4)
            # an unversioned database that already has tables is not 'new' either
            tmp = self._fixture(1)
            c = sqlite3.connect(os.path.join(tmp, "methodflow.db"))
            c.execute("PRAGMA user_version=0")
            c.close()
            config.set_data(tmp)
            with self.assertRaises(db.OldSchemaError):
                db.init_db()
            # a database from a NEWER program stays refused as before
            tmp = tempfile.mkdtemp(dir=PTMP)
            config.set_data(tmp)
            db.init_db()
            c = sqlite3.connect(os.path.join(tmp, "methodflow.db"))
            c.execute("PRAGMA user_version=99")
            c.close()
            with self.assertRaises(RuntimeError) as cm:
                db.init_db()
            self.assertNotIsInstance(cm.exception, db.OldSchemaError)
        finally:
            config.set_data(saved)
            auth.reset_limits()
        # a fresh directory initialises normally and gets the current version
        fresh = tempfile.mkdtemp(dir=PTMP)
        try:
            config.set_data(fresh)
            db.init_db()
            with db.read() as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
                self.assertGreaterEqual({r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                                        {"projects", "project_members", "methods", "method_members", "stages", "experiments", "attachments", "generated_docs", "audit_log"})
                cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)")}
                self.assertGreaterEqual(cols, {"project_id", "method_id", "hv"})
                self.assertIn("method_id", {r[1] for r in conn.execute("PRAGMA table_info(stages)")})
                self.assertIn("format", {r[1] for r in conn.execute("PRAGMA table_info(generated_docs)")})
            db.init_db()                                                                                   # idempotent
        finally:
            config.set_data(saved)

    def _migrate_and_check(self, ver):
        tmp = self._fixture(ver)
        tool = os.path.join(ROOT, "tools", "migrate_v1_to_v2.py")
        port = free_port()
        p = subprocess.run([sys.executable, tool, "--data", tmp, "--yes", "--port", str(port)], capture_output=True)
        out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("转换完成", out)
        backups = [f for f in os.listdir(os.path.join(tmp, "backups")) if f.startswith("premigrate_") and f.endswith(".db")]
        self.assertEqual(len(backups), 1)
        old = sqlite3.connect(os.path.join(tmp, "backups", backups[0]))
        self.assertEqual(old.execute("PRAGMA user_version").fetchone()[0], ver)                           # the original is kept
        old.close()
        # running it again says that there is nothing to do
        p2 = subprocess.run([sys.executable, tool, "--data", tmp, "--yes", "--port", str(port)], capture_output=True)
        self.assertEqual(p2.returncode, 0)
        self.assertIn("无需转换", p2.stdout.decode("utf-8", "replace"))
        saved = config.DATA
        try:
            config.set_data(tmp)
            auth.reset_limits()
            db.init_db()                                                                                   # accepted now (and a no-op)
            with db.read() as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
                proj = conn.execute("SELECT * FROM projects").fetchall()
                self.assertEqual(len(proj), 1)
                self.assertEqual((proj[0]["id"], proj[0]["name"], proj[0]["product"], proj[0]["status"], proj[0]["owner_id"], proj[0]["phase"]),
                                 (1, "Old Assay", "ProdX", "active", 1, "II"))
                self.assertEqual(proj[0]["code"], "PRJ-2026-001")
                m = conn.execute("SELECT * FROM methods").fetchall()
                self.assertEqual(len(m), 1)
                self.assertEqual((m[0]["id"], m[0]["code"], m[0]["project_id"], m[0]["name"], m[0]["analyte"], m[0]["intended_use"], m[0]["template_key"],
                                  m[0]["lifecycle"], m[0]["status"], m[0]["method_version"]),
                                 (1, "AM-2026-001", 1, "Old Assay", "CD19", "QC", "flow", "development", "active", "V0.1"))
                self.assertEqual(json.loads(m[0]["meta"])["legacy_code"], "MD-2026-001")
                self.assertEqual({(r["user_id"], r["role"]) for r in conn.execute("SELECT * FROM project_members")}, {(1, "owner"), (2, "member")})
                self.assertEqual({(r["user_id"], r["role"]) for r in conn.execute("SELECT * FROM method_members")}, {(1, "owner"), (1, "author"), (2, "reviewer")})
                flags = {r["code"]: r["added_after_plan"] for r in conn.execute("SELECT code, added_after_plan FROM experiments")}
                self.assertEqual(flags, {"P0": 0, "P8": 0, "P9": 1})
                self.assertEqual(json.loads(conn.execute("SELECT contributors FROM stages WHERE id=1").fetchone()[0]), [1])
                # signatures made with the old formulas still verify
                ok, bad = workflow.method_signatures(conn, 1)
                self.assertTrue(ok, bad)
                # the audit chain: the old records untouched, one new record at the end
                res = audit.verify_chain(conn, live_anchor=True)
                self.assertTrue(res["ok"], res)
                self.assertEqual(res["count"], 4)
                self.assertEqual([r["hv"] for r in conn.execute("SELECT hv FROM audit_log ORDER BY id")], [ver, ver, ver, 3])
                last = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
                self.assertEqual((last["action"], last["username"]), ("schema.migrate", "system:migrate"))
                self.assertEqual([r["method_id"] for r in conn.execute("SELECT method_id FROM audit_log ORDER BY id")], [None, 1, 1, None])
                self.assertTrue(audit.triggers_present(conn))
                self.assertTrue(audit.verify(conn)["ok"])
            self.assertTrue(os.path.exists(os.path.join(tmp, "audit_head.json")))
            # the application works on it
            c = client()
            self.assertEqual(c.post("/api/login", json={"username": "old", "password": PW}).status_code, 200)
            mt = c.get("/api/methods").json()
            self.assertEqual([(x["code"], x["name"], x["project_code"]) for x in mt], [("AM-2026-001", "Old Assay", "PRJ-2026-001")])
            self.assertEqual([x["name"] for x in c.get("/api/projects").json()], ["Old Assay"])
            d = c.get("/api/methods/1").json()
            self.assertTrue(d["signatures_ok"], d["bad_signatures"])
            st = c.get("/api/methods/1/stages/plan").json()
            self.assertTrue(st["signatures_ok"] and all(r["intact"] for r in st["reviews"]), st["signature_problems"])
            self.assertEqual(len(c.get("/api/projects/1/audit").json()), 2)          # the two old records that carried project_id=1
            self.assertTrue(c.get("/api/audit/verify").json()["ok"])
            self.assertEqual(c.get("/api/dashboard").status_code, 200)
            # the old (hv 1/2) signature formulas keep covering what they covered: a change behind our back is still seen
            con = sqlite3.connect(os.path.join(tmp, "methodflow.db"))
            con.execute("UPDATE stages SET data=? WHERE id=1", (json.dumps({"sections": {"use": "TAMPERED"}, "checklist": {}}),))
            con.commit()
            self.assertFalse(c.get("/api/methods/1").json()["signatures_ok"])
            con.close()
            if ver == 2:
                con = sqlite3.connect(os.path.join(tmp, "methodflow.db"))
                con.execute("UPDATE stages SET data=? WHERE id=1", (json.dumps({"sections": {"use": "legacy"}, "checklist": {}}),))
                con.execute("UPDATE projects SET product='sneaky' WHERE id=1")             # the old signature covered the product
                con.commit()
                self.assertFalse(c.get("/api/methods/1").json()["signatures_ok"])
                con.execute("UPDATE projects SET product='ProdX' WHERE id=1")
                con.commit()
                con.close()
                self.assertTrue(c.get("/api/methods/1").json()["signatures_ok"])
        finally:
            config.set_data(saved)
            auth.reset_limits()

    def test_URS106_migration_tool_converts_a_version_1_database(self):
        self._migrate_and_check(1)

    def test_URS106_migration_tool_converts_a_version_2_database_and_keeps_the_keyed_chain(self):
        self._migrate_and_check(2)

    def test_URS106_migration_tool_refuses_running_servers_and_unknown_databases(self):
        tool = os.path.join(ROOT, "tools", "migrate_v1_to_v2.py")
        tmp = self._fixture(1)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        p = subprocess.run([sys.executable, tool, "--data", tmp, "--yes", "--port", str(port)], capture_output=True)
        s.close()
        self.assertEqual(p.returncode, 3, p.stdout.decode("utf-8", "replace"))
        self.assertEqual(sqlite3.connect(os.path.join(tmp, "methodflow.db")).execute("PRAGMA user_version").fetchone()[0], 1)
        empty = tempfile.mkdtemp(dir=PTMP)
        p = subprocess.run([sys.executable, tool, "--data", empty, "--yes", "--port", str(free_port())], capture_output=True)
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
