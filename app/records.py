"""Records beside the workflow: material / equipment registry, run records and deviations.

  materials / equipment   a registry shared by all methods (batch numbers, expiry, calibration)
  runs                    one record per execution of an experiment: date, analyst, equipment, materials, outcome;
                          a second person verifies it (never the analyst)
  deviations              deviations from the plan with classification, impact, root cause, action and a closure that
                          needs an electronic signature of a person other than the opener

Runs and deviations are append-only in spirit: nothing is deleted, edits are audited, and a run that was verified is
frozen.  Open major / critical deviations of a step block its submission (see workflow.gate_checks).
"""
import datetime as dt
import json

from . import audit, db, validate, workflow
from .workflow import WFError

MATERIAL_KINDS = {"reagent": "试剂", "reference": "参比品", "standard": "标准品", "consumable": "耗材", "cell": "细胞/生物材料", "other": "其他"}
MATERIAL_STATUS = {"active": "可用", "quarantine": "隔离", "expired": "已过期", "retired": "停用"}
EQUIPMENT_STATUS = {"active": "在用", "out_of_service": "停用待修", "retired": "报废"}
RUN_OUTCOMES = {"valid": "有效", "invalid": "无效", "aborted": "中止"}
DEV_CLASS = {"minor": "轻微", "major": "主要", "critical": "严重"}
DEV_STATUS = {"open": "未关闭", "investigating": "调查中", "closed": "已关闭"}
SOON_DAYS = 30


def _today():
    return dt.date.today()


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _require_registry_writer(user):
    if not ({"author", "admin", "approver"} & set(user["roles"])):
        raise WFError("维护试剂/仪器台账需要“开发人员”“批准人”或管理员角色", 403)


def _enum(v, allowed, label):
    if not isinstance(v, str) or v not in allowed:
        raise validate.Invalid("%s无效" % label)
    return v


def _next_code(conn, table, prefix, where="", args=()):
    n = conn.execute("SELECT COUNT(*) FROM %s %s" % (table, where), args).fetchone()[0] + 1
    while conn.execute("SELECT 1 FROM %s WHERE code=? %s" % (table, ("AND " + where[6:]) if where else ""), (("%s%04d" % (prefix, n),) + tuple(args))).fetchone():
        n += 1
    return "%s%04d" % (prefix, n)


# ------------------------------------------------------------------ materials
def material_state(m):
    e = _d(m["expiry_at"])
    if not e:
        return "none"
    left = (e - _today()).days
    return "expired" if left < 0 else ("soon" if left <= SOON_DAYS else "ok")


def _material_row(r):
    d = dict(r)
    d["critical"] = bool(d["critical"])
    d["active"] = bool(d["active"])
    d["kind_label"] = MATERIAL_KINDS.get(d["kind"], d["kind"])
    d["status_label"] = MATERIAL_STATUS.get(d["status"], d["status"])
    d["expiry_state"] = material_state(d)
    return d


def list_materials(conn, q="", kind="", state="", all_=False):
    out = []
    ql = (q or "").lower()
    for r in conn.execute("SELECT * FROM materials %s ORDER BY name, lot, id" % ("" if all_ else "WHERE active=1")):
        d = _material_row(r)
        if kind and d["kind"] != kind:
            continue
        if state and d["expiry_state"] != state:
            continue
        if ql and ql not in " ".join(str(d[k]) for k in ("code", "name", "supplier", "catalog_no", "lot", "notes")).lower():
            continue
        out.append(d)
    return out


