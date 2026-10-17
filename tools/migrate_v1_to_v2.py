"""把旧版数据库（项目 = 方法，结构版本 1 或 2）转换为新版（项目/方法分离，结构版本 3）。

用法:
    python tools\\migrate_v1_to_v2.py                  # 转换 .\\data（或环境变量 METHODFLOW_DATA）
    python tools\\migrate_v1_to_v2.py --data D:\\xxx    # 指定数据目录
    python tools\\migrate_v1_to_v2.py --yes             # 不再询问确认
    python tools\\migrate_v1_to_v2.py --port 8790       # 服务器若用了非默认端口，请同样指定，以便检测服务器是否仍在运行

转换规则
  * 每个旧“项目”变成一个“方法”（方法 id = 旧项目 id，阶段/实验/附件/评审/文档/审计的归属不变），
    并自动新建一个同名的“项目”（项目 id = 旧项目 id）作为容器；旧项目负责人成为新项目负责人，其他成员为项目成员
    （只读者为只读成员）；旧项目成员及角色原样成为方法成员。
  * 编号：新项目 PRJ-YYYY-NNN、新方法 AM-YYYY-NNN（按旧项目创建年份、id 顺序）；旧编号（MD-…）保存在方法的 meta.legacy_code。
  * 旧项目的 title/attribute 变为方法的 name/analyte；product 变为项目的 product；状态 cancelled → 项目“归档”、方法“取消”。
  * 签名与审计不被改写：stage_revisions/reviews 逐字复制，旧审计记录（hv=1/2）逐字复制并保持哈希链，其未参与哈希的
    method_id 列填入旧项目 id；随后追加一条 schema.migrate 记录（hv=3）。旧版的签名哈希公式（hv=1/2）继续用于验证旧签名。
  * 结构版本 1 的库同时补齐加固字段（贡献者、方案外追加标记）。
  * 整个转换在新文件中完成并校验（完整性、审计链、行数），成功后才替换 data\\methodflow.db；原数据库另存为
    data\\backups\\premigrate_时间戳.db（连同 .audit_key 与 audit_head.json 的副本），任何一步失败都不改动现有数据。
要求先关闭 MethodFlow 服务器。
"""
import argparse
import datetime as dt
import json
import os
import shutil
import socket
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def server_running(host, port):
    probe = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    try:
        with socket.create_connection((probe, port), timeout=0.7):
            return True
    except OSError:
        return False


def db_locked(path):
    try:
        con = sqlite3.connect(path, timeout=0.5, isolation_level=None)
        try:
            con.execute("BEGIN EXCLUSIVE")
            con.execute("ROLLBACK")
        finally:
            con.close()
        return False
    except sqlite3.Error:
        return True


PROJECT_STATUS = {"active": "active", "completed": "completed", "archived": "archived", "cancelled": "archived"}


def _cols(conn, schema, table):
    return {r[1] for r in conn.execute("PRAGMA %s.table_info(%s)" % (schema, table))}


