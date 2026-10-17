"""Workflow engine: permissions, projects, methods, stages, gates (review & e-signature), experiments,
attachments, progress, dashboard, knowledge-base suggestions, backup.

Data model v2: a *project* is a container (product / pipeline) with a team; a *method* (one analytical method)
belongs to exactly one project and carries the 9-stage development workflow, experiments, attachments,
reviews, audit records and documents.  Everything below that used to be keyed by `project_id` is keyed by
`method_id` now (`mid`).

Permissions
  view a method   = method member  OR  member of its project (any project role)  OR  admin
  edit / sign     = method roles only (owner / author edit, reviewer / approver sign), with every separation-of-duties
                    rule of the single-level model
  project owner   = manages the project team, creates methods, adjusts any method team of the project
  method owner    = edits method info, adjusts the method team (members must be project members; admins excepted)
"""
import datetime as dt
import json
import os
import re
import sqlite3
import uuid

from . import audit, auth, config, db, notifier, stats, templates_data, validate

EDITABLE = ("not_started", "in_progress", "returned")
LOCKED = ("approved", "completed")
FROZEN = ("in_review", "approved", "completed")        # stage content may not change in these states
STATUS_LABELS = {"not_started": "未开始", "in_progress": "进行中", "in_review": "待复核", "returned": "已退回",
                 "approved": "已通过", "completed": "已完成"}
ROLE_LABELS = {"owner": "方法负责人", "author": "开发人员", "reviewer": "复核人", "approver": "批准人(QA)", "viewer": "只读"}
MEMBER_ROLES = list(ROLE_LABELS)                         # method team roles
PROJECT_ROLE_LABELS = {"owner": "项目负责人", "member": "项目成员", "viewer": "只读"}
PROJECT_ROLES = list(PROJECT_ROLE_LABELS)
PROJECT_STATUS_LABELS = {"active": "进行中", "paused": "暂停", "completed": "完成", "archived": "归档"}
METHOD_STATUS_LABELS = {"active": "进行中", "completed": "完成", "archived": "归档", "cancelled": "取消"}
LIFECYCLE_LABELS = {"development": "开发", "validation": "验证", "transfer": "转移", "routine": "常规使用", "retired": "停用"}
EDIT_ROLES = {"owner", "author"}           # "make content" roles
SIGN_ROLES = {"reviewer", "approver"}      # "sign content" roles - never combined with EDIT_ROLES for one person
GLOBAL_NEED = {"owner": {"author", "admin"}, "author": {"author", "admin"}, "reviewer": {"reviewer"},
               "approver": {"approver"}, "viewer": None}
HASH_V = 3                                 # current stage_hash formula (1 = legacy text only, 2 = + experiments /
                                           # attachments / single-level project metadata, 3 = method metadata)
META_FROZEN = ("name", "analyte", "matrix", "intended_use")     # method fields covered by the charter signature
SAMPLE_MARK = "示例值，须按ATP确认"                                # templates_data.SAMPLE_TAG without its brackets
SAMPLE_WORD = "示例值"                                             # any wording of the template's example marker is detected
PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z])XX+(?![A-Za-z])")       # template placeholders such as “XX 方法”, “XX 实验室”


def has_mark(text):
    """True when the text still carries a template example marker (“示例值”) or an “XX” placeholder."""
    return SAMPLE_WORD in text or bool(PLACEHOLDER_RE.search(text))


class WFError(Exception):
    def __init__(self, msg, status=400, detail=None):
        super().__init__(msg)
        self.status = status
        self.detail = detail


# ------------------------------------------------------------------ small helpers
def _loadm(p):
    p = dict(p)
    p["meta"] = db.jl(p.get("meta"), {})
    return p


def _loads(s):
    s = dict(s)
    s["def"] = db.jl(s["def"], {})
    s["data"] = db.jl(s["data"], {})
    s["editors"] = db.jl(s["editors"], [])
    s["contributors"] = db.jl(s.get("contributors"), [])
    s["stale"] = bool(s["stale"])
    s["title"] = s["def"].get("title", s["key"])
    return s


def get_project(conn, pid):
    p = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        raise WFError("项目不存在", 404)
    return dict(p)


def get_method(conn, mid):
    m = conn.execute("SELECT * FROM methods WHERE id=?", (mid,)).fetchone()
    if not m:
        raise WFError("方法不存在", 404)
    return _loadm(m)


def get_stage(conn, mid, key):
    s = conn.execute("SELECT * FROM stages WHERE method_id=? AND key=?", (mid, key)).fetchone()
    if not s:
        raise WFError("阶段不存在", 404)
    return _loads(s)


def list_stages(conn, mid):
    return [_loads(s) for s in conn.execute("SELECT * FROM stages WHERE method_id=? ORDER BY ord", (mid,))]


def project_roles(conn, pid, uid):
    return {r["role"] for r in conn.execute("SELECT role FROM project_members WHERE project_id=? AND user_id=?", (pid, uid))}


def method_roles(conn, mid, uid):
    return {r["role"] for r in conn.execute("SELECT role FROM method_members WHERE method_id=? AND user_id=?", (mid, uid))}


def project_of(conn, mid):
    m = conn.execute("SELECT project_id FROM methods WHERE id=?", (mid,)).fetchone()
    return m["project_id"] if m else None


def can_view_project(conn, user, pid):
    return "admin" in user["roles"] or bool(project_roles(conn, pid, user["id"]))


def require_view_project(conn, user, pid):
    if not can_view_project(conn, user, pid):
        raise WFError("无权访问该项目", 403)


def can_view(conn, user, mid):
    """Method visibility = method member OR member of the method's project OR admin."""
    if "admin" in user["roles"]:
        return True
    if method_roles(conn, mid, user["id"]):
        return True
    pid = project_of(conn, mid)
    return pid is not None and bool(project_roles(conn, pid, user["id"]))


def require_view(conn, user, mid):
    if not can_view(conn, user, mid):
        raise WFError("无权访问该方法", 403)


def can_edit(conn, user, mid):
    r = method_roles(conn, mid, user["id"])
    return bool(r & EDIT_ROLES)


def require_edit(conn, user, mid):
    if not can_edit(conn, user, mid):
        raise WFError("仅方法负责人/开发人员可编辑", 403)


def method_writable_reason(conn, m):
    """None when content of method `m` may be written, else the reason (status of the method or of its project)."""
    if m["status"] != "active":
        return "方法已%s，不可修改" % METHOD_STATUS_LABELS.get(m["status"], "关闭")
    p = conn.execute("SELECT status FROM projects WHERE id=?", (m["project_id"],)).fetchone()
    if p and p["status"] != "active":
        return "所属项目已%s，不可修改" % PROJECT_STATUS_LABELS.get(p["status"], "关闭")
    return None


def stage_blockers(conn, mid, s):
    """Prerequisite stages of `s` that are not yet approved/completed (or are stale): [(step number, title)].
    Empty when the standard stage order is not enforced (config enforce_stage_order=false)."""
    if not config.get("enforce_stage_order"):
        return []
    stages = {x["key"]: x for x in list_stages(conn, mid)}
    out = []
    for req in s["def"].get("requires", []):
        rs = stages.get(req)
        if rs and (rs["status"] not in LOCKED or rs["stale"]):
            out.append((rs["ord"], rs["title"]))
    return sorted(out)


def _blockers_text(blockers):
    return "、".join("第 %d 步“%s”" % b for b in blockers)


def require_active_method(conn, mid):
    """M2: every write to method content needs the method AND its project to be 'active'.  Returns the method."""
    m = get_method(conn, mid)
    why = method_writable_reason(conn, m)
    if why:
        raise WFError(why, 409)
    return m


def require_active_project(conn, pid):
    p = get_project(conn, pid)
    if p["status"] != "active":
        raise WFError("项目已%s，不可修改" % PROJECT_STATUS_LABELS.get(p["status"], "关闭"), 409)
    return p


def _iso_date(d):
    return d.strftime("%Y-%m-%d")


def _today():
    return dt.date.today()


def _short(v, n=6000):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…(截断)"


def _blank(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple)):
        return all(_blank(x) for x in v)
    if isinstance(v, dict):
        return all(_blank(x) for x in v.values())
    return False


def _names(conn, ids):
    ids = [i for i in ids if isinstance(i, int)]
    if not ids:
        return []
    return [r["display_name"] for r in conn.execute(
        "SELECT display_name FROM users WHERE id IN (%s) ORDER BY display_name" % ",".join("?" * len(ids)), ids)]


def _user_name(conn, uid):
    r = conn.execute("SELECT display_name FROM users WHERE id=?", (uid,)).fetchone() if uid is not None else None
    return r["display_name"] if r else ""


# ------------------------------------------------------------------ signature hash (H3)
def _stage_attachment_hashes(conn, mid, key, direct_only):
    q = "SELECT sha256 FROM attachments WHERE method_id=? AND deleted=0 AND (stage_key=?"
    args = [mid, key]
    if not direct_only:
        q += " OR experiment_id IN (SELECT id FROM experiments WHERE method_id=? AND stage_key=?)"
        args += [mid, key]
    q += ") ORDER BY sha256, id"
    return [r["sha256"] for r in conn.execute(q, args)]


def _stage_extra(conn, mid, key):
    """Everything besides the stage's own text that a signature on `key` vouches for.
    plan  : every experiment that existed when the plan was signed (not flagged added_after_plan):
            code/title/objective/design/acceptance, plus the plan stage's own attachments.
    other : the experiments assigned to that stage with ALL their fields (results, conclusion, deviations,
            status) plus the attachments of the stage and of those experiments."""
    if key == "plan":
        exps = [{"code": r["code"], "title": r["title"], "objective": r["objective"] or "", "design": r["design"] or "",
                 "acceptance": r["acceptance"] or ""}
                for r in conn.execute("SELECT code,title,objective,design,acceptance FROM experiments "
                                      "WHERE method_id=? AND added_after_plan=0 ORDER BY code", (mid,))]
        return {"exps": exps, "atts": _stage_attachment_hashes(conn, mid, key, True)}
    exps = [{"code": r["code"], "title": r["title"], "objective": r["objective"] or "", "design": r["design"] or "",
             "acceptance": r["acceptance"] or "", "results": db.jl(r["results"], []), "conclusion": r["conclusion"] or "",
             "deviations": r["deviations"] or "", "status": r["status"]}
            for r in conn.execute("SELECT code,title,objective,design,acceptance,results,conclusion,deviations,status "
                                  "FROM experiments WHERE method_id=? AND stage_key=? ORDER BY code", (mid, key))]
    return {"exps": exps, "atts": _stage_attachment_hashes(conn, mid, key, False)}


def _meta_snapshot(conn, method_id, hv):
    """The method / project fields a signature on the charter (or on a gate covering it) vouches for.
    hv=2 (databases converted from the single-level model) reproduces the old four-field snapshot:
    title = method name, product = project product, attribute = analyte, intended_use."""
    r = conn.execute("SELECT m.name, m.analyte, m.matrix, m.intended_use, p.product FROM methods m "
                     "JOIN projects p ON p.id=m.project_id WHERE m.id=?", (method_id,)).fetchone()
    if r is None:
        return {}
    if hv == 2:
        return {"title": r["name"] or "", "product": r["product"] or "", "attribute": r["analyte"] or "",
                "intended_use": r["intended_use"] or ""}
    return {"name": r["name"] or "", "analyte": r["analyte"] or "", "matrix": r["matrix"] or "",
            "intended_use": r["intended_use"] or "", "product": r["product"] or ""}


def stage_hash(conn, method_id, stage, hv=HASH_V):
    """Hash binding a signature to the stage content (and to covered stages for composite gates).
    hv=1 is the legacy formula (stage data + covered stage data only) kept to verify old signatures;
    hv=2 also covers experiments, attachments and (for the charter / gates covering it) the single-level
    project metadata; hv=3 (current) covers the method name / analyte / matrix / intended use and the product
    of the method's project."""
    covers = (stage["def"].get("gate") or {}).get("covers") or []
    cov = {}
    for k in covers:
        s = conn.execute("SELECT data, revision FROM stages WHERE method_id=? AND key=?", (method_id, k)).fetchone()
        if s:
            cov[k] = {"rev": s["revision"], "h": db.sha256(s["data"])}
            if hv >= 2:
                cov[k]["x"] = db.sha256(db.canon(_stage_extra(conn, method_id, k)))
    if hv == 1:
        return db.sha256(db.canon({"stage": stage["key"], "revision": stage["revision"], "data": stage["data"], "covers": cov}))
    body = {"stage": stage["key"], "revision": stage["revision"], "data": stage["data"], "covers": cov, "hv": hv,
            "x": _stage_extra(conn, method_id, stage["key"])}
    if stage["key"] == "charter" or "charter" in covers:
        body["project"] = _meta_snapshot(conn, method_id, hv)
    return db.sha256(db.canon(body))


def _snapshot(conn, stage_id, revision):
    return conn.execute("SELECT data_hash, hv FROM stage_revisions WHERE stage_id=? AND revision=? ORDER BY id DESC LIMIT 1",
                        (stage_id, revision)).fetchone()


def current_hash(conn, mid, s):
    """The hash the UI shows / the reviewer signs: same formula version as the stage's submission snapshot."""
    snap = _snapshot(conn, s["id"], s["revision"])
    return stage_hash(conn, mid, s, snap["hv"] if snap else HASH_V)