def _material_fields(d, partial=False):
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    out = {}
    if "name" in d or not partial:
        out["name"] = validate.text(d.get("name"), "名称", 200, required=True)
    for k, label, n in (("supplier", "供应商", 200), ("catalog_no", "货号", 100), ("lot", "批号", 100), ("grade", "规格/等级", 100),
                        ("concentration", "浓度", 100), ("storage", "储存条件", 200), ("notes", "备注", 2000)):
        if k in d or not partial:
            out[k] = validate.text(d.get(k, ""), label, n)
    if "kind" in d or not partial:
        out["kind"] = _enum(d.get("kind", "reagent"), MATERIAL_KINDS, "类别")
    if "status" in d or not partial:
        out["status"] = _enum(d.get("status", "active"), MATERIAL_STATUS, "状态")
    for k, label in (("received_at", "接收日期"), ("expiry_at", "效期")):
        if k in d or not partial:
            out[k] = validate.date_or_none(d.get(k), label)
    if "critical" in d or not partial:
        out["critical"] = 1 if validate.boolean(d.get("critical", False), "关键试剂") else 0
    return out


def create_material(conn, user, d):
    _require_registry_writer(user)
    f = _material_fields(d)
    code = _next_code(conn, "materials", "MAT-")
    cur = conn.execute("INSERT INTO materials(code,name,kind,supplier,catalog_no,lot,grade,concentration,storage,received_at,expiry_at,critical,status,notes,active,created_by,created_at,updated_at) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                       (code, f["name"], f["kind"], f["supplier"], f["catalog_no"], f["lot"], f["grade"], f["concentration"], f["storage"], f["received_at"], f["expiry_at"],
                        f["critical"], f["status"], f["notes"], user["id"], db.now(), db.now()))
    audit.log(conn, user, "material.create", "material", cur.lastrowid, None, {"code": code, "name": f["name"], "lot": f["lot"]})
    return cur.lastrowid


def update_material(conn, user, mid, d):
    _require_registry_writer(user)
    old = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    if not old:
        raise WFError("材料不存在", 404)
    f = _material_fields(d, partial=True)
    ch = {k: {"old": old[k], "new": v} for k, v in f.items() if old[k] != v}
    if ch:
        conn.execute("UPDATE materials SET %s, updated_at=? WHERE id=?" % ",".join("%s=?" % k for k in f), list(f.values()) + [db.now(), mid])
        audit.log(conn, user, "material.update", "material", mid, None, {"code": old["code"], "changes": ch})


def set_material_active(conn, user, mid, active):
    _require_registry_writer(user)
    if not conn.execute("SELECT 1 FROM materials WHERE id=?", (mid,)).fetchone():
        raise WFError("材料不存在", 404)
    conn.execute("UPDATE materials SET active=?, updated_at=? WHERE id=?", (1 if active else 0, db.now(), mid))
    audit.log(conn, user, "material.restore" if active else "material.deactivate", "material", mid, None, {})


# ------------------------------------------------------------------ equipment
def calibration_state(e):
    due = _d(e["calibration_due"])
    if not due:
        return "none"
    left = (due - _today()).days
    return "overdue" if left < 0 else ("soon" if left <= SOON_DAYS else "ok")


def _equipment_row(r):
    d = dict(r)
    d["active"] = bool(d["active"])
    d["status_label"] = EQUIPMENT_STATUS.get(d["status"], d["status"])
    d["calibration_state"] = calibration_state(d)
    return d


def list_equipment(conn, q="", state="", all_=False):
    out = []
    ql = (q or "").lower()
    for r in conn.execute("SELECT * FROM equipment %s ORDER BY name, id" % ("" if all_ else "WHERE active=1")):
        d = _equipment_row(r)
        if state and d["calibration_state"] != state:
            continue
        if ql and ql not in " ".join(str(d[k]) for k in ("code", "name", "model", "serial_no", "location", "notes")).lower():
            continue
        out.append(d)
    return out


def _equipment_fields(d, partial=False):
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    out = {}
    if "name" in d or not partial:
        out["name"] = validate.text(d.get("name"), "名称", 200, required=True)
    for k, label, n in (("model", "型号", 100), ("serial_no", "序列号/资产号", 100), ("location", "位置", 100), ("notes", "备注", 2000)):
        if k in d or not partial:
            out[k] = validate.text(d.get(k, ""), label, n)
    if "status" in d or not partial:
        out["status"] = _enum(d.get("status", "active"), EQUIPMENT_STATUS, "状态")
    for k, label in (("last_calibration", "上次校准日期"), ("calibration_due", "校准到期日")):
        if k in d or not partial:
            out[k] = validate.date_or_none(d.get(k), label)
    return out