def convert(conn, old_ver, db, audit):
    """Copy everything from the attached database `old` into the (empty, v3-schema) main database."""
    has = {t: _cols(conn, "old", t) for t in ("stages", "stage_revisions", "experiments", "audit_log", "projects")}
    counts = {}
    # ---------------------------------------------------------------- accounts
    conn.execute("INSERT INTO users(id,username,display_name,roles,pw_hash,active,failed_count,locked_until,must_change,created_at) "
                 "SELECT id,username,display_name,roles,pw_hash,active,failed_count,locked_until,must_change,created_at FROM old.users")
    conn.execute("INSERT INTO sessions SELECT token_hash,user_id,created_at,last_seen,expires_at FROM old.sessions")
    # ---------------------------------------------------------------- projects (containers) and methods
    seq = {}
    proj = conn.execute("SELECT * FROM old.projects ORDER BY id").fetchall()

    def next_code(prefix, created):
        year = created[:4] if created and created[:4].isdigit() else str(dt.date.today().year)
        seq[(prefix, year)] = seq.get((prefix, year), 0) + 1
        return "%s-%s-%03d" % (prefix, year, seq[(prefix, year)])

    for p in proj:
        prj_code, am_code = next_code("PRJ", p["created_at"]), next_code("AM", p["created_at"])
        meta = json.loads(p["meta"] or "{}")
        meta["legacy_code"] = p["code"]
        conn.execute("INSERT INTO projects(id,code,name,product,indication,phase,description,status,planned_start,planned_end,owner_id,created_by,created_at,updated_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (p["id"], prj_code, p["title"], p["product"] or "", "", p["phase"] or "", "",
                      PROJECT_STATUS.get(p["status"], "archived"), p["planned_start"], p["planned_end"], p["owner_id"],
                      p["created_by"], p["created_at"], p["updated_at"]))
        conn.execute("INSERT INTO methods(id,code,project_id,name,technique,template_key,template_version,analyte,matrix,intended_use,phase,"
                     "method_version,lifecycle,status,planned_start,planned_end,owner_id,created_by,created_at,updated_at,meta)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (p["id"], am_code, p["id"], p["title"], p["technique"], p["template_key"], p["template_version"], p["attribute"] or "", "",
                      p["intended_use"] or "", p["phase"] or "", "V0.1", "development", p["status"], p["planned_start"], p["planned_end"],
                      p["owner_id"], p["created_by"], p["created_at"], p["updated_at"], json.dumps(meta, ensure_ascii=False)))
    counts["projects"] = len(proj)
    members = {}
    for r in conn.execute("SELECT project_id, user_id, role FROM old.project_members"):
        members.setdefault((r["project_id"], r["user_id"]), set()).add(r["role"])
        conn.execute("INSERT INTO method_members(method_id,user_id,role) VALUES(?,?,?)", (r["project_id"], r["user_id"], r["role"]))
    for (pid, uid), roles in sorted(members.items()):
        role = "owner" if "owner" in roles else ("member" if roles & {"author", "reviewer", "approver"} else "viewer")
        conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?)", (pid, uid, role))
    # ---------------------------------------------------------------- stages and their evidence
    contrib = "contributors" if "contributors" in has["stages"] else "'[]'"
    conn.execute("INSERT INTO stages(id,method_id,key,ord,def,status,revision,version,stale,data,editors,contributors,planned_start,planned_end,"
                 "actual_start,actual_end,submitted_at,updated_at) SELECT id,project_id,key,ord,def,status,revision,version,stale,data,editors,%s,"
                 "planned_start,planned_end,actual_start,actual_end,submitted_at,updated_at FROM old.stages" % contrib)
    hv = "hv" if "hv" in has["stage_revisions"] else "1"
    conn.execute("INSERT INTO stage_revisions(id,stage_id,revision,data,data_hash,created_by,created_at,reason,hv) "
                 "SELECT id,stage_id,revision,data,data_hash,created_by,created_at,reason,%s FROM old.stage_revisions" % hv)
    conn.execute("INSERT INTO reviews(id,method_id,stage_id,revision,role,user_id,decision,comment,signed_at,data_hash,meaning) "
                 "SELECT id,project_id,stage_id,revision,role,user_id,decision,comment,signed_at,data_hash,meaning FROM old.reviews")
    late = "added_after_plan" if "added_after_plan" in has["experiments"] else "0"
    conn.execute("INSERT INTO experiments(id,method_id,stage_key,code,title,objective,design,acceptance,planned_start,planned_end,actual_start,actual_end,"
                 "status,owner_id,results,conclusion,deviations,version,created_at,updated_at,added_after_plan) "
                 "SELECT id,project_id,stage_key,code,title,objective,design,acceptance,planned_start,planned_end,actual_start,actual_end,"
                 "status,owner_id,results,conclusion,deviations,version,created_at,updated_at,%s FROM old.experiments" % late)
    conn.execute("INSERT INTO attachments(id,method_id,stage_key,experiment_id,filename,size,sha256,path,description,uploaded_by,uploaded_at,"
                 "deleted,deleted_by,deleted_at,delete_reason) SELECT id,project_id,stage_key,experiment_id,filename,size,sha256,path,description,"
                 "uploaded_by,uploaded_at,deleted,deleted_by,deleted_at,delete_reason FROM old.attachments")
    conn.execute("INSERT INTO generated_docs(id,method_id,kind,format,filename,path,version_label,status_label,data_hash,created_by,created_at,summary) "
                 "SELECT id,project_id,kind,'docx',filename,path,version_label,status_label,data_hash,created_by,created_at,summary FROM old.generated_docs")
    conn.execute("INSERT INTO kb_items(id,kind,title,body,tags,techniques,stages,source,origin_method_id,builtin,active,created_by,created_at,updated_at) "
                 "SELECT id,kind,title,body,tags,techniques,stages,source,origin_project_id,"
                 "CASE WHEN created_by IS NULL AND origin_project_id IS NULL THEN 1 ELSE 0 END,active,created_by,created_at,updated_at FROM old.kb_items")
    conn.execute("INSERT INTO settings SELECT key,value FROM old.settings")
    # ---------------------------------------------------------------- hardening fields of a version-1 database
    if old_ver == 1:
        for s in conn.execute("SELECT id, editors FROM stages").fetchall():
            who = set(json.loads(s["editors"] or "[]"))
            for r in conn.execute("SELECT created_by FROM stage_revisions WHERE stage_id=?", (s["id"],)):
                if r["created_by"] is not None:
                    who.add(r["created_by"])
            conn.execute("UPDATE stages SET contributors=? WHERE id=?", (json.dumps(sorted(who)), s["id"]))
        for p in conn.execute("SELECT s.method_id, MAX(r.signed_at) AS t FROM stages s JOIN reviews r ON r.stage_id=s.id "
                              "WHERE s.key='plan' AND s.status IN ('approved','completed') AND r.decision='approve' GROUP BY s.method_id"):
            if p["t"]:
                conn.execute("UPDATE experiments SET added_after_plan=1 WHERE method_id=? AND created_at>?", (p["method_id"], p["t"]))
    # ---------------------------------------------------------------- audit trail, verbatim
    ahv = "hv" if "hv" in has["audit_log"] else "1"
    conn.execute("INSERT INTO audit_log(id,ts,user_id,username,action,entity_type,entity_id,project_id,method_id,details,reason,prev_hash,hash,hv) "
                 "SELECT id,ts,user_id,username,action,entity_type,entity_id,project_id,project_id,details,reason,prev_hash,hash,%s FROM old.audit_log" % ahv)
    counts["audit"] = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    for t in ("users", "projects", "methods", "stages", "stage_revisions", "reviews", "experiments", "attachments", "generated_docs", "kb_items"):
        counts[t] = conn.execute("SELECT COUNT(*) FROM main.%s" % t).fetchone()[0]
    return counts


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="把旧版（项目=方法）数据库转换为项目/方法分离的新版")
    ap.add_argument("--data", help="数据目录")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    ap.add_argument("--force", action="store_true", help="忽略“服务器仍在运行”的探测（不建议）")
    ap.add_argument("--port", type=int, help="服务器端口（若启动时用了非默认端口）")
    args = ap.parse_args()
    if args.data:
        os.environ["METHODFLOW_DATA"] = os.path.abspath(args.data)
    if args.port:
        os.environ["METHODFLOW_PORT"] = str(args.port)
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    from app import audit, config, db  # noqa: E402

    if not config.DB_PATH.exists():
        print("错误：找不到数据库 %s（--data 路径不对？）" % config.DB_PATH)
        return 1
    if not args.force and server_running(config.get("host"), int(config.get("port"))):
        print("拒绝：检测到 MethodFlow 仍在运行（端口 %s 有响应）。请先关闭服务器再重试。" % config.get("port"))
        return 3
    if db_locked(str(config.DB_PATH)):
        print("拒绝：数据库正被其他进程占用（服务器是否仍在运行？）。")
        return 3
    probe = sqlite3.connect(str(config.DB_PATH))
    try:
        ver = probe.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        probe.close()
    if ver >= db.MIN_SUPPORTED_VERSION:
        print("该数据库已经是新版结构（%d），无需转换。" % ver)
        return 0
    if ver not in (1, 2) or "projects" not in tables or "methods" in tables:
        print("错误：无法识别的数据库结构（user_version=%d）。本工具只转换结构版本 1 或 2 的旧库。" % ver)
        return 1
    key_needed = ver == 2
    if key_needed and not config.AUDIT_KEY.exists():
        print("错误：缺少审计密钥文件 %s，旧库的审计链无法验证与延续。请先把 .audit_key 放回数据目录。" % config.AUDIT_KEY)
        return 1

    print("数据目录 : %s" % config.DATA)
    print("旧数据库 : %s（结构版本 %d）" % (config.DB_PATH, ver))
    print("将把每个旧项目转换为一个方法，并为其自动建同名项目；原数据库会先另存为 data\\backups\\premigrate_*.db。")
    if not args.yes and input("确认请输入 YES：").strip() != "YES":
        print("已取消。")
        return 1

    config.ensure_dirs()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    aside = config.BACKUPS / ("premigrate_%s.db" % stamp)
    s = sqlite3.connect(str(config.DB_PATH))
    try:
        d = sqlite3.connect(str(aside))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()
    for src, suffix in ((config.AUDIT_KEY, ".audit_key"), (config.AUDIT_HEAD, ".head.json")):
        if src.exists():
            shutil.copyfile(str(src), str(config.BACKUPS / ("premigrate_%s%s" % (stamp, suffix))))
    print("[1/4] 已备份：%s" % aside)

    new_path = config.DB_PATH.with_name(config.DB_PATH.name + ".migrating")
    for ext in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(str(new_path) + ext)
        except OSError:
            pass
    conn = sqlite3.connect(str(new_path), isolation_level=None, factory=db._Conn)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        for stmt in db.split_sql(db.DDL):
            conn.execute(stmt)
        conn.execute("ATTACH DATABASE ? AS old", (str(aside),))
        print("[2/4] 复制并转换数据 ...")
        counts = convert(conn, ver, db, audit)
        audit.load_key(create=True, conn=conn)
        audit.log(conn, "system:migrate", "schema.migrate", "system", None, None,
                  {"from_version": ver, "to_version": db.SCHEMA_VERSION, "projects_converted": counts["projects"], "tool": "tools/migrate_v1_to_v2.py"},
                  "旧版（项目=方法）数据库转换为项目/方法分离结构")
        for stmt in db.split_sql(db.TRIGGERS):
            conn.execute(stmt)
        conn.execute("COMMIT")
        conn.execute("DETACH DATABASE old")
        conn.execute("PRAGMA user_version=%d" % db.SCHEMA_VERSION)
        print("[3/4] 校验新数据库 ...")
        ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
        chain = audit.verify_chain(conn)
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if ic != "ok" or not chain["ok"] or fk or chain["count"] != counts["audit"] + 1:
            raise RuntimeError("新数据库校验失败：完整性=%s；审计链=%s（首个异常记录 id=%s）；外键问题 %d 处" %
                               (ic, chain["ok"], chain["first_bad_id"], len(fk)))
        print("      完整性=ok；审计链通过（%d 条，其中旧记录 %d 条原样保留）；项目/方法 %d 个" % (chain["count"], counts["audit"], counts["projects"]))
    except BaseException as e:
        try:
            conn.close()
        except Exception:
            pass
        for ext in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(str(new_path) + ext)
            except OSError:
                pass
        print("\n错误：转换失败，现有数据未改动。原因：%s" % e)
        return 4
    conn.close()
    for ext in ("-wal", "-shm"):
        try:
            os.remove(str(config.DB_PATH) + ext)
        except OSError:
            pass
    os.replace(str(new_path), str(config.DB_PATH))
    print("[4/4] 已替换 %s" % config.DB_PATH)
    try:
        head = audit.write_head(force=True)
        if head:
            print("      审计链锚点已更新（id=%s，%d 条）。" % (head["id"], head["count"]))
    except Exception as e:
        print("      警告：无法更新审计链锚点（%s）。可稍后运行 python tools\\audit_anchor.py --reset" % e)
    print("\n转换完成。附件与文档文件位置不变；旧编号保存在各方法的 meta.legacy_code，新编号为 PRJ-/AM-。")
    print("请重新运行 start.bat，登录后在“管理”页执行审计链校验，并抽查各方法的签名完整性。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