def _signature_eval(conn, mid, s):
    """Returns ({review_id: intact}, problems).  A signature is intact when (a) it equals the hash that was
    stored with the submission snapshot of that revision (history can't be recomputed - the snapshot table is
    append-only) and (b) for the stage's current, locked revision the live content still hashes to it."""
    revs = {}
    for r in conn.execute("SELECT revision, data_hash, hv FROM stage_revisions WHERE stage_id=? ORDER BY id", (s["id"],)):
        revs[r["revision"]] = r
    live = {}

    def live_hash(hv):
        if hv not in live:
            live[hv] = stage_hash(conn, mid, s, hv)
        return live[hv]

    intact, problems = {}, []
    locked_now = s["status"] in FROZEN and not s["stale"]
    for rv in conn.execute("SELECT id, revision, role, decision, data_hash FROM reviews WHERE stage_id=? ORDER BY id", (s["id"],)):
        snap = revs.get(rv["revision"])
        label = "R%d %s" % (rv["revision"], ROLE_LABELS.get(rv["role"], rv["role"]))
        ok = True
        if snap is None:
            ok = False; problems.append("%s 的签名没有对应的提交快照" % label)
        elif snap["data_hash"] != rv["data_hash"]:
            ok = False; problems.append("%s 的签名哈希与提交快照不一致" % label)
        elif rv["revision"] == s["revision"] and locked_now and live_hash(snap["hv"]) != rv["data_hash"]:
            ok = False; problems.append("%s 签名后阶段内容（含实验/附件/方法与项目信息）已被改动" % label)
        intact[rv["id"]] = ok
    if s["status"] in LOCKED:
        snap = revs.get(s["revision"])
        if snap is None:
            problems.append("阶段已%s但没有提交快照" % STATUS_LABELS[s["status"]])
        elif not s["stale"] and live_hash(snap["hv"]) != snap["data_hash"]:
            problems.append("阶段内容与提交快照不一致（%s后被改动）" % STATUS_LABELS[s["status"]])
        gate = s["def"].get("gate")
        if gate:
            have = {r["role"] for r in conn.execute("SELECT role FROM reviews WHERE stage_id=? AND revision=? AND decision='approve'",
                                                    (s["id"], s["revision"]))}
            for role in gate["roles"]:
                if role not in have:
                    problems.append("缺少%s的签名记录" % ROLE_LABELS[role])
    return intact, problems


def stage_signature_status(conn, mid, s):
    """(ok, problems) for one stage - used by stage_detail, the audit verification and document generation."""
    return (lambda r: (not r[1], r[1]))(_signature_eval(conn, mid, s))


def method_signatures(conn, mid):
    bad = []
    for s in list_stages(conn, mid):
        if s["status"] in LOCKED or conn.execute("SELECT 1 FROM reviews WHERE stage_id=? LIMIT 1", (s["id"],)).fetchone():
            ok, problems = stage_signature_status(conn, mid, s)
            if not ok:
                bad.append({"stage": s["key"], "title": s["title"], "revision": s["revision"], "problems": problems})
    return (not bad), bad


# ------------------------------------------------------------------ codes, seeding, team validation
def _next_code(conn, table, prefix):
    """PRJ-YYYY-NNN (table 'projects') / AM-YYYY-NNN (table 'methods'); the sequence is global per year."""
    y = _today().year
    n = conn.execute("SELECT COUNT(*) FROM %s WHERE code LIKE ?" % table, ("%s-%d-%%" % (prefix, y),)).fetchone()[0] + 1
    while conn.execute("SELECT 1 FROM %s WHERE code=?" % table, ("%s-%d-%03d" % (prefix, y, n),)).fetchone():
        n += 1
    return "%s-%d-%03d" % (prefix, y, n)


def _seed_stage_data(tpl, stage_def):
    key = stage_def["key"]
    seed = tpl["seed"]
    sections = {}
    if key == "atp":
        sections["criteria"] = [{"characteristic": r[0], "criterion": r[1], "rationale": r[2], "source": r[3]} for r in seed["atp_rows"]]
    elif key == "tech":
        m = seed["matrix"]
        sections["matrix"] = {"options": list(m["options"]), "selected": "",
                              "criteria": [{"name": n, "weight": w, "scores": {}} for n, w in m["criteria"]]}
    elif key == "risk":
        sections["fmea"] = [dict(r, owner="") for r in seed["fmea"]]
    elif key == "plan":
        sections["phases"] = [{"phase": e["code"], "objective": e["objective"], "design": e["design"],
                               "acceptance": e["acceptance"], "weeks": e["weeks"]} for e in seed["experiments"]]
    elif key == "control":
        sections["sst"] = [{"item": r[0], "criterion": r[1], "risk": r[2], "action": r[3]} for r in seed["sst"]]
    # E1 (template 1.1): every table from its `seed_rows`, every text from its `default`
    for sec in stage_def["sections"]:
        if sec["key"] in sections:
            continue
        if sec["type"] == "table" and sec.get("seed_rows"):
            sections[sec["key"]] = json.loads(json.dumps(sec["seed_rows"], ensure_ascii=False))
        elif sec["type"] == "text" and sec.get("default"):
            sections[sec["key"]] = sec["default"]
    checklist = {c["key"]: {"status": "todo", "note": "", "by": None, "at": None} for c in stage_def["checklist"]}
    # everything the template pre-filled is "unconfirmed" until a person confirms the section (the scoring matrix is
    # excluded: its scores are always entered by people)
    unconfirmed = [k for k, v in sections.items() if k != "matrix" and not _blank(v)]
    return {"sections": sections, "checklist": checklist, "unconfirmed": unconfirmed}


def normalize_members(conn, members, base=(), project_id=None):
    """H1: validate a METHOD team list and return the set of (user_id, role).
    - the user must exist and be active; the method role must match a global role
      (owner/author: author or admin; reviewer: reviewer; approver: approver);
    - with `project_id`: the user must be a member of that project (global admins excepted);
    - nobody may combine an editing role (owner/author) with a signing role (reviewer/approver);
    - nobody may be both reviewer and approver."""
    if not isinstance(members, list) or len(members) > 200:
        raise WFError("成员必须是列表")
    new = set(base)
    for m in members:
        if not isinstance(m, dict):
            raise WFError("成员条目格式不正确")
        role = m.get("role")
        if not isinstance(role, str) or role not in MEMBER_ROLES:
            raise WFError("未知成员角色")
        uid = m.get("user_id")
        if isinstance(uid, bool) or not isinstance(uid, int):
            raise WFError("成员的 user_id 必须是整数")
        u = conn.execute("SELECT id, username, roles, active FROM users WHERE id=?", (uid,)).fetchone()
        if not u or not u["active"]:
            raise WFError("用户不存在或已停用")
        uroles = set(db.jl(u["roles"], []))
        need = GLOBAL_NEED[role]
        if need and not (need & uroles):
            raise WFError("用户“%s”的全局角色不允许担任方法角色“%s”（须具备全局角色：%s）" %
                          (u["username"], ROLE_LABELS[role], "/".join(sorted(auth.ROLE_LABELS[r] for r in need))))
        if project_id is not None and "admin" not in uroles and not project_roles(conn, project_id, uid):
            raise WFError("用户“%s”不是所属项目的成员，请先把他加入项目团队" % u["username"])
        new.add((uid, role))
    by_user = {}
    for uid, role in new:
        by_user.setdefault(uid, set()).add(role)
    for uid, roles in by_user.items():
        if roles & EDIT_ROLES and roles & SIGN_ROLES:
            raise WFError("同一人不能同时担任编辑类角色（负责人/开发人员）和签署类角色（复核人/批准人）——职责分离")
        if SIGN_ROLES <= roles:
            raise WFError("同一人不能同时是复核人和批准人")
    return new


_PRANK = {"owner": 3, "member": 2, "viewer": 1}


def normalize_project_members(conn, members, base=()):
    """Validate a PROJECT team list -> set of (user_id, role) with exactly one (the highest) role per person.
    Project owners need the global role author or admin; any active account may be member / viewer."""
    if not isinstance(members, list) or len(members) > 200:
        raise WFError("成员必须是列表")
    new = set(base)
    for m in members:
        if not isinstance(m, dict):
            raise WFError("成员条目格式不正确")
        role = m.get("role")
        if not isinstance(role, str) or role not in PROJECT_ROLES:
            raise WFError("未知项目成员角色（owner / member / viewer）")
        uid = m.get("user_id")
        if isinstance(uid, bool) or not isinstance(uid, int):
            raise WFError("成员的 user_id 必须是整数")
        u = conn.execute("SELECT id, username, roles, active FROM users WHERE id=?", (uid,)).fetchone()
        if not u or not u["active"]:
            raise WFError("用户不存在或已停用")
        if role == "owner" and not ({"author", "admin"} & set(db.jl(u["roles"], []))):
            raise WFError("用户“%s”的全局角色不允许担任项目负责人（须具备全局角色：开发人员/管理员）" % u["username"])
        new.add((uid, role))
    best = {}
    for uid, role in new:
        if uid not in best or _PRANK[role] > _PRANK[best[uid]]:
            best[uid] = role
    return {(uid, role) for uid, role in best.items()}


def _check_dates(start, end):
    if start and end and end < start:
        raise WFError("计划结束日期不能早于开始日期")


# ------------------------------------------------------------------ projects
_PROJECT_TEXT = {"product": ("产品", 2000), "indication": ("适应症", 2000), "phase": ("研发阶段", 2000), "description": ("项目说明", 20000)}


def _project_fields(d, creating=False):
    """Validated copies of the project fields present in `d`."""
    out = {}
    if "name" in d or creating:
        out["name"] = validate.text(d.get("name"), "项目名称", 200, required=True).strip()
    for k, (label, mx) in _PROJECT_TEXT.items():
        if k in d:
            out[k] = validate.text(d[k], label, mx)
    for k in ("planned_start", "planned_end"):
        if k in d:
            out[k] = validate.date_or_none(d[k], "计划日期")
    return out


def create_project(conn, user, d):
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    if not ({"author", "admin"} & set(user["roles"])):
        raise WFError("新建项目需要“开发人员”或管理员角色", 403)
    f = _project_fields(d, creating=True)
    _check_dates(f.get("planned_start"), f.get("planned_end"))
    members = normalize_project_members(conn, d.get("members") or [], base={(user["id"], "owner")})
    code = _next_code(conn, "projects", "PRJ")
    cur = conn.execute(
        "INSERT INTO projects(code,name,product,indication,phase,description,status,planned_start,planned_end,owner_id,created_by,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, f["name"], f.get("product", ""), f.get("indication", ""), f.get("phase", ""), f.get("description", ""), "active",
         f.get("planned_start"), f.get("planned_end"), user["id"], user["id"], db.now(), db.now()))
    pid = cur.lastrowid
    for uid, role in sorted(members):
        conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?)", (pid, uid, role))
    audit.log(conn, user, "project.create", "project", pid, None, {"code": code, "name": f["name"]}, project_id=pid)
    return pid


def _project_has_locked_stage(conn, pid):
    return conn.execute("SELECT 1 FROM stages s JOIN methods m ON m.id=s.method_id WHERE m.project_id=? AND s.status IN ('approved','completed') LIMIT 1",
                        (pid,)).fetchone() is not None


def update_project(conn, user, pid, d):
    """Project owner edits project fields / status.  Re-authentication for a status regression (back to
    'active') is done by the caller (main.project_patch) before this function runs; the reason is enforced here.
    The product is part of the charter signature of every method of the project (see _meta_snapshot): it is
    frozen as soon as one stage of one of the project's methods is approved / completed."""
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    p = get_project(conn, pid)
    if "owner" not in project_roles(conn, pid, user["id"]):
        raise WFError("仅项目负责人可修改项目信息", 403)
    f = _project_fields(d)
    reason = validate.text(d.get("reason"), "原因", 2000)
    _check_dates(f.get("planned_start", p["planned_start"]), f.get("planned_end", p["planned_end"]))
    sets, vals, changes = [], [], {}
    product_changed = "product" in f and f["product"] != (p["product"] or "")
    if product_changed and _project_has_locked_stage(conn, pid):
        raise WFError("项目下已有方法的阶段通过批准/完成，产品名称已冻结；如需修改请先重新打开相应阶段", 409)
    for k, v in f.items():
        if (v or "") != (p[k] or ""):
            sets.append("%s=?" % k); vals.append(v); changes[k] = [p[k], v]
    if "status" in d and d["status"] != p["status"]:
        st = d["status"]
        if not isinstance(st, str) or st not in PROJECT_STATUS_LABELS:
            raise WFError("无效状态")
        if st == "completed":
            busy = [r["code"] for r in conn.execute("SELECT code FROM methods WHERE project_id=? AND status='active' ORDER BY id", (pid,))]
            if busy:
                raise WFError("仍有进行中的方法：" + "、".join(busy), 422)
        if st == "active" and not reason.strip():
            raise WFError("将项目恢复为进行中须填写原因")
        sets.append("status=?"); vals.append(st); changes["status"] = [p["status"], st]
    if not sets:
        return
    sets.append("updated_at=?"); vals.append(db.now()); vals.append(pid)
    conn.execute("UPDATE projects SET %s WHERE id=?" % ",".join(sets), vals)
    if product_changed:        # the product is part of every method's charter / plan signature
        for r in conn.execute("SELECT id FROM methods WHERE project_id=?", (pid,)).fetchall():
            for k in ("charter", "plan"):
                _add_contributor(conn, r["id"], k, user["id"])
    audit.log(conn, user, "project.update", "project", pid, None, changes, reason or None, project_id=pid)


def set_project_members(conn, user, pid, members):
    """Project owner replaces the project team.  Nobody who is still on a method team of the project can be
    removed from it (method teams must stay a subset of the project team)."""
    if "owner" not in project_roles(conn, pid, user["id"]):
        raise WFError("仅项目负责人可调整项目成员", 403)
    p = require_active_project(conn, pid)
    old = [(r["user_id"], r["role"]) for r in conn.execute("SELECT user_id, role FROM project_members WHERE project_id=?", (pid,))]
    new = normalize_project_members(conn, members)
    if not any(r == "owner" for _, r in new):
        raise WFError("至少保留一名项目负责人")
    gone = {u for u, _ in old} - {u for u, _ in new}
    if gone:
        stuck = conn.execute("SELECT DISTINCT u.display_name AS display_name, m.code AS code FROM method_members mm "
                             "JOIN methods m ON m.id=mm.method_id JOIN users u ON u.id=mm.user_id "
                             "WHERE m.project_id=? AND mm.user_id IN (%s) ORDER BY m.code" % ",".join("?" * len(gone)),
                             [pid] + sorted(gone)).fetchall()
        if stuck:
            raise WFError("下列成员仍在方法团队中，请先在相应方法中移除后再移出项目：" +
                          "；".join("%s（%s）" % (r["display_name"], r["code"]) for r in stuck), 409)
    conn.execute("DELETE FROM project_members WHERE project_id=?", (pid,))
    for uid, role in sorted(new):
        conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?)", (pid, uid, role))
    if p["owner_id"] not in {u for u, r in new if r == "owner"}:
        conn.execute("UPDATE projects SET owner_id=? WHERE id=?", (min(u for u, r in new if r == "owner"), pid))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now(), pid))
    audit.log(conn, user, "project.members", "project", pid, None, {"old": sorted(old), "new": sorted(new)}, project_id=pid)