def create_equipment(conn, user, d):
    _require_registry_writer(user)
    f = _equipment_fields(d)
    code = _next_code(conn, "equipment", "EQ-")
    cur = conn.execute("INSERT INTO equipment(code,name,model,serial_no,location,last_calibration,calibration_due,status,notes,active,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?)",
                       (code, f["name"], f["model"], f["serial_no"], f["location"], f["last_calibration"], f["calibration_due"], f["status"], f["notes"], user["id"], db.now(), db.now()))
    audit.log(conn, user, "equipment.create", "equipment", cur.lastrowid, None, {"code": code, "name": f["name"]})
    return cur.lastrowid


def update_equipment(conn, user, eid, d):
    _require_registry_writer(user)
    old = conn.execute("SELECT * FROM equipment WHERE id=?", (eid,)).fetchone()
    if not old:
        raise WFError("仪器不存在", 404)
    f = _equipment_fields(d, partial=True)
    ch = {k: {"old": old[k], "new": v} for k, v in f.items() if old[k] != v}
    if ch:
        conn.execute("UPDATE equipment SET %s, updated_at=? WHERE id=?" % ",".join("%s=?" % k for k in f), list(f.values()) + [db.now(), eid])
        audit.log(conn, user, "equipment.update", "equipment", eid, None, {"code": old["code"], "changes": ch})


def set_equipment_active(conn, user, eid, active):
    _require_registry_writer(user)
    if not conn.execute("SELECT 1 FROM equipment WHERE id=?", (eid,)).fetchone():
        raise WFError("仪器不存在", 404)
    conn.execute("UPDATE equipment SET active=?, updated_at=? WHERE id=?", (1 if active else 0, db.now(), eid))
    audit.log(conn, user, "equipment.restore" if active else "equipment.deactivate", "equipment", eid, None, {})


def registry_alerts(conn):
    """Materials expiring within 30 days / already expired and equipment whose calibration is due or overdue."""
    mats = [m for m in list_materials(conn) if m["expiry_state"] in ("expired", "soon") and m["status"] == "active"]
    eqs = [e for e in list_equipment(conn) if e["calibration_state"] in ("overdue", "soon") and e["status"] == "active"]
    return {"materials": [{"id": m["id"], "code": m["code"], "name": m["name"], "lot": m["lot"], "expiry_at": m["expiry_at"], "state": m["expiry_state"], "critical": m["critical"]} for m in mats],
            "equipment": [{"id": e["id"], "code": e["code"], "name": e["name"], "calibration_due": e["calibration_due"], "state": e["calibration_state"]} for e in eqs]}


# ------------------------------------------------------------------ runs
def _ids(v, label):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > 100 or any(isinstance(i, bool) or not isinstance(i, int) for i in v):
        raise validate.Invalid("%s必须是编号列表" % label)
    return sorted(set(v))


def run_warnings(conn, run_date, equipment_ids, material_ids):
    """Facts a reviewer must see: expired material, overdue calibration, non-usable status on the run date."""
    day = _d(run_date) or _today()
    w = []
    for i in material_ids:
        m = conn.execute("SELECT * FROM materials WHERE id=?", (i,)).fetchone()
        if not m:
            raise validate.Invalid("材料 #%d 不存在" % i)
        e = _d(m["expiry_at"])
        if e and e < day:
            w.append("材料 %s（%s，批号 %s）在运行日已过期（效期 %s）" % (m["code"], m["name"], m["lot"] or "—", m["expiry_at"]))
        if m["status"] in ("quarantine", "expired", "retired"):
            w.append("材料 %s（%s）状态为“%s”" % (m["code"], m["name"], MATERIAL_STATUS.get(m["status"], m["status"])))
    for i in equipment_ids:
        q = conn.execute("SELECT * FROM equipment WHERE id=?", (i,)).fetchone()
        if not q:
            raise validate.Invalid("仪器 #%d 不存在" % i)
        due = _d(q["calibration_due"])
        if due and due < day:
            w.append("仪器 %s（%s）在运行日校准已到期（%s）" % (q["code"], q["name"], q["calibration_due"]))
        if q["status"] != "active":
            w.append("仪器 %s（%s）状态为“%s”" % (q["code"], q["name"], EQUIPMENT_STATUS.get(q["status"], q["status"])))
    return w


