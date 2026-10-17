"""Compliance helpers: audit-trail reviews, the inspection pack (method dossier), section comments, global search and
method revisions.  Pure functions on a connection; the HTTP layer is in main.py."""
import csv
import datetime as dt
import io
import json
import os
import re
import zipfile

from . import audit, config, db, validate, workflow
from .workflow import WFError

# ------------------------------------------------------------------ audit-trail reviews
REVIEW_CONCLUSIONS = {"no_issue": "未发现异常", "issues_found": "发现异常"}


def _require_reviewer(user):
    if not ({"admin", "approver"} & set(user["roles"])):
        raise WFError("审计追踪审核需要管理员或批准人角色", 403)


def create_audit_review(conn, user, d):
    """Records that a person reviewed the audit trail of a period (and optionally one method).  The caller has
    re-authenticated the password: this is an electronic signature.  The chain and the signatures are verified
    at that moment and the result is stored with the record."""
    _require_reviewer(user)
    if not isinstance(d, dict):
        raise validate.Invalid("请求格式不正确")
    p_from = validate.date_or_none(d.get("period_from"), "起始日期")
    p_to = validate.date_or_none(d.get("period_to"), "截止日期")
    if not p_from or not p_to:
        raise validate.Invalid("请填写审核期间的起止日期")
    if p_to < p_from:
        raise validate.Invalid("截止日期不能早于起始日期")
    scope = d.get("scope", "all")
    if scope not in ("all", "method"):
        raise validate.Invalid("范围无效")
    mid = d.get("method_id") if scope == "method" else None
    if scope == "method":
        if isinstance(mid, bool) or not isinstance(mid, int):
            raise validate.Invalid("请选择方法")
        workflow.get_method(conn, mid)
    conclusion = d.get("conclusion", "no_issue")
    if conclusion not in REVIEW_CONCLUSIONS:
        raise validate.Invalid("结论无效")
    findings = validate.text(d.get("findings", ""), "发现与处理", 10000, required=(conclusion == "issues_found"))
    q, args = "SELECT COUNT(*) FROM audit_log WHERE substr(ts,1,10)>=? AND substr(ts,1,10)<=?", [p_from, p_to]
    if mid:
        q += " AND method_id=?"
        args.append(mid)
    n = conn.execute(q, args).fetchone()[0]
    res = audit.verify(conn)            # hash chain, anchor, triggers and the signature integrity of every signed step
    ok = bool(res.get("ok")) and bool(res.get("signatures_ok", True))
    cur = conn.execute("INSERT INTO audit_reviews(reviewer_id,scope,method_id,period_from,period_to,entries_checked,chain_ok,conclusion,findings,signed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (user["id"], scope, mid, p_from, p_to, n, 1 if ok else 0, conclusion, findings, db.now()))
    audit.log(conn, user, "audit.review", "audit_review", cur.lastrowid, mid, {"period": [p_from, p_to], "entries": n, "chain_ok": ok, "conclusion": conclusion})
    return cur.lastrowid


def list_audit_reviews(conn):
    names = {r["id"]: r["display_name"] for r in conn.execute("SELECT id, display_name FROM users")}
    out = []
    for r in conn.execute("SELECT * FROM audit_reviews ORDER BY id DESC LIMIT 200"):
        d = dict(r)
        d["reviewer_name"] = names.get(d["reviewer_id"], "")
        d["chain_ok"] = bool(d["chain_ok"])
        d["conclusion_label"] = REVIEW_CONCLUSIONS.get(d["conclusion"], d["conclusion"])
        out.append(d)
    return out


def audit_review_status(conn):
    """When was the audit trail last reviewed, and is the next review overdue (config audit_review_days, 0 = off)?"""
    days = int(config.get("audit_review_days") or 0)
    last = conn.execute("SELECT signed_at FROM audit_reviews WHERE scope='all' ORDER BY id DESC LIMIT 1").fetchone()
    since = None
    if last:
        try:
            since = (dt.datetime.utcnow() - dt.datetime.strptime(last["signed_at"], "%Y-%m-%dT%H:%M:%SZ")).days
        except ValueError:
            since = None
    return {"interval_days": days, "last": last["signed_at"] if last else None, "days_since": since,
            "overdue": bool(days and (since is None or since > days))}


# ------------------------------------------------------------------ inspection pack
def _csv(rows, header):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def build_dossier(conn, user, mid, out_path, include_files=True):
    """Writes a zip file with the complete record of a method: content (JSON), experiments / runs / deviations (CSV),
    the signature manifest, the audit trail, the attachments with a SHA-256 manifest and the generated documents."""
    m = workflow.get_method(conn, mid)
    cap = int(config.get("max_dossier_mb") or 2000) * 1024 * 1024
    names = {r["id"]: r["display_name"] for r in conn.execute("SELECT id, display_name FROM users")}
    stages = workflow.list_stages(conn, mid)
    total = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("method.json", json.dumps(workflow.export_method(conn, mid), ensure_ascii=False, indent=1))
        z.writestr("experiments.csv", _csv(
            [(e["code"], e["title"], e["stage_key"], e["status"], e["planned_start"], e["planned_end"], e["conclusion"], e["deviations"], json.dumps(e["results"], ensure_ascii=False))
             for e in workflow.list_experiments(conn, mid)],
            ["code", "title", "stage", "status", "planned_start", "planned_end", "conclusion", "deviations", "results"]))
        from . import records
        z.writestr("runs.csv", _csv([(r["code"], r["experiment_code"], r["run_date"], r["analyst_name"], r["outcome"], "; ".join(i["label"] for i in r["equipment_items"]),
                                      "; ".join(i["label"] for i in r["material_items"]), r["summary"], r["verified_name"], r["verified_at"], "; ".join(r["warnings"]))
                                     for r in records.list_runs(conn, mid)],
                                    ["code", "experiment", "run_date", "analyst", "outcome", "equipment", "materials", "summary", "verified_by", "verified_at", "warnings"]))
        z.writestr("deviations.csv", _csv([(d["code"], d["title"], d["classification"], d["status"], d["stage_key"], d["experiment_code"], d["description"], d["impact"], d["root_cause"],
                                            d["action"], d["opened_name"], d["opened_at"], d["closed_name"], d["closed_at"], d["close_note"]) for d in records.list_deviations(conn, mid)],
                                          ["code", "title", "classification", "status", "stage", "experiment", "description", "impact", "root_cause", "action", "opened_by", "opened_at", "closed_by", "closed_at", "close_note"]))
        sig = []
        for s in stages:
            for r in conn.execute("SELECT * FROM reviews WHERE stage_id=? ORDER BY id", (s["id"],)):
                sig.append((s["key"], s["def"]["title"], r["revision"], r["role"], names.get(r["user_id"], ""), r["decision"], r["signed_at"], r["meaning"], r["data_hash"], r["comment"]))
        z.writestr("signatures.csv", _csv(sig, ["stage", "title", "revision", "role", "signer", "decision", "signed_at", "meaning", "data_hash", "comment"]))
        z.writestr("audit_trail.csv", _csv([(r["id"], r["ts"], r["username"] or names.get(r["user_id"], ""), r["action"], r["entity_type"], r["entity_id"],
                                             r["reason"], r["details"], r["hash"]) for r in conn.execute("SELECT * FROM audit_log WHERE method_id=? ORDER BY id", (mid,))],
                                           ["id", "time", "user", "action", "entity_type", "entity_id", "reason", "details", "hash"]))
        manifest = []
        for a in conn.execute("SELECT a.*, u.display_name AS uploader FROM attachments a LEFT JOIN users u ON u.id=a.uploaded_by WHERE a.method_id=? ORDER BY a.id", (mid,)):
            p = config.DATA / a["path"]
            ok = p.exists() and db.sha256(p.read_bytes()) == a["sha256"]
            manifest.append((a["id"], a["filename"], a["stage_key"], a["experiment_id"], a["size"], a["sha256"], a["uploader"], a["uploaded_at"], "yes" if ok else "NO", "deleted" if a["deleted"] else ""))
            if include_files and not a["deleted"] and p.exists():
                total += p.stat().st_size
                if total > cap:
                    raise WFError("检查包超过 %d MB 上限；请取消“包含附件文件”或联系管理员调大 max_dossier_mb" % (cap // 1048576), 413)
                z.write(str(p), "attachments/%d_%s" % (a["id"], re.sub(r"[\\/:*?\"<>|]", "_", a["filename"])))
        z.writestr("attachments_manifest.csv", _csv(manifest, ["id", "filename", "stage", "experiment_id", "size", "sha256", "uploaded_by", "uploaded_at", "intact", "note"]))
        for d in conn.execute("SELECT * FROM generated_docs WHERE method_id=? ORDER BY id", (mid,)):
            p = config.DATA / d["path"]
            if include_files and p.exists():
                total += p.stat().st_size
                if total > cap:
                    raise WFError("检查包超过 %d MB 上限" % (cap // 1048576), 413)
                z.write(str(p), "documents/" + os.path.basename(d["path"]))
        z.writestr("README.txt", "Inspection pack of %s %s (%s)\nGenerated %s by %s.\n\n"
                   "method.json            content of all steps, members, experiments\n"
                   "experiments.csv        experiments with results and conclusions\n"
                   "runs.csv               run records (analyst, equipment, materials, verification)\n"
                   "deviations.csv         deviation records\n"
                   "signatures.csv         electronic signature manifest (hash = content fingerprint at signing)\n"
                   "audit_trail.csv        audit trail rows of this method (HMAC hash chain)\n"
                   "attachments_manifest.csv + attachments/   raw data files with SHA-256 and an integrity flag\n"
                   "documents/             generated Word / PDF documents\n" % (m["code"], m["name"], m["method_version"], db.now(), user["display_name"]))
    audit.log(conn, user, "dossier.export", "method", mid, mid, {"files": bool(include_files)})


# ------------------------------------------------------------------ comments
def _can_see(conn, mid, uid):
    row = conn.execute("SELECT id, roles FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row) and workflow.can_view(conn, {"id": row["id"], "roles": db.jl(row["roles"], [])}, mid)


MENTION = re.compile(r"@([A-Za-z0-9_.\-]{3,32})")


def add_comment(conn, user, mid, stage_key, section_key, body):
    m = workflow.get_method(conn, mid)
    workflow.require_view(conn, user, mid)
    if not conn.execute("SELECT 1 FROM stages WHERE method_id=? AND key=?", (mid, stage_key)).fetchone():
        raise WFError("阶段不存在", 404)
    body = validate.text(body, "评论", 2000, required=True)
    section_key = validate.text(section_key or "", "章节", 100)
    cur = conn.execute("INSERT INTO comments(method_id,stage_key,section_key,user_id,body,created_at) VALUES(?,?,?,?,?,?)", (mid, stage_key, section_key, user["id"], body, db.now()))
    audit.log(conn, user, "comment.add", "comment", cur.lastrowid, mid, {"stage": stage_key, "section": section_key})
    title = "评论：%s｜%s" % (m["code"], user["display_name"])
    targets = []
    for name in set(MENTION.findall(body)):
        u = conn.execute("SELECT id FROM users WHERE username=? AND active=1", (name,)).fetchone()
        if u and _can_see(conn, mid, u["id"]):
            targets.append(u["id"])
    workflow.notify(conn, targets, user["id"], "mention", mid, stage_key, "你被 @：%s" % title, body[:300])
    workflow.notify(conn, workflow._team_ids(conn, mid, ("owner", "author")), user["id"], "comment", mid, stage_key, title, body[:300])
    return cur.lastrowid


def list_comments(conn, mid, stage_key):
    names = {r["id"]: r["display_name"] for r in conn.execute("SELECT id, display_name FROM users")}
    out = []
    for r in conn.execute("SELECT * FROM comments WHERE method_id=? AND stage_key=? ORDER BY id", (mid, stage_key)):
        d = dict(r)
        d["user_name"] = names.get(d["user_id"], "")
        d["resolved"] = bool(d["resolved"])
        d["resolved_name"] = names.get(d["resolved_by"], "")
        out.append(d)
    return out


def resolve_comment(conn, user, cid, resolved=True):
    r = conn.execute("SELECT * FROM comments WHERE id=?", (cid,)).fetchone()
    if not r:
        raise WFError("评论不存在", 404)
    workflow.require_view(conn, user, r["method_id"])
    roles = workflow.method_roles(conn, r["method_id"], user["id"])
    if user["id"] != r["user_id"] and not (roles & {"owner", "author", "reviewer", "approver"}):
        raise WFError("仅评论人或方法团队成员可处理评论", 403)
    conn.execute("UPDATE comments SET resolved=?, resolved_by=?, resolved_at=? WHERE id=?", (1 if resolved else 0, user["id"] if resolved else None, db.now() if resolved else None, cid))
    audit.log(conn, user, "comment.resolve" if resolved else "comment.reopen", "comment", cid, r["method_id"], {})


# ------------------------------------------------------------------ global search
def search(conn, user, q, limit=15):
    q = (q or "").strip()
    if len(q) < 2:
        raise validate.Invalid("请输入至少 2 个字符")
    like = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
    visible = {m["id"]: m for m in workflow.visible_methods(conn, user)}
    out = {"projects": [], "methods": [], "experiments": [], "deviations": [], "kb": [], "links": [], "materials": []}
    for p in workflow.visible_projects(conn, user):
        if len(out["projects"]) < limit and re.search(re.escape(q), "%s %s %s %s" % (p["code"], p["name"], p["product"] or "", p["indication"] or ""), re.I):
            out["projects"].append({"id": p["id"], "code": p["code"], "title": p["name"]})
    for m in visible.values():
        if len(out["methods"]) < limit and re.search(re.escape(q), "%s %s %s %s %s" % (m["code"], m["name"], m["analyte"] or "", m["matrix"] or "", m["intended_use"] or ""), re.I):
            out["methods"].append({"id": m["id"], "code": m["code"], "title": m["name"]})
    if visible:
        ids = ",".join(str(i) for i in visible)
        for r in conn.execute("SELECT id, method_id, code, title FROM experiments WHERE method_id IN (%s) AND (title LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\' OR conclusion LIKE ? ESCAPE '\\' OR objective LIKE ? ESCAPE '\\') LIMIT ?" % ids,
                              (like, like, like, like, limit)):
            out["experiments"].append({"id": r["id"], "method_id": r["method_id"], "code": r["code"], "title": r["title"], "method_code": visible[r["method_id"]]["code"]})
        for r in conn.execute("SELECT id, method_id, code, title FROM deviations WHERE method_id IN (%s) AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\') LIMIT ?" % ids,
                              (like, like, like, limit)):
            out["deviations"].append({"id": r["id"], "method_id": r["method_id"], "code": r["code"], "title": r["title"], "method_code": visible[r["method_id"]]["code"]})
    for r in conn.execute("SELECT id, title FROM kb_items WHERE active=1 AND (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\') LIMIT ?", (like, like, limit)):
        out["kb"].append({"id": r["id"], "title": r["title"]})
    for r in conn.execute("SELECT id, title, title_en, url FROM kb_links WHERE active=1 AND (title LIKE ? ESCAPE '\\' OR title_en LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR org LIKE ? ESCAPE '\\') LIMIT ?", (like, like, like, like, limit)):
        out["links"].append({"id": r["id"], "title": r["title"], "title_en": r["title_en"], "url": r["url"]})
    for r in conn.execute("SELECT id, code, name, lot FROM materials WHERE active=1 AND (name LIKE ? ESCAPE '\\' OR lot LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\') LIMIT ?", (like, like, like, limit)):
        out["materials"].append({"id": r["id"], "code": r["code"], "title": "%s %s" % (r["name"], r["lot"] or "")})
    out["total"] = sum(len(v) for v in out.values() if isinstance(v, list))
    return out


# ------------------------------------------------------------------ method revision
def _next_version(v):
    m = re.fullmatch(r"([A-Za-z]*)(\d+)\.(\d+)", (v or "").strip())
    if m:
        return "%s%s.%d" % (m.group(1), m.group(2), int(m.group(3)) + 1)
    return ((v or "V1.0").strip() or "V1.0") + "-r2"


def revise_method(conn, user, mid, note, version=None):
    """New revision of an approved method: a copy of its content (with the 'confirmed' state kept) as a NEW method that
    points back at the old one, with a mandatory change description.  The old method is not modified."""
    src = workflow.get_method(conn, mid)
    roles = workflow.method_roles(conn, mid, user["id"])
    if not (roles & {"owner", "approver"}):
        raise WFError("仅方法负责人或批准人可创建修订版", 403)
    if not any(s["status"] in workflow.LOCKED for s in workflow.list_stages(conn, mid)):
        raise WFError("尚无已通过的阶段；修订版用于已批准的方法（未批准的方法直接修改即可）", 409)
    note = validate.text(note, "变更说明", 5000, required=True)
    ver = validate.text(version or "", "方法版本", 50) or _next_version(src["method_version"])
    new_id = workflow.clone_method(conn, user, mid, src["name"], None)
    old = {s["key"]: s for s in workflow.list_stages(conn, mid)}
    for ns in workflow.list_stages(conn, new_id):
        d = ns["data"]
        d["unconfirmed"] = list((old[ns["key"]]["data"].get("unconfirmed")) or []) if ns["key"] in old else d.get("unconfirmed", [])
        conn.execute("UPDATE stages SET data=? WHERE id=?", (json.dumps(d, ensure_ascii=False), ns["id"]))
    conn.execute("UPDATE methods SET revision_of=?, revision_note=?, method_version=? WHERE id=?", (mid, note, ver, new_id))
    audit.log(conn, user, "method.revise", "method", new_id, new_id, {"from": src["code"], "version": ver}, note)
    workflow.notify(conn, workflow._team_ids(conn, mid, ("owner", "author", "reviewer", "approver")), user["id"], "revision", new_id, None,
                    "已创建修订版 %s（%s）" % (ver, src["code"]), note[:300])
    return new_id