# ------------------------------------------------------------------ methods
_METHOD_TEXT = {"analyte": ("被测属性/分析物", 2000), "matrix": ("样品基质", 2000), "intended_use": ("预期用途", 2000),
                "phase": ("研发阶段", 2000)}


def _method_fields(d, creating=False):
    """Validated copies of the method fields present in `d`."""
    out = {}
    if "name" in d or creating:
        out["name"] = validate.text(d.get("name"), "方法名称", 200, required=True).strip()
    for k, (label, mx) in _METHOD_TEXT.items():
        if k in d:
            out[k] = validate.text(d[k], label, mx)
    if "method_version" in d:
        out["method_version"] = validate.text(d["method_version"], "方法版本", 40).strip()
        if not out["method_version"]:
            if not creating:
                raise WFError("请填写方法版本")
            del out["method_version"]
    for k in ("planned_start", "planned_end"):
        if k in d:
            out[k] = validate.date_or_none(d[k], "计划日期")
    return out


def create_method(conn, user, pid, d):
    """Create a method (with its 9 stages and the template's experiment seeds) inside project `pid`.
    The caller must be owner / member of the project AND hold the global role author (or admin)."""
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    project = get_project(conn, pid)
    if not (project_roles(conn, pid, user["id"]) & {"owner", "member"}):
        raise WFError("仅项目负责人或项目成员可新增方法", 403)
    if not ({"author", "admin"} & set(user["roles"])):
        raise WFError("新增方法需要“开发人员”或管理员角色", 403)
    if project["status"] != "active":
        raise WFError("项目已%s，不能新增方法" % PROJECT_STATUS_LABELS.get(project["status"], "关闭"), 409)
    f = _method_fields(d, creating=True)
    tkey = d.get("template_key") if d.get("template_key") is not None else d.get("technique")
    tkey = tkey or "generic"
    if not isinstance(tkey, str):
        raise WFError("技术模板必须是文本")
    try:
        tpl = templates_data.build_template(tkey)
    except KeyError:
        raise WFError("未知的技术模板")
    members = normalize_members(conn, d.get("members") or [], base={(user["id"], "owner"), (user["id"], "author")}, project_id=pid)
    code = _next_code(conn, "methods", "AM")
    start = f.get("planned_start") or _iso_date(_today())
    cur = conn.execute(
        "INSERT INTO methods(code,project_id,name,technique,template_key,template_version,analyte,matrix,intended_use,phase,method_version,"
        "lifecycle,status,planned_start,planned_end,owner_id,created_by,created_at,updated_at,meta) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, pid, f["name"], tkey, tkey, tpl["version"], f.get("analyte", ""), f.get("matrix", ""), f.get("intended_use", ""),
         f.get("phase", ""), f.get("method_version") or "V0.1", "development", "active", start, None, user["id"], user["id"],
         db.now(), db.now(), json.dumps({"template_label": tpl["label"]}, ensure_ascii=False)))
    mid = cur.lastrowid
    for uid, role in sorted(members):
        conn.execute("INSERT OR IGNORE INTO method_members(method_id,user_id,role) VALUES(?,?,?)", (mid, uid, role))
    cursor_date = dt.date.fromisoformat(start)
    stage_dates = {}
    for i, sd in enumerate(tpl["stages"], 1):
        end = cursor_date + dt.timedelta(weeks=sd["weeks"]) - dt.timedelta(days=1)
        stage_dates[sd["key"]] = (_iso_date(cursor_date), _iso_date(end))
        conn.execute(
            "INSERT INTO stages(method_id,key,ord,def,status,data,planned_start,planned_end,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (mid, sd["key"], i, json.dumps(sd, ensure_ascii=False), "not_started",
             json.dumps(_seed_stage_data(tpl, sd), ensure_ascii=False), stage_dates[sd["key"]][0], stage_dates[sd["key"]][1], db.now()))
        cursor_date = end + dt.timedelta(days=1)
    conn.execute("UPDATE methods SET planned_end=? WHERE id=?", (_iso_date(cursor_date - dt.timedelta(days=1)), mid))
    for e in tpl["seed"]["experiments"]:
        ps, pe = stage_dates.get(e["stage_key"], (start, start))
        conn.execute(
            "INSERT INTO experiments(method_id,stage_key,code,title,objective,design,acceptance,planned_start,planned_end,status,owner_id,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, e["stage_key"], e["code"], e["title"], e["objective"], e["design"], e["acceptance"], ps, pe, "planned",
             user["id"], db.now(), db.now()))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now(), pid))
    audit.log(conn, user, "method.create", "method", mid, mid,
              {"code": code, "name": f["name"], "template": tkey, "project": project["code"]})
    return mid