def _run_row(conn, r, names):
    d = dict(r)
    d["equipment"] = db.jl(d["equipment"], [])
    d["materials"] = db.jl(d["materials"], [])
    d["analyst_name"] = names.get(d["analyst_id"], "")
    d["verified_name"] = names.get(d["verified_by"], "")
    d["outcome_label"] = RUN_OUTCOMES.get(d["outcome"], d["outcome"])
    d["equipment_items"] = [{"id": i, "label": _label(conn, "equipment", i)} for i in d["equipment"]]
    d["material_items"] = [{"id": i, "label": _label(conn, "materials", i)} for i in d["materials"]]
    d["warnings"] = run_warnings(conn, d["run_date"], [i for i in d["equipment"] if _exists(conn, "equipment", i)], [i for i in d["materials"] if _exists(conn, "materials", i)])
    d["verified"] = bool(d["verified_by"])
    exp = conn.execute("SELECT code, stage_key FROM experiments WHERE id=?", (d["experiment_id"],)).fetchone() if d["experiment_id"] else None
    d["experiment_code"] = exp["code"] if exp else ""
    return d


def _exists(conn, table, i):
    return conn.execute("SELECT 1 FROM %s WHERE id=?" % table, (i,)).fetchone() is not None


def _label(conn, table, i):
    r = conn.execute("SELECT code, name" + (", lot" if table == "materials" else "") + " FROM %s WHERE id=?" % table, (i,)).fetchone()
    if not r:
        return "#%d" % i
    return "%s %s%s" % (r["code"], r["name"], (" / " + r["lot"]) if table == "materials" and r["lot"] else "")


def _names(conn):
    return {r["id"]: r["display_name"] for r in conn.execute("SELECT id, display_name FROM users")}


def list_runs(conn, mid, experiment_id=None):
    names = _names(conn)
    q, args = "SELECT * FROM runs WHERE method_id=?", [mid]
    if experiment_id:
        q += " AND experiment_id=?"
        args.append(experiment_id)
    return [_run_row(conn, r, names) for r in conn.execute(q + " ORDER BY id", args)]


def _check_experiment(conn, mid, eid):
    if eid in (None, 0):
        return None
    if isinstance(eid, bool) or not isinstance(eid, int):
        raise validate.Invalid("experiment_id 必须是整数")
    e = conn.execute("SELECT * FROM experiments WHERE id=?", (eid,)).fetchone()
    if not e or e["method_id"] != mid:
        raise WFError("实验不属于该方法", 404)
    if workflow._exp_lock(conn, dict(e)):
        raise WFError("所属阶段已锁定/待复核，不能新增或修改该实验的运行记录", 409)
    return e