def clone_method(conn, user, mid, title, target_project_id=None):
    """Copy a method's section content (checklists start fresh, no signatures, no experiments results) into a new
    method of the same or another project.  The target project is checked exactly like a normal creation."""
    src = get_method(conn, mid)
    require_view(conn, user, mid)
    if title is not None and not isinstance(title, str):
        raise WFError("方法名称必须是文本")
    if target_project_id is not None and (isinstance(target_project_id, bool) or not isinstance(target_project_id, int)):
        raise WFError("project_id 必须是整数")
    pid = target_project_id or src["project_id"]
    nm = (title or "").strip() or (src["name"] + "（副本）")
    new_id = create_method(conn, user, pid, {"name": nm, "template_key": src["template_key"], "analyte": src["analyte"],
                                             "matrix": src["matrix"], "intended_use": src["intended_use"], "phase": src["phase"]})
    new_stages = {s["key"]: s for s in list_stages(conn, new_id)}
    for s in list_stages(conn, mid):
        ns = new_stages.get(s["key"])
        if not ns:
            continue
        keys = {x["key"] for x in ns["def"]["sections"]}
        data = ns["data"]
        for k, v in (s["data"].get("sections") or {}).items():
            if k in keys:
                data.setdefault("sections", {})[k] = v
        conn.execute("UPDATE stages SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), ns["id"]))
    audit.log(conn, user, "method.clone", "method", new_id, new_id,
              {"from": src["code"], "from_project_id": src["project_id"], "to_project_id": pid})
    return new_id


def update_method(conn, user, mid, d):
    """Method owner edits method info / development status.  Re-authentication for a status regression (back to
    'active') is done by the caller (main.method_patch); the reason is enforced here.  name / analyte / matrix /
    intended_use are covered by the charter signature: frozen once any stage is approved / completed."""
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    m = get_method(conn, mid)
    if "owner" not in method_roles(conn, mid, user["id"]):
        raise WFError("仅方法负责人可修改方法信息", 403)
    for k in ("lifecycle", "project_id", "template_key", "technique", "code"):
        if k in d and d[k] != m[k]:
            raise WFError("不能通过此接口修改“%s”%s" % (k, "（请使用 /lifecycle 接口）" if k == "lifecycle" else ""))
    f = _method_fields(d)
    reason = validate.text(d.get("reason"), "原因", 2000)
    _check_dates(f.get("planned_start", m["planned_start"]), f.get("planned_end", m["planned_end"]))
    sets, vals, changes = [], [], {}
    meta_changed = [k for k in META_FROZEN if k in f and f[k] != (m[k] or "")]
    if meta_changed:
        locked = [s["title"] for s in list_stages(conn, mid) if s["status"] in LOCKED]
        if locked:
            raise WFError("阶段“%s”已批准/完成，方法名称/被测属性/样品基质/预期用途已冻结；如需修改请先重新打开相应阶段" % "、".join(locked), 409)
    for k, v in f.items():
        if (v or "") != (m[k] or ""):
            sets.append("%s=?" % k); vals.append(v); changes[k] = [m[k], v]
    if "status" in d and d["status"] != m["status"]:
        st = d["status"]
        if not isinstance(st, str) or st not in METHOD_STATUS_LABELS:
            raise WFError("无效状态")
        if st == "completed":
            bad = [s["title"] for s in list_stages(conn, mid) if s["status"] not in LOCKED or s["stale"]]
            if bad:
                raise WFError("仍有阶段未通过或已失效：" + "、".join(bad), 422)
        if st == "active" and not reason.strip():
            raise WFError("将方法恢复为进行中须填写原因")
        sets.append("status=?"); vals.append(st); changes["status"] = [m["status"], st]
    if not sets:
        return
    sets.append("updated_at=?"); vals.append(db.now()); vals.append(mid)
    conn.execute("UPDATE methods SET %s WHERE id=?" % ",".join(sets), vals)
    if meta_changed:        # method metadata is part of the charter / plan signatures
        for k in ("charter", "plan"):
            _add_contributor(conn, mid, k, user["id"])
    audit.log(conn, user, "method.update", "method", mid, mid, changes, reason or None)


def set_members(conn, user, mid, members):
    """Replace the METHOD team.  Allowed for the method owner and for the owner of the method's project."""
    m = get_method(conn, mid)
    if "owner" not in method_roles(conn, mid, user["id"]) and "owner" not in project_roles(conn, m["project_id"], user["id"]):
        raise WFError("仅方法负责人或项目负责人可调整方法团队", 403)
    require_active_method(conn, mid)
    old = [(r["user_id"], r["role"]) for r in conn.execute("SELECT user_id, role FROM method_members WHERE method_id=?", (mid,))]
    new = normalize_members(conn, members, project_id=m["project_id"])
    if not any(r == "owner" for _, r in new):
        raise WFError("至少保留一名方法负责人")
    if conn.execute("SELECT 1 FROM stages WHERE method_id=? AND status='in_review' LIMIT 1", (mid,)).fetchone():
        if {x for x in old if x[1] in SIGN_ROLES} != {x for x in new if x[1] in SIGN_ROLES}:
            raise WFError("有阶段正在待复核：此时不能增删复核人/批准人（请先撤回或完成复核）", 409)
    conn.execute("DELETE FROM method_members WHERE method_id=?", (mid,))
    for uid, role in sorted(new):
        conn.execute("INSERT INTO method_members(method_id,user_id,role) VALUES(?,?,?)", (mid, uid, role))
    if m["owner_id"] not in {u for u, r in new if r == "owner"}:
        conn.execute("UPDATE methods SET owner_id=? WHERE id=?", (min(u for u, r in new if r == "owner"), mid))
    conn.execute("UPDATE methods SET updated_at=? WHERE id=?", (db.now(), mid))
    audit.log(conn, user, "method.members", "method", mid, mid, {"old": sorted(old), "new": sorted(new)})


def check_lifecycle_allowed(conn, user, mid):
    """Who may change the lifecycle: the method owner or approver (re-authentication is done by the caller)."""
    m = get_method(conn, mid)
    if not (method_roles(conn, mid, user["id"]) & {"owner", "approver"}):
        raise WFError("仅方法负责人或批准人可变更生命周期", 403)
    return m


def set_lifecycle(conn, user, mid, lifecycle, reason):
    """Record a lifecycle change (development / validation / transfer / routine / retired).  Allowed in every
    development status - a finished development is exactly when a method moves on to validation."""
    m = check_lifecycle_allowed(conn, user, mid)
    if not isinstance(lifecycle, str) or lifecycle not in LIFECYCLE_LABELS:
        raise WFError("无效的生命周期（%s）" % " / ".join(LIFECYCLE_LABELS))
    reason = validate.text(reason, "原因", 2000)
    if not reason.strip():
        raise WFError("变更生命周期须填写原因")
    if lifecycle == m["lifecycle"]:
        raise WFError("生命周期未变化")
    conn.execute("UPDATE methods SET lifecycle=?, updated_at=? WHERE id=?", (lifecycle, db.now(), mid))
    audit.log(conn, user, "method.lifecycle", "method", mid, mid, {"from": m["lifecycle"], "to": lifecycle}, reason)


# ------------------------------------------------------------------ progress
def _dict_rows(val):
    return [r for r in val if isinstance(r, dict)] if isinstance(val, list) else []


def _section_filled(sec, val):
    t = sec["type"]
    if t == "text":
        return not _blank(val)
    if t == "fields":
        val = val if isinstance(val, dict) else {}
        req = [f for f in sec["fields"] if f.get("required")]
        if req:
            return all(not _blank(val.get(f["key"])) for f in req)
        return not _blank(val)
    if t in ("table", "fmea"):
        rows = [r for r in (val if isinstance(val, list) else []) if not _blank(r)]
        return len(rows) >= max(1, sec.get("min_rows", 1) if t == "table" else 1)
    if t == "matrix":
        m = val if isinstance(val, dict) else {}
        crit = _dict_rows(m.get("criteria"))
        return bool(m.get("selected")) and any(isinstance(c.get("scores"), dict) and any(c["scores"].values()) for c in crit)
    return False


def stage_progress(conn, method_id, s):
    if s["status"] in LOCKED:
        return 100
    d = s["data"]
    items = s["def"]["checklist"]
    done = sum(1 for c in items if d.get("checklist", {}).get(c["key"], {}).get("status") in ("done", "na"))
    cl = done / len(items) if items else 1
    secs = [x for x in s["def"]["sections"] if x.get("required")] or s["def"]["sections"]
    unc = set(d.get("unconfirmed") or [])           # template pre-fill that nobody has confirmed does not count as progress
    sf = sum(1 for x in secs if x["key"] not in unc and _section_filled(x, d.get("sections", {}).get(x["key"]))) / len(secs) if secs else 1
    exps = conn.execute("SELECT status FROM experiments WHERE method_id=? AND stage_key=?", (method_id, s["key"])).fetchall()
    if exps:
        ex = sum(1 for e in exps if e["status"] in ("done", "cancelled")) / len(exps)
        v = 0.4 * cl + 0.3 * sf + 0.3 * ex
    else:
        v = 0.6 * cl + 0.4 * sf
    if s["status"] == "in_review":
        return 95
    return int(min(90, round(v * 100)))


def method_summary(conn, p):
    """progress / overdue stage titles (only while the method is active) / current stage / stale stage titles."""
    stages = list_stages(conn, p["id"])
    prog = [stage_progress(conn, p["id"], s) for s in stages]
    today = _iso_date(_today())
    overdue = [s["title"] for s in stages if s["status"] not in LOCKED and s["planned_end"] and s["planned_end"] < today] \
        if p.get("status", "active") == "active" else []
    cur = next((s for s in stages if s["status"] not in LOCKED), None)
    return {"progress": int(sum(prog) / len(prog)) if prog else 0, "overdue": overdue,
            "current_stage": {"key": cur["key"], "title": cur["title"], "status": cur["status"]} if cur else None,
            "stale": [s["title"] for s in stages if s["stale"]]}


# ------------------------------------------------------------------ contributors (H1)
def _add_contributor(conn, mid, stage_key, uid, current=True):
    """Record that `uid` touched the stage.  `contributors` is cumulative (never reset by withdraw / reject /
    reopen / revision bumps) and drives separation of duties; `editors` is only the current revision's list.
    A stage that is locked or in review is never modified."""
    if not stage_key or uid is None:
        return
    s = conn.execute("SELECT id, status, editors, contributors FROM stages WHERE method_id=? AND key=?", (mid, stage_key)).fetchone()
    if not s or s["status"] not in EDITABLE:
        return
    con = set(db.jl(s["contributors"], []))
    ed = set(db.jl(s["editors"], []))
    if uid in con and (not current or uid in ed):
        return
    con.add(uid)
    if current:
        ed.add(uid)
    conn.execute("UPDATE stages SET editors=?, contributors=? WHERE id=?", (json.dumps(sorted(ed)), json.dumps(sorted(con)), s["id"]))


# ------------------------------------------------------------------ stage editing
def _merge_save(conn, user, p, s, payload):
    mid = p["id"]
    require_edit(conn, user, mid)
    why = method_writable_reason(conn, p)
    if why:
        raise WFError(why, 409)
    if s["status"] not in EDITABLE:
        raise WFError("阶段当前状态为“%s”，不可编辑；如需修改请先撤回或重新打开" % STATUS_LABELS[s["status"]], 409)
    blockers = stage_blockers(conn, mid, s)
    if blockers:
        raise WFError("本步骤尚未开放：标准流程要求先完成并通过 %s" % _blockers_text(blockers), 409)
    version = validate.integer(payload.get("version", -1), "version")
    if version != s["version"]:
        raise WFError("内容已被他人更新（版本冲突），请刷新后重试", 409)
    data = s["data"]
    changes = {}
    reason = validate.text(payload.get("reason"), "修改原因", 2000)
    if config.get("require_change_reason") and (s["revision"] > 1 or s["status"] == "returned") and not reason.strip() and (payload.get("sections") or payload.get("checklist")):
        raise WFError("该阶段已被退回/重新打开过，修改内容须填写“修改原因”", 400)
    secs_def = {x["key"]: x for x in s["def"]["sections"]}
    in_secs = payload.get("sections") or {}
    in_cl = payload.get("checklist") or {}
    if not isinstance(in_secs, dict) or not isinstance(in_cl, dict):
        raise WFError("sections / checklist 必须是对象")
    for k, v in in_secs.items():
        if k not in secs_def:
            raise WFError("未知章节：%s" % str(k)[:40])
        v = validate.section(secs_def[k], v)
        old = data.get("sections", {}).get(k)
        if old != v:
            changes["section:" + k] = {"old": _short(old), "new": _short(v)}
            data.setdefault("sections", {})[k] = v
    cl_def = {c["key"] for c in s["def"]["checklist"]}
    for k, v in in_cl.items():
        if k not in cl_def:
            raise WFError("未知检查项：%s" % str(k)[:40])
        v = validate.checklist_item(v, k)
        old = data.get("checklist", {}).get(k, {})
        if old.get("status") != v["status"] or old.get("note", "") != v["note"]:
            changes["check:" + k] = {"old": [old.get("status"), old.get("note")], "new": [v["status"], v["note"]]}
            data.setdefault("checklist", {})[k] = {"status": v["status"], "note": v["note"], "by": user["id"], "at": db.now()}
    confirm = payload.get("confirm_sections") or []
    if not isinstance(confirm, list) or any(not isinstance(x, str) for x in confirm):
        raise WFError("confirm_sections 必须是章节键的列表")
    for k in confirm:
        if k not in secs_def:
            raise WFError("未知章节：%s" % k[:40])
        if k in (data.get("unconfirmed") or []):
            if has_mark(json.dumps(data.get("sections", {}).get(k), ensure_ascii=False)):
                raise WFError("“%s”中仍含“%s”标记或“XX”占位符：请逐项核对数值与依据，替换为真实内容并删除标记后再确认" % (secs_def[k]["title"], SAMPLE_WORD))
            data["unconfirmed"] = [x for x in data["unconfirmed"] if x != k]
            changes["confirm:" + k] = {"old": "unconfirmed", "new": "confirmed"}
    sets, vals = [], []
    for k in ("planned_start", "planned_end"):
        if k in payload:
            nv = validate.date_or_none(payload[k], "计划日期")
            if nv != s[k]:
                changes[k] = {"old": s[k], "new": nv}
                sets.append("%s=?" % k); vals.append(nv)
    if not changes:
        return False
    editors = set(s["editors"]); editors.add(user["id"])
    contributors = set(s["contributors"]); contributors.add(user["id"])
    status = "in_progress" if s["status"] == "not_started" else s["status"]
    conn.execute("UPDATE stages SET data=?, editors=?, contributors=?, version=version+1, status=?, actual_start=COALESCE(actual_start,?), updated_at=?%s WHERE id=?"
                 % ("".join("," + x for x in sets)),
                 [json.dumps(data, ensure_ascii=False), json.dumps(sorted(editors)), json.dumps(sorted(contributors)), status,
                  _iso_date(_today()), db.now()] + vals + [s["id"]])
    audit.log(conn, user, "stage.save", "stage", s["id"], mid, {"stage": s["key"], "revision": s["revision"], "changes": changes}, reason or None)
    return True


def save_stage(conn, user, mid, key, payload):
    if not isinstance(payload, dict):
        raise WFError("请求格式不正确")
    p = get_method(conn, mid)
    s = get_stage(conn, mid, key)
    _merge_save(conn, user, p, s, payload)
    return get_stage(conn, mid, key)


# ------------------------------------------------------------------ gate checks
def _next_role(conn, s):
    gate = s["def"].get("gate")
    if not gate:
        return None
    signed = {r["role"] for r in conn.execute("SELECT role FROM reviews WHERE stage_id=? AND revision=? AND decision='approve'", (s["id"], s["revision"]))}
    for role in gate["roles"]:
        if role not in signed:
            return role
    return None


def _eligible(conn, mid, role, s, exclude=()):
    """Members who hold `role` in the method team AND globally, are active, and never contributed to the stage."""
    out = []
    for r in conn.execute("SELECT DISTINCT u.id, u.roles FROM method_members m JOIN users u ON u.id=m.user_id "
                          "WHERE m.method_id=? AND m.role=? AND u.active=1", (mid, role)):
        if role not in db.jl(r["roles"], []):
            continue
        if r["id"] in s["contributors"] or r["id"] in exclude:
            continue
        out.append(r["id"])
    return out


def _sod(r):
    """(S, O, D) as ints, or None when any is missing / not a whole number."""
    try:
        return int(r.get("S")), int(r.get("O")), int(r.get("D"))
    except (TypeError, ValueError, OverflowError):
        return None


def gate_checks(conn, p, s):
    blocks, warns = [], []
    mid = p["id"]
    d = s["data"]
    stages = {x["key"]: x for x in list_stages(conn, mid)}
    for req in s["def"].get("requires", []):
        rs = stages.get(req)
        if not rs or rs["status"] not in LOCKED:
            blocks.append("前置阶段“%s”尚未通过/完成" % (rs["title"] if rs else req))
        elif rs["stale"]:
            blocks.append("前置阶段“%s”已失效，需重新复核" % rs["title"])
    for k in (s["def"].get("gate") or {}).get("covers", []):
        cs = stages.get(k)
        if cs and (cs["status"] not in LOCKED or cs["stale"]):
            blocks.append("本门覆盖的阶段“%s”未通过或已失效" % cs["title"])
    strict = bool(config.get("strict_completeness"))
    core = CORE_SECTIONS.get(s["key"], set())
    incomplete = []          # progressive completion: unfilled supplementary items only warn (listed here and in warns)
    for c in s["def"]["checklist"]:
        it = d.get("checklist", {}).get(c["key"], {})
        st = it.get("status", "todo")
        if c.get("required") and st == "todo":
            if strict:
                blocks.append("检查项未完成：%s" % c["text"])
            else:
                incomplete.append("检查项尚未勾选：%s" % c["text"])
        if st == "na" and not (it.get("note") or "").strip():
            blocks.append("检查项标记“不适用”须填写理由：%s" % c["text"])
        if st == "done" and c.get("evidence") and not (it.get("note") or "").strip():
            blocks.append("检查项需填写证据说明：%s" % c["text"])
    unc = set(d.get("unconfirmed") or [])
    for sec in s["def"]["sections"]:
        val = d.get("sections", {}).get(sec["key"])
        if sec["key"] in unc:
            # template pre-fill nobody has confirmed: the core of a step blocks submission, other sections warn
            msg = "模板预置内容尚未确认：%s（请逐项核对并修改后点击“确认本节”）" % sec["title"]
            if strict or sec["key"] in core:
                blocks.append(msg)
            else:
                incomplete.append(msg)
            continue
        if sec.get("required") and not _section_filled(sec, val):
            if sec["type"] == "table":
                msg = "必填表格“%s”至少需要 %d 行有效内容" % (sec["title"], max(1, sec.get("min_rows", 1)))
            else:
                msg = "必填章节未填写：%s" % sec["title"]
            if strict or sec["key"] in core:
                blocks.append(msg)                      # core content of the step must exist before it can be reviewed
            else:
                incomplete.append(msg)
    thr, sthr = config.get("rpn_threshold"), config.get("severity_threshold")
    if s["key"] == "risk":
        for r in _dict_rows(d.get("sections", {}).get("fmea")):
            if _blank(r):
                continue
            trio = _sod(r)
            if trio is None:
                blocks.append("FMEA 行“%s”的 S/O/D 未填写完整" % (r.get("mode") or "?"))
                continue
            S_, O_, D_ = trio
            if not all(1 <= v <= 10 for v in trio):
                blocks.append("FMEA 行“%s”的 S/O/D 需在 1–10" % (r.get("mode") or "?"))
                continue
            rpn = S_ * O_ * D_
            if (rpn >= thr or S_ >= sthr) and not (r.get("control") or "").strip():
                blocks.append("FMEA 高风险项“%s”（RPN=%d，S=%d）必须填写控制措施" % (r.get("mode") or "?", rpn, S_))
    if s["key"] == "atp":
        for r in _dict_rows(d.get("sections", {}).get("criteria")):
            if not _blank(r) and not re.search(r"\d", str(r.get("criterion") or "")):
                warns.append("ATP 判据“%s”不含数值，建议用统计区间表达" % (r.get("characteristic") or "?"))
    if s["key"] == "plan":
        exps = conn.execute("SELECT code, design, acceptance, status FROM experiments WHERE method_id=? AND status!='cancelled'", (mid,)).fetchall()
        if not exps:
            blocks.append("尚未在“实验”页登记任何实验")
        for e in exps:
            if not (e["design"] or "").strip() or not (e["acceptance"] or "").strip():
                blocks.append("实验 %s 缺少设计或接受标准" % e["code"])
            elif SAMPLE_WORD in (e["design"] or "") or SAMPLE_WORD in (e["acceptance"] or ""):
                # after approval the design / criteria are frozen, so unconfirmed example criteria must be dealt with before
                blocks.append("实验 %s 的设计或接受标准仍含“%s”标记：请核对并改为本产品的判据（或在实验页点“确认示例值”）" % (e["code"], SAMPLE_WORD))
        fm = [r for r in _dict_rows(stages["risk"]["data"].get("sections", {}).get("fmea")) if not _blank(r)] if "risk" in stages else []
        high = [r for r in fm if _is_high(r)]
        if high:
            warns.append("有 %d 个高风险 FMEA 项，请确认已映射到具体实验" % len(high))
    # E2: example values of the template that were never replaced (any wording containing “示例值”), at every step
    scope = [s] + [stages[k] for k in (s["def"].get("gate") or {}).get("covers", []) if k in stages]
    in_stages = {x["title"]: _marked_items(x["data"].get("sections", {})) for x in scope}
    in_stages = {k: v for k, v in in_stages.items() if v}
    n_exp = 0
    if s["key"] in ("plan", "report"):
        n_exp = conn.execute("SELECT COUNT(*) FROM experiments WHERE method_id=? AND status!='cancelled' AND acceptance LIKE ?",
                             (mid, "%" + SAMPLE_WORD + "%")).fetchone()[0]
    if in_stages or n_exp:
        warns.append("仍有 %d 处内容带有“%s”标记（%s；实验接受标准 %d 个）：请核对并按 ATP 确认或修改，确认后删去标记"
                     % (sum(in_stages.values()) + n_exp, SAMPLE_WORD,
                        "、".join("%s %d 处" % kv for kv in in_stages.items()) or "各阶段章节 0 处", n_exp))
    exps = conn.execute("SELECT code, status, conclusion, deviations, results FROM experiments WHERE method_id=? AND stage_key=?", (mid, s["key"])).fetchall()
    if s["key"] not in ("plan",):
        for e in exps:
            for r in db.jl(e["results"], []):
                if isinstance(r, dict) and r.get("auto") == "不符合" and (r.get("verdict") or "") != "不符合":
                    warns.append("实验 %s 的结果“%s”：系统按判据自动判定为“不符合”，但人工判定为“%s”，请核对并在结论/偏离中说明" % (e["code"], r.get("metric") or "?", r.get("verdict") or "未填"))
            if e["status"] in ("planned", "running"):
                blocks.append("实验 %s 尚未完成或取消" % e["code"])
            elif e["status"] == "done" and not (e["conclusion"] or "").strip():
                blocks.append("实验 %s 已完成但缺少结论" % e["code"])
            elif e["status"] == "cancelled" and not (e["deviations"] or "").strip():
                blocks.append("实验 %s 已取消，须在“偏离/说明”中写明原因" % e["code"])
    from . import records                    # (records imports this module; imported here to avoid a cycle)
    dev_blocks, dev_warns = records.open_blocking(conn, mid, s["key"])
    blocks.extend(dev_blocks)
    warns.extend(dev_warns)
    gate = s["def"].get("gate")
    if gate:
        for role in gate["roles"]:
            if not _eligible(conn, mid, role, s):
                blocks.append("方法团队中没有可用的%s（须是方法成员、具备相应全局角色，且从未编辑/保存/提交过本阶段）" % ROLE_LABELS[role])
    if incomplete:
        warns.insert(0, "尚有 %d 项补充内容未填写（不阻止提交，但会向复核人显示，并在文档中标为【待填写】）" % len(incomplete))
    return {"blocks": blocks, "warns": warns, "incomplete": incomplete}


# Core content per step: these required items must exist before a step can be submitted for review.  Every other
# required item only warns ("progressive completion") unless config strict_completeness=true.
CORE_SECTIONS = {
    "charter": {"objective"},
    "atp": {"use", "attribute", "criteria"},
    "tech": {"matrix", "decision"},
    "risk": {"fmea"},
    "plan": {"phases"},
    "control": {"sst"},
    "report": {"summary", "verdict", "vs_atp"},
}


def _marked_items(sections):
    """Number of table rows / texts / field groups of a stage that still carry the template's example-value tag."""
    n = 0
    for v in (sections or {}).values():
        if isinstance(v, list):
            n += sum(1 for r in v if has_mark(json.dumps(r, ensure_ascii=False)))
        elif v and has_mark(json.dumps(v, ensure_ascii=False)):
            n += 1
    return n


def _is_high(r):
    trio = _sod(r)
    if trio is None:
        return False
    S_, O_, D_ = trio
    return S_ * O_ * D_ >= config.get("rpn_threshold") or S_ >= config.get("severity_threshold")


# ------------------------------------------------------------------ gate actions
def notify(conn, user_ids, actor_id, kind, mid, stage_key, title, body=""):
    """In-app notification for each user (never for the actor, de-duplicated)."""
    seen = set()
    for uid in user_ids:
        if uid is None or uid == actor_id or uid in seen:
            continue
        seen.add(uid)
        cur = conn.execute("INSERT INTO notifications(user_id,created_at,kind,method_id,stage_key,title,body) VALUES(?,?,?,?,?,?,?)",
                           (uid, db.now(), kind, mid, stage_key, str(title)[:200], str(body or "")[:1000]))
        notifier.enqueue(cur.lastrowid)            # e-mail / webhook, only when configured; sent after the commit


def _team_ids(conn, mid, roles):
    q = ",".join("?" * len(roles))
    return [r["user_id"] for r in conn.execute(
        "SELECT DISTINCT mm.user_id FROM method_members mm JOIN users u ON u.id=mm.user_id WHERE mm.method_id=? AND mm.role IN (%s) AND u.active=1" % q,
        [mid] + list(roles))]


def _notify_next_signer(conn, user, p, s):
    nxt = _next_role(conn, s)
    if nxt:
        notify(conn, _eligible(conn, p["id"], nxt, s), user["id"], "review_requested", p["id"], s["key"],
               "待您%s：%s｜%s" % ("批准" if nxt == "approver" else "复核", p["code"], s["def"]["title"]),
               "方法 %s 的“%s”已提交，请打开该阶段审阅并签署。" % (p["name"], s["def"]["title"]))


def submit_stage(conn, user, mid, key, comment=""):
    p = get_method(conn, mid)
    s = get_stage(conn, mid, key)
    require_edit(conn, user, mid)
    why = method_writable_reason(conn, p)
    if why:
        raise WFError(why, 409)
    if s["status"] not in EDITABLE:
        raise WFError("当前状态不可提交", 409)
    comment = validate.text(comment, "提交说明", 2000)
    chk = gate_checks(conn, p, s)
    if chk["blocks"]:
        raise WFError("未满足提交条件", 422, chk)
    _add_contributor(conn, mid, key, user["id"], current=False)          # the submitter counts as a contributor
    s = get_stage(conn, mid, key)
    h = stage_hash(conn, mid, s)
    conn.execute("INSERT INTO stage_revisions(stage_id,revision,data,data_hash,created_by,created_at,reason,hv) VALUES(?,?,?,?,?,?,?,?)",
                 (s["id"], s["revision"], json.dumps(s["data"], ensure_ascii=False), h, user["id"], db.now(), comment, HASH_V))
    gate = s["def"].get("gate")
    if gate:
        conn.execute("UPDATE stages SET status='in_review', submitted_at=?, updated_at=? WHERE id=?", (db.now(), db.now(), s["id"]))
        _notify_next_signer(conn, user, p, get_stage(conn, mid, key))
        audit.log(conn, user, "stage.submit", "stage", s["id"], mid, {"stage": key, "revision": s["revision"], "hash": h, "warnings": chk["warns"],
                                                                      "incomplete": chk.get("incomplete", [])}, comment)
    else:
        conn.execute("UPDATE stages SET status='completed', actual_end=?, submitted_at=?, updated_at=? WHERE id=?",
                     (_iso_date(_today()), db.now(), db.now(), s["id"]))
        audit.log(conn, user, "stage.complete", "stage", s["id"], mid, {"stage": key, "revision": s["revision"], "hash": h,
                                                                       "incomplete": chk.get("incomplete", [])}, comment)
    return get_stage(conn, mid, key)


def withdraw_stage(conn, user, mid, key, reason):
    s = get_stage(conn, mid, key)
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    if s["status"] != "in_review":
        raise WFError("仅“待复核”状态可撤回", 409)
    reason = validate.text(reason, "撤回原因", 2000)
    if not reason.strip():
        raise WFError("撤回须填写原因")
    conn.execute("UPDATE stages SET status='in_progress', revision=revision+1, editors='[]', updated_at=? WHERE id=?", (db.now(), s["id"]))
    audit.log(conn, user, "stage.withdraw", "stage", s["id"], mid, {"stage": key, "revision": s["revision"]}, reason)


def pending_role_for(conn, user, p, s):
    """Which role can `user` sign next on this stage (or None) and why not."""
    if s["status"] != "in_review":
        return None, "阶段不在待复核状态"
    why = method_writable_reason(conn, p)
    if why:
        return None, why
    nxt = _next_role(conn, s)
    if not nxt:
        return None, "已完成全部签署"
    roles = method_roles(conn, p["id"], user["id"])
    if nxt not in roles:
        return None, "当前需要“%s”签署" % ROLE_LABELS[nxt]
    if nxt not in user["roles"]:
        return None, "您的账号不具备全局角色“%s”" % ROLE_LABELS[nxt]
    if user["id"] in s["contributors"]:
        return None, "您编辑/保存/提交过本阶段内容，不得复核/批准（职责分离）"
    prior = {r["user_id"] for r in conn.execute("SELECT user_id FROM reviews WHERE stage_id=? AND revision=?", (s["id"], s["revision"]))}
    if user["id"] in prior:
        return None, "同一版本中同一人不得重复签署"
    return nxt, ""


def check_binding(conn, mid, s, revision, expected_hash):
    """H5: the signature must be bound to what the reviewer actually looked at."""
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise WFError("签名请求须带 revision（整数）")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise WFError("签名请求须带 expected_hash")
    if revision != s["revision"] or expected_hash != current_hash(conn, mid, s):
        raise WFError("内容已更新，请刷新后重新审阅", 409)


def review_stage(conn, user, mid, key, decision, comment, revision=None, expected_hash=None):
    """Caller must have run auth.reauthenticate() immediately before (separate tx)."""
    p = get_method(conn, mid)
    s = get_stage(conn, mid, key)
    role, why = pending_role_for(conn, user, p, s)
    if not role:
        raise WFError(why, 403)
    if decision not in ("approve", "reject"):
        raise WFError("决定无效")
    comment = validate.text(comment, "意见", 5000)
    if decision == "reject" and not comment.strip():
        raise WFError("退回须填写原因")
    check_binding(conn, mid, s, revision, expected_hash)
    snap = _snapshot(conn, s["id"], s["revision"])
    h = stage_hash(conn, mid, s, snap["hv"] if snap else HASH_V)
    if not snap or snap["data_hash"] != h:
        raise WFError("提交后数据与快照不一致，无法签署", 409)
    meaning = {"reviewer": "复核：我已审阅本阶段内容，确认其完整、准确并符合方案要求" if decision == "approve" else "复核：退回，需修改",
               "approver": "批准：我批准本阶段内容及其结论" if decision == "approve" else "批准：退回，需修改"}[role]
    conn.execute("INSERT INTO reviews(method_id,stage_id,revision,role,user_id,decision,comment,signed_at,data_hash,meaning) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (mid, s["id"], s["revision"], role, user["id"], decision, comment, db.now(), h, meaning))
    if decision == "reject":
        conn.execute("UPDATE stages SET status='returned', revision=revision+1, editors='[]', updated_at=? WHERE id=?", (db.now(), s["id"]))
        audit.log(conn, user, "stage.reject", "stage", s["id"], mid, {"stage": key, "revision": s["revision"], "role": role, "hash": h}, comment)
        notify(conn, _team_ids(conn, mid, ("owner", "author")) + list(s["contributors"]), user["id"], "returned", mid, key,
               "已被退回：%s｜%s" % (p["code"], s["def"]["title"]), "%s 退回：%s" % (user["display_name"], comment))
    else:
        audit.log(conn, user, "stage.sign", "stage", s["id"], mid, {"stage": key, "revision": s["revision"], "role": role, "hash": h}, comment)
        if _next_role(conn, s) is None:
            conn.execute("UPDATE stages SET status='approved', actual_end=?, stale=0, updated_at=? WHERE id=?", (_iso_date(_today()), db.now(), s["id"]))
            audit.log(conn, user, "stage.approved", "stage", s["id"], mid, {"stage": key, "revision": s["revision"]})
            notify(conn, _team_ids(conn, mid, ("owner", "author")) + list(s["contributors"]), user["id"], "approved", mid, key,
                   "已通过：%s｜%s" % (p["code"], s["def"]["title"]), "该阶段已通过评审并锁定，下一步已开放。")
        else:
            _notify_next_signer(conn, user, p, s)
    return get_stage(conn, mid, key)


def _dependents(conn, mid, key):
    """L4: transitive closure of the stages that (directly or indirectly) require / are covered by `key`."""
    stages = list_stages(conn, mid)
    seen, frontier, out = {key}, [key], []
    while frontier:
        k = frontier.pop(0)
        for x in stages:
            if x["key"] in seen:
                continue
            gate = x["def"].get("gate") or {}
            if k in x["def"].get("requires", []) or k in gate.get("covers", []):
                seen.add(x["key"])
                out.append(x)
                frontier.append(x["key"])
    return out


def reopen_stage(conn, user, mid, key, reason):
    """Caller must have run auth.reauthenticate() before. Invalidates dependants (transitively)."""
    p = get_method(conn, mid)
    s = get_stage(conn, mid, key)
    roles = method_roles(conn, mid, user["id"])
    if not (roles & {"owner", "approver"}):
        raise WFError("仅方法负责人或批准人可重新打开已通过的阶段", 403)
    if s["status"] not in LOCKED:
        raise WFError("仅已通过/已完成的阶段可重新打开", 409)
    reason = validate.text(reason, "原因", 2000)
    if not reason.strip():
        raise WFError("重新打开须填写原因")
    why = method_writable_reason(conn, p)
    if why:
        raise WFError(why, 409)
    conn.execute("UPDATE stages SET status='in_progress', revision=revision+1, editors='[]', stale=0, actual_end=NULL, updated_at=? WHERE id=?", (db.now(), s["id"]))
    affected = []
    for dpt in _dependents(conn, mid, key):
        if dpt["status"] in LOCKED:
            conn.execute("UPDATE stages SET stale=1, updated_at=? WHERE id=?", (db.now(), dpt["id"]))
            affected.append({"stage": dpt["key"], "effect": "已失效(需重新复核)"})
        elif dpt["status"] == "in_review":
            conn.execute("UPDATE stages SET status='returned', revision=revision+1, editors='[]', updated_at=? WHERE id=?", (db.now(), dpt["id"]))
            affected.append({"stage": dpt["key"], "effect": "待复核被退回"})
    audit.log(conn, user, "stage.reopen", "stage", s["id"], mid, {"stage": key, "revision": s["revision"], "affected": affected}, reason)
    pm = get_method(conn, mid)
    notify(conn, _team_ids(conn, mid, ("owner", "author", "reviewer", "approver")), user["id"], "reopened", mid, key,
           "已重新打开：%s｜%s" % (pm["code"], s["def"]["title"]), "%s 重新打开：%s" % (user["display_name"], reason))
    return affected


def recertify_stage(conn, user, mid, key, comment=""):
    """A stale approved stage is re-submitted for review without changing content (new revision)."""
    get_method(conn, mid)
    s = get_stage(conn, mid, key)
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    if not s["stale"]:
        raise WFError("该阶段未失效", 409)
    # new revision, editors reset (content unchanged), then a normal submission for review
    conn.execute("UPDATE stages SET status='in_progress', revision=revision+1, editors='[]', stale=0, actual_end=NULL WHERE id=?", (s["id"],))
    return submit_stage(conn, user, mid, key, comment or "失效后重新提交复核")   # a WFError rolls the revision bump back


def reschedule(conn, user, mid, from_stage, start_date):
    """Shift the planned dates of `from_stage` and every later stage that is not locked, one after the other by their
    planned number of weeks, starting at `start_date`; unfinished experiments follow their stage's dates."""
    p = get_method(conn, mid)
    require_edit(conn, user, mid)
    why = method_writable_reason(conn, p)
    if why:
        raise WFError(why, 409)
    start = validate.date_or_none(start_date, "开始日期")
    if not start:
        raise WFError("请提供开始日期")
    stages = list_stages(conn, mid)
    keys = [x["key"] for x in stages]
    if from_stage not in keys:
        raise WFError("未知阶段")
    cursor = dt.date.fromisoformat(start)
    moved = []
    for st in stages[keys.index(from_stage):]:
        if st["status"] in LOCKED:
            continue
        end = cursor + dt.timedelta(weeks=int(st["def"].get("weeks") or 1)) - dt.timedelta(days=1)
        conn.execute("UPDATE stages SET planned_start=?, planned_end=?, updated_at=? WHERE id=?", (_iso_date(cursor), _iso_date(end), db.now(), st["id"]))
        conn.execute("UPDATE experiments SET planned_start=?, planned_end=?, updated_at=? WHERE method_id=? AND stage_key=? AND status IN ('planned','running')",
                     (_iso_date(cursor), _iso_date(end), db.now(), mid, st["key"]))
        moved.append({"stage": st["key"], "planned_start": _iso_date(cursor), "planned_end": _iso_date(end)})
        cursor = end + dt.timedelta(days=1)
    if moved:
        conn.execute("UPDATE methods SET planned_end=?, updated_at=? WHERE id=?", (moved[-1]["planned_end"], db.now(), mid))
    audit.log(conn, user, "method.reschedule", "method", mid, mid, {"from_stage": from_stage, "start": start, "moved": moved})
    return moved


# ------------------------------------------------------------------ experiments
EXP_STATUS = {"planned": "计划中", "running": "进行中", "done": "已完成", "cancelled": "已取消"}
_PLAN_FROZEN_MSG = "开发方案已提交/批准，实验的名称/目的/设计/接受标准/所属阶段已冻结；需先重新打开方案阶段，或在“偏离/说明”中记录"


def _exp_lock(conn, e):
    if not e["stage_key"]:
        return False
    s = conn.execute("SELECT status FROM stages WHERE method_id=? AND key=?", (e["method_id"], e["stage_key"])).fetchone()
    return bool(s and s["status"] in FROZEN)


def _plan_frozen(conn, mid):
    s = conn.execute("SELECT status FROM stages WHERE method_id=? AND key='plan'", (mid,)).fetchone()
    return bool(s and s["status"] in FROZEN)


def list_experiments(conn, mid):
    out = []
    for e in conn.execute("SELECT * FROM experiments WHERE method_id=? ORDER BY id", (mid,)):
        d = dict(e)
        d["results"] = db.jl(d["results"], [])
        d["locked"] = _exp_lock(conn, d)
        d["attachments"] = conn.execute("SELECT COUNT(*) FROM attachments WHERE experiment_id=? AND deleted=0", (d["id"],)).fetchone()[0]
        out.append(d)
    return out


def get_experiment(conn, eid):
    e = conn.execute("SELECT * FROM experiments WHERE id=?", (eid,)).fetchone()
    if not e:
        raise WFError("实验不存在", 404)
    d = dict(e)
    d["results"] = db.jl(d["results"], [])
    d["locked"] = _exp_lock(conn, d)
    return d


def _touch_editor(conn, mid, stage_key, uid):
    _add_contributor(conn, mid, stage_key, uid, current=True)


def _check_target_stage(conn, mid, stage_key, what):
    """The stage an experiment / attachment is assigned to must exist and be editable."""
    if not isinstance(stage_key, str):
        raise WFError("stage_key 必须是文本")
    st = get_stage(conn, mid, stage_key)      # 404 if it does not exist
    if st["status"] in FROZEN:
        raise WFError("所属阶段已锁定/待复核，不能%s" % what, 409)
    return st


def _check_owner(conn, mid, owner_id):
    if owner_id is None:
        return None
    if isinstance(owner_id, bool) or not isinstance(owner_id, int):
        raise WFError("owner_id 必须是整数")
    if not method_roles(conn, mid, owner_id):
        raise WFError("实验负责人必须是方法团队成员")
    return owner_id


def create_experiment(conn, user, mid, d):
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    title = validate.text(d.get("title"), "实验名称", 200, required=True).strip()
    stage_key = d.get("stage_key") or None
    if stage_key:
        _check_target_stage(conn, mid, stage_key, "新增实验")
    code = d.get("code")
    code = validate.text(code, "实验编号", 50).strip() if code is not None else ""
    objective = validate.text(d.get("objective"), "目的", 20000)
    design = validate.text(d.get("design"), "设计", 20000)
    acceptance = validate.text(d.get("acceptance"), "接受标准", 20000)
    ps = validate.date_or_none(d.get("planned_start"), "计划开始日期")
    pe = validate.date_or_none(d.get("planned_end"), "计划结束日期")
    owner = _check_owner(conn, mid, d.get("owner_id")) if d.get("owner_id") is not None else user["id"]
    if not code:
        n = conn.execute("SELECT COUNT(*) FROM experiments WHERE method_id=?", (mid,)).fetchone()[0] + 1
        code = "EXP-%02d" % n
        while conn.execute("SELECT 1 FROM experiments WHERE method_id=? AND code=?", (mid, code)).fetchone():
            n += 1; code = "EXP-%02d" % n
    if conn.execute("SELECT 1 FROM experiments WHERE method_id=? AND code=?", (mid, code)).fetchone():
        raise WFError("实验编号已存在")
    late = 1 if _plan_frozen(conn, mid) else 0          # H3: added after the plan was submitted/approved
    if late and not (design.strip() and acceptance.strip()):
        # the plan gate blocks on an experiment without design / acceptance criterion, so refuse it up front
        raise WFError("开发方案已提交/批准，其后新增的实验必须填写“设计”和“接受标准”（否则方案阶段无法重新复核）", 400)
    cur = conn.execute(
        "INSERT INTO experiments(method_id,stage_key,code,title,objective,design,acceptance,planned_start,planned_end,status,owner_id,created_at,updated_at,added_after_plan)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, stage_key, code, title, objective, design, acceptance, ps, pe, "planned", owner, db.now(), db.now(), late))
    _touch_editor(conn, mid, stage_key, user["id"])
    audit.log(conn, user, "experiment.create", "experiment", cur.lastrowid, mid,
              {"code": code, "title": title, "stage": stage_key, "added_after_plan": bool(late)})
    return cur.lastrowid


_SAMPLE_TAG_RE = re.compile(r"[（(]\s*示例值[^）)]*[）)]|示例值[，,；;]?\s*须按\s*ATP\s*确认[。.]?|示例值[，,；;]?\s*须按[^。；;）)\n]*确认[。.]?|示例值")


def confirm_experiment_examples(conn, user, e):
    """The user states that the example design / acceptance criteria of an experiment were checked and fit the
    product: the template's example marker is removed from design / objective / acceptance (recorded in the audit).
    Goes through update_experiment, so every freeze rule of the approved plan applies."""
    texts = {k: (e.get(k) or "") for k in ("objective", "design", "acceptance")}
    new = {k: _SAMPLE_TAG_RE.sub("", v).strip(" ；;，,") for k, v in texts.items()}
    if all(new[k] == texts[k].strip(" ；;，,") or SAMPLE_WORD not in texts[k] for k in texts):
        raise WFError("该实验没有“%s”标记" % SAMPLE_WORD)
    d = {"version": e["version"]}
    d.update({k: new[k] for k in texts if new[k] != texts[k]})
    update_experiment(conn, user, e["id"], d)


def _with_auto(row):
    """Adds the machine verdict of a result row: its criterion (e.g. "≥5", "90–110%") is evaluated against its value."""
    r = {k: v for k, v in row.items() if k != "auto"}
    a = stats.evaluate(r.get("criterion"), r.get("value"))
    if a:
        r["auto"] = a
    return r


def update_experiment(conn, user, eid, d):
    e = get_experiment(conn, eid)
    mid = e["method_id"]
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    if not isinstance(d, dict):
        raise WFError("请求格式不正确")
    if e["locked"]:
        raise WFError("所属阶段已锁定/待复核，实验记录不可修改", 409)
    version = validate.integer(d.get("version", -1), "version")
    if version != e["version"]:
        raise WFError("内容已被他人更新（版本冲突），请刷新", 409)
    new = {}
    for k, name, mx in (("title", "实验名称", 200), ("objective", "目的", 20000), ("design", "设计", 20000), ("acceptance", "接受标准", 20000),
                        ("conclusion", "结论", 20000), ("deviations", "偏离/说明", 20000)):
        if k in d:
            new[k] = validate.text(d[k], name, mx, required=(k == "title"))
    for k in ("planned_start", "planned_end"):
        if k in d:
            new[k] = validate.date_or_none(d[k], "计划日期")
    if "owner_id" in d:
        new["owner_id"] = _check_owner(conn, mid, d["owner_id"])
    if "stage_key" in d:
        sk = d["stage_key"] or None
        if sk != e["stage_key"]:
            if sk is None:
                raise WFError("实验一旦分配到阶段，所属阶段不可置空", 409)
            _check_target_stage(conn, mid, sk, "接收该实验")         # new stage must exist and be editable
            new["stage_key"] = sk
    if "results" in d:
        new["results"] = [_with_auto(r) for r in validate.results(d["results"])]
    if not e["added_after_plan"] and _plan_frozen(conn, mid):
        frozen = [k for k in ("title", "objective", "design", "acceptance", "stage_key") if k in new and new[k] != e[k]]
        if frozen:
            raise WFError(_PLAN_FROZEN_MSG, 409)
    changes = {}
    sets, vals = [], []
    for k, v in new.items():
        if k == "results":
            if v != e["results"]:
                changes["results"] = {"old": _short(e["results"]), "new": _short(v)}
                sets.append("results=?"); vals.append(json.dumps(v, ensure_ascii=False))
        elif v != e[k]:
            changes[k] = {"old": _short(e[k], 1500), "new": _short(v, 1500)}
            sets.append("%s=?" % k); vals.append(v)
    if not sets:
        return
    sets += ["version=version+1", "updated_at=?"]
    vals += [db.now(), eid]
    conn.execute("UPDATE experiments SET %s WHERE id=?" % ",".join(sets), vals)
    _touch_editor(conn, mid, e["stage_key"], user["id"])
    if new.get("stage_key"):
        _touch_editor(conn, mid, new["stage_key"], user["id"])
    audit.log(conn, user, "experiment.update", "experiment", eid, mid, {"code": e["code"], "changes": changes})


def set_experiment_status(conn, user, eid, status, reason=""):
    e = get_experiment(conn, eid)
    mid = e["method_id"]
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    if not isinstance(status, str) or status not in EXP_STATUS:
        raise WFError("无效状态")
    reason = validate.text(reason, "原因", 2000)
    if e["locked"]:
        raise WFError("所属阶段已锁定/待复核，不能变更实验状态", 409)
    old = e["status"]
    allowed = {("planned", "running"), ("running", "done"), ("planned", "cancelled"), ("running", "cancelled"), ("done", "running"), ("cancelled", "planned")}
    if (old, status) not in allowed:
        raise WFError("不允许从“%s”变更为“%s”" % (EXP_STATUS[old], EXP_STATUS[status]))
    if status == "running":
        plan = conn.execute("SELECT status, stale FROM stages WHERE method_id=? AND key='plan'", (mid,)).fetchone()
        if plan and plan["status"] != "approved":
            raise WFError("开发方案尚未批准，不得开始实验（先完成 GP 方案批准）", 409)
        if plan and plan["stale"]:
            raise WFError("开发方案已失效，须重新复核后才能开始实验", 409)
    if status == "done" and not (e["conclusion"] or "").strip():
        raise WFError("完成实验须先填写结论")
    if status == "cancelled" and not reason.strip():
        raise WFError("取消实验须填写原因")
    if (old, status) == ("done", "running") and not reason.strip():
        raise WFError("重新打开已完成的实验须填写原因")
    ex = {"actual_start": e["actual_start"], "actual_end": e["actual_end"], "deviations": e["deviations"]}
    if status == "running" and not ex["actual_start"]:
        ex["actual_start"] = _iso_date(_today())
    if status == "done":
        ex["actual_end"] = _iso_date(_today())
    if status == "running":
        ex["actual_end"] = None
    if status == "cancelled":
        ex["deviations"] = ((e["deviations"] or "") + "\n取消原因：" + reason).strip()
    conn.execute("UPDATE experiments SET status=?, actual_start=?, actual_end=?, deviations=?, version=version+1, updated_at=? WHERE id=?",
                 (status, ex["actual_start"], ex["actual_end"], ex["deviations"], db.now(), eid))
    _touch_editor(conn, mid, e["stage_key"], user["id"])
    audit.log(conn, user, "experiment.status", "experiment", eid, mid, {"code": e["code"], "from": old, "to": status}, reason)


def delete_experiment(conn, user, eid, reason):
    e = get_experiment(conn, eid)
    require_edit(conn, user, e["method_id"])
    require_active_method(conn, e["method_id"])
    if e["locked"]:
        raise WFError("所属阶段已锁定/待复核", 409)
    if e["status"] in ("running", "done"):
        raise WFError("已开始的实验不能删除，请改为“取消”并说明原因", 409)
    if not e["added_after_plan"] and _plan_frozen(conn, e["method_id"]):
        raise WFError("开发方案已提交/批准，方案内的实验不能删除；请改为“取消”并说明原因，或先重新打开方案阶段", 409)
    reason = validate.text(reason, "删除原因", 2000)
    if not reason.strip():
        raise WFError("删除须填写原因")
    conn.execute("DELETE FROM experiments WHERE id=?", (eid,))
    _touch_editor(conn, e["method_id"], e["stage_key"], user["id"])
    audit.log(conn, user, "experiment.delete", "experiment", eid, e["method_id"], {"code": e["code"], "title": e["title"]}, reason)


# ------------------------------------------------------------------ attachments
def _safe_name(n):
    n = os.path.basename((n or "file").replace("\\", "/")).strip().replace("\x00", "")
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", n)[:120]
    return n or "file"


def check_attachment_target(conn, user, mid, stage_key, experiment_id):
    """Permission / lock checks for adding an attachment (run before streaming the body and again in the
    committing transaction).  Returns the stage the upload counts towards (for contributors)."""
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    stage_for = stage_key
    if stage_key:
        _check_target_stage(conn, mid, stage_key, "新增附件")
    if experiment_id:
        e = get_experiment(conn, experiment_id)
        if e["method_id"] != mid:
            raise WFError("实验不属于该方法")
        if e["locked"]:
            raise WFError("所属阶段已锁定/待复核，不能新增附件", 409)
        stage_for = stage_for or e["stage_key"]
    return stage_for


def _file_sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add_attachment_file(conn, user, mid, stage_key, experiment_id, filename, tmp_path, size, sha, description=""):
    """Commit an already-uploaded temp file as an attachment (the caller streamed it and computed size/sha)."""
    stage_for = check_attachment_target(conn, user, mid, stage_key, experiment_id)
    if size <= 0:
        raise WFError("文件为空")
    if size > config.get("max_upload_mb") * 1024 * 1024:
        raise WFError("文件超过 %d MB 限制" % config.get("max_upload_mb"), 413)
    description = validate.text(description, "附件说明", 2000)
    name = _safe_name(filename)
    folder = config.UPLOADS / str(mid)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("%s_%s" % (sha[:16], name))
    i = 1
    while path.exists() and _file_sha(path) != sha:       # never overwrite an existing (possibly altered) file
        i += 1
        path = folder / ("%s_%d_%s" % (sha[:16], i, name))
    if path.exists():
        os.remove(str(tmp_path))
    else:
        os.replace(str(tmp_path), str(path))
    cur = conn.execute(
        "INSERT INTO attachments(method_id,stage_key,experiment_id,filename,size,sha256,path,description,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (mid, stage_key or None, experiment_id or None, name, size, sha, str(path.relative_to(config.DATA)), description, user["id"], db.now()))
    _touch_editor(conn, mid, stage_for, user["id"])
    audit.log(conn, user, "attachment.add", "attachment", cur.lastrowid, mid, {"filename": name, "size": size, "sha256": sha, "stage": stage_key, "experiment": experiment_id})
    return cur.lastrowid


def list_attachments(conn, mid, stage_key=None, experiment_id=None):
    q = "SELECT a.*, u.display_name AS uploader FROM attachments a LEFT JOIN users u ON u.id=a.uploaded_by WHERE a.method_id=? AND a.deleted=0"
    args = [mid]
    if stage_key:
        q += " AND a.stage_key=?"; args.append(stage_key)
    if experiment_id:
        q += " AND a.experiment_id=?"; args.append(experiment_id)
    return [{k: v for k, v in dict(r).items() if k != "path"} for r in conn.execute(q + " ORDER BY a.id", args)]


def get_attachment(conn, aid):
    a = conn.execute("SELECT * FROM attachments WHERE id=? AND deleted=0", (aid,)).fetchone()
    if not a:
        raise WFError("附件不存在", 404)
    return dict(a)


def delete_attachment(conn, user, aid, reason):
    a = get_attachment(conn, aid)
    mid = a["method_id"]
    require_edit(conn, user, mid)
    require_active_method(conn, mid)
    reason = validate.text(reason, "删除原因", 2000)
    if not reason.strip():
        raise WFError("删除附件须填写原因")
    stage_for = a["stage_key"]
    if a["stage_key"]:
        st = get_stage(conn, mid, a["stage_key"])
        if st["status"] in FROZEN:
            raise WFError("所属阶段已锁定/待复核，附件不可删除", 409)
    if a["experiment_id"]:
        e = conn.execute("SELECT * FROM experiments WHERE id=?", (a["experiment_id"],)).fetchone()
        if e:
            if _exp_lock(conn, dict(e)):
                raise WFError("附件所属实验的阶段已锁定/待复核，附件不可删除", 409)
            stage_for = stage_for or e["stage_key"]
    conn.execute("UPDATE attachments SET deleted=1, deleted_by=?, deleted_at=?, delete_reason=? WHERE id=?", (user["id"], db.now(), reason, aid))
    _touch_editor(conn, mid, stage_for, user["id"])
    audit.log(conn, user, "attachment.delete", "attachment", aid, mid, {"filename": a["filename"], "sha256": a["sha256"]}, reason)


def verify_attachment(a):
    p = config.DATA / a["path"]
    if not p.exists():
        return False
    return _file_sha(p) == a["sha256"]


# ------------------------------------------------------------------ stage detail for UI
def stage_detail(conn, user, p, s):
    mid = p["id"]
    chk = gate_checks(conn, p, s)
    role, why = pending_role_for(conn, user, p, s)
    reviews = []
    for r in conn.execute("SELECT r.*, u.display_name FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.stage_id=? ORDER BY r.id", (s["id"],)):
        reviews.append({k: r[k] for k in ("id", "revision", "role", "decision", "comment", "signed_at", "data_hash", "meaning", "display_name")})
    snap = conn.execute("SELECT revision, data_hash, created_at FROM stage_revisions WHERE stage_id=? ORDER BY id", (s["id"],)).fetchall()
    cur_hash = current_hash(conn, mid, s)
    intact, problems = _signature_eval(conn, mid, s)
    for r in reviews:
        r["role_label"] = ROLE_LABELS.get(r["role"], r["role"])
        r["intact"] = bool(intact.get(r["id"], False))
    is_editor_role = can_edit(conn, user, mid)
    blockers = stage_blockers(conn, mid, s)
    editable = (is_editor_role and s["status"] in EDITABLE and method_writable_reason(conn, p) is None and not blockers)
    proj = get_project(conn, p["project_id"])
    d = dict(s)
    d["method"] = {"id": mid, "code": p["code"], "name": p["name"], "status": p["status"], "lifecycle": p["lifecycle"]}
    d["project"] = {"id": proj["id"], "code": proj["code"], "name": proj["name"]}
    d["status_label"] = STATUS_LABELS[s["status"]]
    d["progress"] = stage_progress(conn, mid, s)
    d["checks"] = chk
    d["next_role"] = _next_role(conn, s) if s["status"] == "in_review" else None
    d["can_sign_as"] = role
    d["cannot_sign_reason"] = why if s["status"] == "in_review" else ""
    d["editable"] = editable
    d["can_submit"] = is_editor_role and s["status"] in EDITABLE and not blockers
    d["blocked_by"] = [{"step": b[0], "title": b[1]} for b in blockers]
    d["can_withdraw"] = is_editor_role and s["status"] == "in_review"
    d["can_reopen"] = bool(method_roles(conn, mid, user["id"]) & {"owner", "approver"}) and s["status"] in LOCKED
    d["can_recertify"] = is_editor_role and s["stale"]
    d["reviews"] = reviews
    d["revisions"] = [dict(r) for r in snap]
    d["hash"] = cur_hash
    d["experiments"] = [e for e in list_experiments(conn, mid) if e["stage_key"] == s["key"]]
    d["attachments"] = list_attachments(conn, mid, stage_key=s["key"])
    d["editor_names"] = _names(conn, s["editors"])
    d["contributors_names"] = _names(conn, s["contributors"])
    d["signatures_ok"] = not problems
    d["signature_problems"] = problems
    return d


# ------------------------------------------------------------------ method / project views
def method_row(conn, user, m, project=None):
    """One method as listed by GET /api/methods, GET /api/projects/{pid}/methods and the dashboard."""
    summ = method_summary(conn, m)
    uid = user["id"]
    if project is None:
        project = get_project(conn, m["project_id"])
    return {"id": m["id"], "code": m["code"], "name": m["name"],
            "project_id": m["project_id"], "project_code": project["code"], "project_name": project["name"],
            "technique": m["template_key"], "technique_label": (m.get("meta") or {}).get("template_label", m["template_key"]),
            "template_version": m["template_version"],
            "analyte": m["analyte"] or "", "matrix": m["matrix"] or "", "intended_use": m["intended_use"] or "", "phase": m["phase"] or "",
            "method_version": m["method_version"], "lifecycle": m["lifecycle"], "lifecycle_label": LIFECYCLE_LABELS.get(m["lifecycle"], m["lifecycle"]),
            "status": m["status"], "status_label": METHOD_STATUS_LABELS.get(m["status"], m["status"]),
            "planned_start": m["planned_start"], "planned_end": m["planned_end"],
            "owner_id": m["owner_id"], "owner_name": _user_name(conn, m["owner_id"]), "updated_at": m["updated_at"],
            "my_roles": sorted(method_roles(conn, m["id"], uid)), "my_project_roles": sorted(project_roles(conn, m["project_id"], uid)),
            "progress": summ["progress"], "current_stage": summ["current_stage"], "overdue": summ["overdue"], "stale": summ["stale"]}


def visible_methods(conn, user, project_id=None, status=None, technique=None, lifecycle=None):
    """Methods the user may see (method member OR project member OR admin), newest activity first."""
    where, args = [], []
    if "admin" not in user["roles"]:
        where.append("(m.id IN (SELECT method_id FROM method_members WHERE user_id=?) OR m.project_id IN (SELECT project_id FROM project_members WHERE user_id=?))")
        args += [user["id"], user["id"]]
    for col, val in (("project_id", project_id), ("status", status), ("template_key", technique), ("lifecycle", lifecycle)):
        if val not in (None, ""):
            where.append("m.%s=?" % col)
            args.append(val)
    sql = "SELECT m.* FROM methods m" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY m.updated_at DESC, m.id DESC"
    return [_loadm(r) for r in conn.execute(sql, args)]


def list_methods(conn, user, q="", status="", project_id=None, technique="", lifecycle=""):
    projects = {}
    out = []
    ql = (q or "").strip().lower()
    for m in visible_methods(conn, user, project_id or None, status, technique, lifecycle):
        proj = projects.get(m["project_id"]) or projects.setdefault(m["project_id"], get_project(conn, m["project_id"]))
        if ql and ql not in " ".join([m["code"], m["name"], m["analyte"] or "", m["matrix"] or "", proj["code"], proj["name"]]).lower():
            continue
        out.append(method_row(conn, user, m, proj))
    return out


def project_row(conn, user, p):
    ms = [_loadm(r) for r in conn.execute("SELECT * FROM methods WHERE project_id=? ORDER BY id", (p["id"],))]
    live = [(m, method_summary(conn, m)) for m in ms if m["status"] != "cancelled"]
    return {"id": p["id"], "code": p["code"], "name": p["name"], "product": p["product"] or "", "indication": p["indication"] or "",
            "phase": p["phase"] or "", "description": p["description"] or "", "status": p["status"],
            "status_label": PROJECT_STATUS_LABELS.get(p["status"], p["status"]),
            "planned_start": p["planned_start"], "planned_end": p["planned_end"],
            "owner_id": p["owner_id"], "owner_name": _user_name(conn, p["owner_id"]), "created_at": p["created_at"], "updated_at": p["updated_at"],
            "my_roles": sorted(project_roles(conn, p["id"], user["id"])),
            "method_count": len(ms),
            "progress": int(sum(s["progress"] for _, s in live) / len(live)) if live else 0,
            "overdue": [m["code"] for m, s in live if s["overdue"]],
            "stale": [m["code"] for m, s in live if s["stale"]]}


def visible_projects(conn, user, status=None):
    where, args = [], []
    if "admin" not in user["roles"]:
        where.append("id IN (SELECT project_id FROM project_members WHERE user_id=?)")
        args.append(user["id"])
    if status:
        where.append("status=?")
        args.append(status)
    sql = "SELECT * FROM projects" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, args)]


def list_projects(conn, user, q="", status=""):
    ql = (q or "").strip().lower()
    out = []
    for p in visible_projects(conn, user, status):
        if ql and ql not in " ".join([p["code"], p["name"], p["product"] or "", p["indication"] or ""]).lower():
            continue
        out.append(project_row(conn, user, p))
    return out


def stage_diff(conn, mid, key, rev_from=None, rev_to=None):
    """Section-level difference between two submitted revisions of a stage (default: the last two snapshots).
    Reviewers use it to see what changed after a rejection.  Revisions are the numbers shown in the stage history."""
    s = get_stage(conn, mid, key)
    snaps = {}
    for r in conn.execute("SELECT revision, data FROM stage_revisions WHERE stage_id=? ORDER BY id", (s["id"],)):
        snaps[r["revision"]] = db.jl(r["data"], {})
    revs = sorted(snaps)
    if rev_to is None:
        rev_to = revs[-1] if revs else None
    if rev_to not in snaps:
        return {"from": None, "to": rev_to, "revisions": revs, "changes": [], "note": "没有可比较的已提交修订"}
    if rev_from is None:
        earlier = [r for r in revs if r < rev_to]
        rev_from = earlier[-1] if earlier else None
    if rev_from is None or rev_from not in snaps:
        return {"from": None, "to": rev_to, "revisions": revs, "changes": [], "note": "这是第一次提交，没有更早的修订可比较"}
    a, b = snaps[rev_from].get("sections", {}), snaps[rev_to].get("sections", {})
    titles = {x["key"]: x for x in s["def"]["sections"]}
    changes = []
    for k, sec in titles.items():
        old, new = a.get(k), b.get(k)
        if old == new:
            continue
        ch = {"key": k, "title": sec["title"], "type": sec["type"]}
        if isinstance(old, list) or isinstance(new, list):
            old_l = old if isinstance(old, list) else []
            new_l = new if isinstance(new, list) else []
            rows = []
            for i in range(max(len(old_l), len(new_l))):
                o = old_l[i] if i < len(old_l) else None
                n = new_l[i] if i < len(new_l) else None
                if o != n:
                    rows.append({"row": i + 1, "old": o, "new": n})
            ch["rows"] = rows
        elif isinstance(old, dict) or isinstance(new, dict):
            old_d = old if isinstance(old, dict) else {}
            new_d = new if isinstance(new, dict) else {}
            ch["fields"] = [{"key": f, "old": old_d.get(f), "new": new_d.get(f)} for f in sorted(set(old_d) | set(new_d)) if old_d.get(f) != new_d.get(f)]
        else:
            ch["old"], ch["new"] = old, new
        changes.append(ch)
    ca, cb = snaps[rev_from].get("checklist", {}), snaps[rev_to].get("checklist", {})
    cl_changed = [c["text"] for c in s["def"]["checklist"]
                  if (ca.get(c["key"]) or {}).get("status") != (cb.get(c["key"]) or {}).get("status")
                  or (ca.get(c["key"]) or {}).get("note", "") != (cb.get(c["key"]) or {}).get("note", "")]
    return {"from": rev_from, "to": rev_to, "revisions": revs, "changes": changes, "checklist_changed": cl_changed, "note": ""}


def project_detail(conn, user, p):
    pid = p["id"]
    out = project_row(conn, user, p)
    members = [dict(r) for r in conn.execute(
        "SELECT m.user_id, m.role, u.display_name, u.username, u.active FROM project_members m JOIN users u ON u.id=m.user_id "
        "WHERE m.project_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'member' THEN 1 ELSE 2 END, u.display_name", (pid,))]
    for m in members:
        m["role_label"] = PROJECT_ROLE_LABELS[m["role"]]
        m["active"] = bool(m["active"])
    out["members"] = members
    is_owner = "owner" in out["my_roles"]
    out["permissions"] = {"can_edit": is_owner, "can_manage_members": is_owner,
                          "can_create_method": bool({"owner", "member"} & set(out["my_roles"])) and bool({"author", "admin"} & set(user["roles"]))
                          and p["status"] == "active"}
    return out


def project_methods(conn, user, pid):
    """All methods of a project (every project member sees all of them) with the integrity flag of their signatures."""
    p = get_project(conn, pid)
    out = []
    for r in conn.execute("SELECT * FROM methods WHERE project_id=? ORDER BY id", (pid,)).fetchall():
        m = _loadm(r)
        row = method_row(conn, user, m, p)
        ok, bad = method_signatures(conn, m["id"])
        row["signatures_ok"] = ok
        out.append(row)
    return out


def method_detail(conn, user, m):
    mid = m["id"]
    stages = list_stages(conn, mid)
    members = [dict(r) for r in conn.execute(
        "SELECT mm.user_id, mm.role, u.display_name, u.username, u.active FROM method_members mm JOIN users u ON u.id=mm.user_id "
        "WHERE mm.method_id=? ORDER BY mm.role, u.display_name", (mid,))]
    for x in members:
        x["role_label"] = ROLE_LABELS[x["role"]]
        x["active"] = bool(x["active"])
    proj = get_project(conn, m["project_id"])
    mroles = method_roles(conn, mid, user["id"])
    proles = project_roles(conn, m["project_id"], user["id"])
    out = dict(m)
    out["project"] = {"id": proj["id"], "code": proj["code"], "name": proj["name"], "status": proj["status"]}
    out["technique_label"] = m["meta"].get("template_label", m["template_key"])
    out["status_label"] = METHOD_STATUS_LABELS.get(m["status"], m["status"])
    out["lifecycle_label"] = LIFECYCLE_LABELS.get(m["lifecycle"], m["lifecycle"])
    out["owner_name"] = _user_name(conn, m["owner_id"])
    out["revision_of_info"] = None
    if m.get("revision_of"):
        ro = conn.execute("SELECT id, code, name, method_version FROM methods WHERE id=?", (m["revision_of"],)).fetchone()
        out["revision_of_info"] = dict(ro) if ro else None
    out["revisions"] = [dict(r) for r in conn.execute("SELECT id, code, method_version, status, revision_note FROM methods WHERE revision_of=? ORDER BY id", (m["id"],))]
    out["summary"] = method_summary(conn, m)
    out["stages"] = [{"key": s["key"], "title": s["title"] if "title" in s else s["def"]["title"], "ord": s["ord"], "status": s["status"],
                      "status_label": STATUS_LABELS[s["status"]], "stale": s["stale"], "revision": s["revision"],
                      "gate": (s["def"].get("gate") or {}).get("name"), "gate_roles": (s["def"].get("gate") or {}).get("roles", []),
                      "planned_start": s["planned_start"], "planned_end": s["planned_end"], "actual_start": s["actual_start"], "actual_end": s["actual_end"],
                      "progress": stage_progress(conn, mid, s), "desc": s["def"].get("desc", ""),
                      "blocked_by": [{"step": b[0], "title": b[1]} for b in stage_blockers(conn, mid, s)]} for s in stages]
    out["members"] = members
    out["my_roles"] = sorted(mroles)
    out["my_project_roles"] = sorted(proles)
    admin = "admin" in user["roles"]
    out["permissions"] = {"can_edit_info": "owner" in mroles,
                          "can_manage_members": "owner" in mroles or "owner" in proles,
                          "can_change_lifecycle": bool(mroles & {"owner", "approver"}),
                          "can_generate_docs": admin or bool(mroles & {"owner", "author", "reviewer", "approver"}),
                          "can_edit_content": bool(mroles & EDIT_ROLES) and method_writable_reason(conn, m) is None}
    ok, bad = method_signatures(conn, mid)
    out["signatures_ok"] = ok
    out["bad_signatures"] = bad
    return out


# ------------------------------------------------------------------ dashboard
def dashboard(conn, user):
    """{projects, methods, to_review, my_stages, my_experiments} - see docs/前端契约.md for every field."""
    uid = user["id"]
    to_review, mine, exps = [], [], []
    today = _iso_date(_today())
    projects = [project_row(conn, user, p) for p in visible_projects(conn, user)]
    methods = []
    projs = {}
    for m in visible_methods(conn, user):
        proj = projs.get(m["project_id"]) or projs.setdefault(m["project_id"], get_project(conn, m["project_id"]))
        row = method_row(conn, user, m, proj)
        methods.append(row)
        if method_writable_reason(conn, m) is not None:
            continue
        roles = set(row["my_roles"])
        ref = {"method_id": m["id"], "method_code": m["code"], "method": m["name"], "project_code": proj["code"]}
        for s in list_stages(conn, m["id"]):
            role, _ = pending_role_for(conn, user, m, s)
            if role:
                to_review.append(dict(ref, stage_key=s["key"], stage=s["def"]["title"], role=role, role_label=ROLE_LABELS[role]))
            if {"owner", "author"} & roles and s["status"] in EDITABLE + ("in_review",):
                if s["status"] == "not_started":
                    if stage_blockers(conn, m["id"], s):
                        continue                    # not open yet: not a to-do (the prerequisite step is)
                    label = "可以开始"
                else:
                    label = STATUS_LABELS[s["status"]]
                mine.append(dict(ref, stage_key=s["key"], stage=s["def"]["title"], status=s["status"], status_label=label,
                                 planned_end=s["planned_end"], overdue=bool(s["planned_end"] and s["planned_end"] < today)))
            if s["stale"] and roles:           # a task for the method team, not for project members who merely read
                to_review.append(dict(ref, stage_key=s["key"], stage=s["def"]["title"], role="stale", role_label="已失效，需重新提交复核"))
    for e in conn.execute("SELECT e.id, e.method_id, e.code, e.title, e.status, e.planned_end, m.code AS mcode, m.name AS mname, p.code AS pcode "
                          "FROM experiments e JOIN methods m ON m.id=e.method_id JOIN projects p ON p.id=m.project_id "
                          "WHERE e.owner_id=? AND e.status IN ('planned','running') AND m.status='active' AND p.status='active' "
                          "AND (e.status='running' OR EXISTS(SELECT 1 FROM stages st WHERE st.method_id=e.method_id AND st.key='plan' AND st.status='approved')) "
                          "ORDER BY e.planned_end", (uid,)):
        exps.append({"id": e["id"], "method_id": e["method_id"], "code": e["code"], "method_code": e["mcode"], "method": e["mname"],
                     "project_code": e["pcode"], "title": e["title"], "status": e["status"], "status_label": EXP_STATUS[e["status"]],
                     "planned_end": e["planned_end"], "overdue": bool(e["planned_end"] and e["planned_end"] < today)})
    return {"projects": projects, "methods": methods, "to_review": to_review, "my_stages": mine, "my_experiments": exps}


# ------------------------------------------------------------------ knowledge base
def kb_for(conn, p, stage_key=None):
    tech = p["template_key"]
    out = []
    for r in conn.execute("SELECT * FROM kb_items WHERE active=1 ORDER BY kind, id"):
        d = dict(r)
        d["tags"] = db.jl(d["tags"], []); d["techniques"] = db.jl(d["techniques"], []); d["stages"] = db.jl(d["stages"], [])
        if d["techniques"] and tech not in d["techniques"] and "all" not in d["techniques"]:
            continue
        if stage_key and d["stages"] and stage_key not in d["stages"]:
            continue
        out.append(d)
    return out


def sync_builtin_kb(conn):
    """E5: insert the built-in knowledge-base items (kb_seed.SEED) whose TITLE is not in the table yet.  A title
    that exists in any state - user-created, edited, deactivated - is never touched or resurrected, so running
    this again is a no-op.  Returns {"added": n, "existing": m, "total": len(SEED)}."""
    from . import kb_seed
    have = {r["title"] for r in conn.execute("SELECT title FROM kb_items")}
    added = 0
    for it in kb_seed.SEED:
        if it["title"] in have:
            continue
        conn.execute("INSERT INTO kb_items(kind,title,body,tags,techniques,stages,source,builtin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)",
                     (it["kind"], it["title"], it["body"], json.dumps(it["tags"], ensure_ascii=False), json.dumps(it["techniques"]),
                      json.dumps(it["stages"]), it["source"], db.now(), db.now()))
        have.add(it["title"])
        added += 1
    return {"added": added, "existing": len(kb_seed.SEED) - added, "total": len(kb_seed.SEED)}


def add_lesson(conn, user, p, title, body, stage_key=None):
    require_edit(conn, user, p["id"])
    title = validate.text(title, "标题", 200, required=True)
    body = validate.text(body, "内容", 50000, required=True)
    if stage_key is not None and not isinstance(stage_key, str):
        raise WFError("stage_key 必须是文本")
    cur = conn.execute("INSERT INTO kb_items(kind,title,body,tags,techniques,stages,source,origin_method_id,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       ("lesson", title, body, json.dumps(["经验教训"]), json.dumps([p["template_key"]]),
                        json.dumps([stage_key] if stage_key else []), "方法 %s" % p["code"], p["id"], user["id"], db.now(), db.now()))
    audit.log(conn, user, "kb.lesson", "kb", cur.lastrowid, p["id"], {"title": title})
    return cur.lastrowid


# ------------------------------------------------------------------ backup (M6)
_SHA_CACHE_NAME = ".sha_cache.json"


def _files_manifest():
    """sha256 of every file under uploads/ and documents/.  Hashes are cached by (size, mtime) so a
    backup does not re-read gigabytes that have not changed."""
    cache_path = config.BACKUPS / _SHA_CACHE_NAME
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    out, new_cache = {}, {}
    for folder in (config.UPLOADS, config.DOCS):
        for dirpath, _dirs, files in os.walk(str(folder)):
            for f in files:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, str(config.DATA)).replace("\\", "/")
                if "/.tmp/" in "/" + rel:
                    continue
                try:
                    stt = os.stat(full)
                except OSError:
                    continue
                c = cache.get(rel)
                if c and c[0] == stt.st_size and c[1] == stt.st_mtime_ns:
                    sha = c[2]
                else:
                    try:
                        sha = _file_sha(full)
                    except OSError:
                        continue
                new_cache[rel] = [stt.st_size, stt.st_mtime_ns, sha]
                out[rel] = {"size": stt.st_size, "sha256": sha}
    try:
        cache_path.write_text(json.dumps(new_cache), encoding="utf-8")
    except OSError:
        pass
    return out