def create_run(conn, user, mid, d):
    p = workflow.get_method(conn, mid)
    workflow.require_edit(conn, user, mid)
    workflow.require_active_method(conn, mid)
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    e = _check_experiment(conn, mid, d.get("experiment_id"))
    run_date = validate.date_or_none(d.get("run_date"), "运行日期") or workflow._iso_date(workflow._today())
    analyst = d.get("analyst_id", user["id"])
    if isinstance(analyst, bool) or not isinstance(analyst, int) or not conn.execute("SELECT 1 FROM users WHERE id=? AND active=1", (analyst,)).fetchone():
        raise validate.Invalid("分析员不存在或已停用")
    eq, mt = _ids(d.get("equipment"), "仪器"), _ids(d.get("materials"), "材料")
    warns = run_warnings(conn, run_date, eq, mt)
    outcome = _enum(d.get("outcome", "valid"), RUN_OUTCOMES, "结果状态")
    summary = validate.text(d.get("summary", ""), "运行摘要", 5000)
    n = conn.execute("SELECT COUNT(*) FROM runs WHERE method_id=?", (mid,)).fetchone()[0] + 1
    code = "RUN-%03d" % n
    cur = conn.execute("INSERT INTO runs(method_id,experiment_id,code,run_date,analyst_id,equipment,materials,outcome,summary,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (mid, e["id"] if e else None, code, run_date, analyst, json.dumps(eq), json.dumps(mt), outcome, summary, user["id"], db.now(), db.now()))
    if e:
        workflow._touch_editor(conn, mid, e["stage_key"], user["id"])
    audit.log(conn, user, "run.create", "run", cur.lastrowid, mid, {"code": code, "experiment": e["code"] if e else None, "outcome": outcome, "warnings": warns})
    return cur.lastrowid


def update_run(conn, user, rid, d):
    r = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
    if not r:
        raise WFError("运行记录不存在", 404)
    mid = r["method_id"]
    workflow.require_edit(conn, user, mid)
    workflow.require_active_method(conn, mid)
    if r["verified_by"]:
        raise WFError("该运行记录已被第二人核对，不能修改", 409)
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    if validate.integer(d.get("version", -1), "version") != r["version"]:
        raise WFError("内容已被他人更新（版本冲突），请刷新后重试", 409)
    if r["experiment_id"]:
        _check_experiment(conn, mid, r["experiment_id"])
    sets, vals, ch = [], [], {}

    def put(k, v, old):
        if v != old:
            sets.append("%s=?" % k)
            vals.append(v)
            ch[k] = {"old": old, "new": v}
    if "run_date" in d:
        put("run_date", validate.date_or_none(d["run_date"], "运行日期"), r["run_date"])
    if "outcome" in d:
        put("outcome", _enum(d["outcome"], RUN_OUTCOMES, "结果状态"), r["outcome"])
    if "summary" in d:
        put("summary", validate.text(d["summary"], "运行摘要", 5000), r["summary"])
    if "equipment" in d:
        put("equipment", json.dumps(_ids(d["equipment"], "仪器")), r["equipment"])
    if "materials" in d:
        put("materials", json.dumps(_ids(d["materials"], "材料")), r["materials"])
    if "analyst_id" in d:
        a = d["analyst_id"]
        if isinstance(a, bool) or not isinstance(a, int) or not conn.execute("SELECT 1 FROM users WHERE id=? AND active=1", (a,)).fetchone():
            raise validate.Invalid("分析员不存在或已停用")
        put("analyst_id", a, r["analyst_id"])
    if not sets:
        return
    conn.execute("UPDATE runs SET %s, version=version+1, updated_at=? WHERE id=?" % ",".join(sets), vals + [db.now(), rid])
    audit.log(conn, user, "run.update", "run", rid, mid, {"code": r["code"], "changes": ch})


def verify_run(conn, user, rid):
    """Second-person check: someone other than the analyst and the person who recorded the run."""
    r = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
    if not r:
        raise WFError("运行记录不存在", 404)
    mid = r["method_id"]
    workflow.require_active_method(conn, mid)
    roles = workflow.method_roles(conn, mid, user["id"])
    if not (roles & {"owner", "author", "reviewer", "approver"}):
        raise WFError("仅方法团队成员可核对运行记录", 403)
    if r["verified_by"]:
        raise WFError("该运行记录已核对", 409)
    if user["id"] in (r["analyst_id"], r["created_by"]):
        raise WFError("运行记录须由分析员和记录人以外的第二个人核对", 403)
    conn.execute("UPDATE runs SET verified_by=?, verified_at=?, updated_at=? WHERE id=?", (user["id"], db.now(), db.now(), rid))
    audit.log(conn, user, "run.verify", "run", rid, mid, {"code": r["code"]})


# ------------------------------------------------------------------ deviations
def _dev_row(conn, r, names):
    d = dict(r)
    d["classification_label"] = DEV_CLASS.get(d["classification"], d["classification"])
    d["status_label"] = DEV_STATUS.get(d["status"], d["status"])
    d["opened_name"] = names.get(d["opened_by"], "")
    d["closed_name"] = names.get(d["closed_by"], "")
    exp = conn.execute("SELECT code FROM experiments WHERE id=?", (d["experiment_id"],)).fetchone() if d["experiment_id"] else None
    d["experiment_code"] = exp["code"] if exp else ""
    return d


def list_deviations(conn, mid):
    names = _names(conn)
    return [_dev_row(conn, r, names) for r in conn.execute("SELECT * FROM deviations WHERE method_id=? ORDER BY id", (mid,))]


def _dev_links(conn, mid, d):
    sk = d.get("stage_key") or None
    if sk is not None:
        if not isinstance(sk, str) or not conn.execute("SELECT 1 FROM stages WHERE method_id=? AND key=?", (mid, sk)).fetchone():
            raise validate.Invalid("所属阶段不存在")
    eid = d.get("experiment_id") or None
    if eid is not None:
        if isinstance(eid, bool) or not isinstance(eid, int):
            raise validate.Invalid("experiment_id 必须是整数")
        e = conn.execute("SELECT * FROM experiments WHERE id=?", (eid,)).fetchone()
        if not e or e["method_id"] != mid:
            raise WFError("实验不属于该方法", 404)
        sk = sk or e["stage_key"]
    return sk, eid


def create_deviation(conn, user, mid, d):
    workflow.get_method(conn, mid)
    workflow.require_edit(conn, user, mid)
    workflow.require_active_method(conn, mid)
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    title = validate.text(d.get("title"), "标题", 300, required=True)
    desc = validate.text(d.get("description", ""), "偏离描述", 10000)
    cls = _enum(d.get("classification", "minor"), DEV_CLASS, "分类")
    sk, eid = _dev_links(conn, mid, d)
    n = conn.execute("SELECT COUNT(*) FROM deviations WHERE method_id=?", (mid,)).fetchone()[0] + 1
    code = "DEV-%03d" % n
    cur = conn.execute("INSERT INTO deviations(method_id,code,title,description,classification,stage_key,experiment_id,impact,root_cause,action,status,opened_by,opened_at) VALUES(?,?,?,?,?,?,?,?,?,?,'open',?,?)",
                       (mid, code, title, desc, cls, sk, eid, validate.text(d.get("impact", ""), "影响评估", 5000), validate.text(d.get("root_cause", ""), "根本原因", 5000),
                        validate.text(d.get("action", ""), "纠正/预防措施", 5000), user["id"], db.now()))
    audit.log(conn, user, "deviation.create", "deviation", cur.lastrowid, mid, {"code": code, "classification": cls, "stage": sk})
    if cls != "minor":
        p = workflow.get_method(conn, mid)
        workflow.notify(conn, workflow._team_ids(conn, mid, ("owner", "reviewer", "approver")), user["id"], "deviation", mid, sk,
                        "新偏离（%s）：%s｜%s" % (DEV_CLASS[cls], p["code"], title), desc[:300])
    return cur.lastrowid


def update_deviation(conn, user, did, d):
    r = conn.execute("SELECT * FROM deviations WHERE id=?", (did,)).fetchone()
    if not r:
        raise WFError("偏离记录不存在", 404)
    mid = r["method_id"]
    workflow.require_edit(conn, user, mid)
    workflow.require_active_method(conn, mid)
    if r["status"] == "closed":
        raise WFError("偏离已关闭，不能修改；如需继续请先重新打开", 409)
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    if validate.integer(d.get("version", -1), "version") != r["version"]:
        raise WFError("内容已被他人更新（版本冲突），请刷新后重试", 409)
    sets, vals, ch = [], [], {}

    def put(k, v):
        if v != r[k]:
            sets.append("%s=?" % k)
            vals.append(v)
            ch[k] = {"old": (r[k] or "")[:200] if isinstance(r[k], str) else r[k], "new": v[:200] if isinstance(v, str) else v}
    for k, label, n in (("title", "标题", 300), ("description", "偏离描述", 10000), ("impact", "影响评估", 5000), ("root_cause", "根本原因", 5000), ("action", "纠正/预防措施", 5000)):
        if k in d:
            put(k, validate.text(d[k], label, n, required=(k == "title")))
    if "classification" in d:
        put("classification", _enum(d["classification"], DEV_CLASS, "分类"))
    if "status" in d:
        st = _enum(d["status"], ("open", "investigating"), "状态")
        put("status", st)
    if "stage_key" in d or "experiment_id" in d:
        sk, eid = _dev_links(conn, mid, d)
        put("stage_key", sk)
        put("experiment_id", eid)
    if not sets:
        return
    conn.execute("UPDATE deviations SET %s, version=version+1 WHERE id=?" % ",".join(sets), vals + [did])
    audit.log(conn, user, "deviation.update", "deviation", did, mid, {"code": r["code"], "changes": ch})


def close_deviation(conn, user, did, note):
    """Closure = electronic signature (the caller re-authenticated the password).  Needs the root cause and the action
    to be filled in; a major / critical deviation needs an approver; nobody closes a deviation they opened."""
    r = conn.execute("SELECT * FROM deviations WHERE id=?", (did,)).fetchone()
    if not r:
        raise WFError("偏离记录不存在", 404)
    mid = r["method_id"]
    workflow.require_active_method(conn, mid)
    roles = workflow.method_roles(conn, mid, user["id"])
    need = {"approver"} if r["classification"] in ("major", "critical") else {"approver", "reviewer", "owner"}
    if not (roles & need):
        raise WFError("关闭该偏离需要：%s" % ("批准人（QA）" if "approver" in need and len(need) == 1 else "方法负责人、复核人或批准人"), 403)
    if r["status"] == "closed":
        raise WFError("偏离已关闭", 409)
    if user["id"] == r["opened_by"]:
        raise WFError("偏离不能由提出人本人关闭", 403)
    if not (r["root_cause"] or "").strip() or not (r["action"] or "").strip():
        raise WFError("关闭前须填写“根本原因”和“纠正/预防措施”", 422)
    note = validate.text(note, "关闭说明", 2000, required=True)
    conn.execute("UPDATE deviations SET status='closed', closed_by=?, closed_at=?, close_note=?, version=version+1 WHERE id=?", (user["id"], db.now(), note, did))
    audit.log(conn, user, "deviation.close", "deviation", did, mid, {"code": r["code"]}, note)
    workflow.notify(conn, [r["opened_by"]], user["id"], "deviation", mid, r["stage_key"], "偏离已关闭：%s" % r["title"], note[:300])


def reopen_deviation(conn, user, did, reason):
    r = conn.execute("SELECT * FROM deviations WHERE id=?", (did,)).fetchone()
    if not r:
        raise WFError("偏离记录不存在", 404)
    mid = r["method_id"]
    workflow.require_active_method(conn, mid)
    if not (workflow.method_roles(conn, mid, user["id"]) & {"owner", "approver", "reviewer"}):
        raise WFError("仅方法负责人、复核人或批准人可重新打开偏离", 403)
    if r["status"] != "closed":
        raise WFError("偏离未关闭", 409)
    reason = validate.text(reason, "原因", 2000, required=True)
    conn.execute("UPDATE deviations SET status='open', closed_by=NULL, closed_at=NULL, version=version+1 WHERE id=?", (did,))
    audit.log(conn, user, "deviation.reopen", "deviation", did, mid, {"code": r["code"]}, reason)


def open_blocking(conn, mid, stage_key):
    """(blocks, warns) texts for the gate check of `stage_key`: open major/critical deviations block, minor ones warn."""
    blocks, warns = [], []
    for r in conn.execute("SELECT code, title, classification FROM deviations WHERE method_id=? AND stage_key=? AND status!='closed'", (mid, stage_key)):
        msg = "偏离 %s（%s）尚未关闭：%s" % (r["code"], DEV_CLASS.get(r["classification"], r["classification"]), r["title"])
        (warns if r["classification"] == "minor" else blocks).append(msg)
    return blocks, warns