def _backup_label(name):
    parts = name[:-3].split("_", 3) if name.endswith(".db") else []
    return re.sub(r"\d+$", "", parts[3]) if len(parts) > 3 else "other"


def backup_now(label="manual"):
    """Online SQLite backup + integrity check + side-car manifest (audit head, schema, file hashes).
    Startup backups are retained separately from daily / manual ones."""
    config.ensure_dirs()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = config.BACKUPS / ("methodflow_%s_%s.db" % (stamp, label))
    n = 1
    while dest.exists():
        n += 1
        dest = config.BACKUPS / ("methodflow_%s_%s.db" % (stamp, "%s%d" % (label, n)))
    src = sqlite3.connect(str(config.DB_PATH))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    chk = sqlite3.connect("file:%s?mode=ro&immutable=1" % dest.as_posix(), uri=True)
    chk.row_factory = sqlite3.Row
    try:
        ic = chk.execute("PRAGMA integrity_check").fetchone()[0]
        ver = chk.execute("PRAGMA user_version").fetchone()[0]
        head = audit.compute_head(chk) if ic == "ok" else None
    finally:
        chk.close()
    if ic != "ok":
        bad = dest.with_name(dest.name + ".corrupt")
        os.replace(str(dest), str(bad))
        raise RuntimeError("备份未通过 PRAGMA integrity_check（%s），已标记为 %s" % (ic, bad.name))
    manifest = {"created": db.now(), "db": dest.name, "label": label, "integrity_check": ic, "schema_version": ver,
                "audit_head": head, "files": _files_manifest()}
    mp = dest.with_name(dest.name + ".manifest.json")
    tmp = str(mp) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False)
    os.replace(tmp, str(mp))
    groups = {}
    for f in sorted(config.BACKUPS.glob("methodflow_*.db")):
        groups.setdefault(_backup_label(f.name), []).append(f)
    for lab, files in groups.items():
        keep = config.get("backup_keep_startup") if lab == "startup" else config.get("backup_keep")
        for f in files[:-keep] if keep > 0 else files:
            for victim in (f, f.with_name(f.name + ".manifest.json")):
                try:
                    victim.unlink()
                except OSError:
                    pass
    return dest.name


def list_backups():
    return [{"name": f.name, "size": f.stat().st_size, "mtime": dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
             "manifest": f.with_name(f.name + ".manifest.json").exists()}
            for f in sorted(config.BACKUPS.glob("methodflow_*.db"), reverse=True)]


def export_method(conn, mid):
    m = get_method(conn, mid)
    ok, bad = method_signatures(conn, mid)
    return {"method": m, "project": get_project(conn, m["project_id"]), "stages": list_stages(conn, mid),
            "experiments": list_experiments(conn, mid), "attachments": list_attachments(conn, mid),
            "reviews": [dict(r) for r in conn.execute("SELECT * FROM reviews WHERE method_id=? ORDER BY id", (mid,))],
            "audit": [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE method_id=? ORDER BY id", (mid,))],
            "signatures_ok": ok, "bad_signatures": bad,
            "exported_at": db.now()}
