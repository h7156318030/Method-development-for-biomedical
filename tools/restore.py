"""从备份文件恢复 MethodFlow 数据库。

用法:
    python tools\\restore.py                         # 列出可用备份
    python tools\\restore.py methodflow_2026....db   # 按文件名（在 data\\backups 中）或完整路径恢复
    python tools\\restore.py <备份> --yes            # 不再询问确认
    python tools\\restore.py <备份> --data D:\\xxx    # 指定数据目录

步骤（程序自动完成）:
  1. 检查服务器是否仍在运行 / 数据库是否被占用 —— 是则拒绝（请先关闭 MethodFlow 窗口；--force 可忽略端口探测，不建议）。
  2. 校验备份：能打开、PRAGMA integrity_check、结构版本、审计哈希链。任一失败则拒绝，不改动现有数据。
  3. 把“当前数据库”另存为 data\\backups\\prerestore_时间戳.db（可回退）。
  4. 用备份替换 data\\methodflow.db（并清除旧的 -wal/-shm 文件）。
  5. 复检恢复后的数据库。
uploads/ 与 documents/ 文件夹不会被改动或删除。
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


def _ro(path):
    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % path.replace("\\", "/"), uri=True)
    con.row_factory = sqlite3.Row
    return con


def verify(path, audit, db):
    """Return (ok, messages)."""
    msgs = []
    try:
        con = _ro(path)
    except sqlite3.Error as e:
        return False, ["无法打开备份：%s" % e]
    try:
        try:
            ic = con.execute("PRAGMA integrity_check").fetchone()[0]
            ver = con.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.Error as e:
            return False, ["备份不是有效的 SQLite 数据库：%s" % e]
        need = {"users", "projects", "methods", "method_members", "project_members", "stages", "audit_log", "reviews", "attachments", "experiments"}
        ok = True
        if ic != "ok":
            ok = False; msgs.append("完整性检查失败：%s" % ic)
        if 0 < ver < db.MIN_SUPPORTED_VERSION:
            ok = False; msgs.append("备份是旧版结构(%d：项目与方法尚未分离)，不能直接恢复到本程序(结构版本 %d)；"
                                    "请先把它放入一个独立的数据目录并运行 tools\\migrate_v1_to_v2.py 转换，再用转换后的库恢复" % (ver, db.SCHEMA_VERSION))
        elif not need <= tables:
            ok = False; msgs.append("缺少数据表：%s" % ", ".join(sorted(need - tables)))
        if ver > db.SCHEMA_VERSION:
            ok = False; msgs.append("备份的结构版本(%d)高于本程序(%d)，请先升级程序" % (ver, db.SCHEMA_VERSION))
        if ok:
            anchor = None                                   # the backup's own side-car records its chain head
            mp = path + ".manifest.json"
            if os.path.exists(mp):
                try:
                    with open(mp, encoding="utf-8") as f:
                        anchor = json.load(f).get("audit_head")
                except Exception:
                    msgs.append("警告：备份旁注文件（manifest）无法读取，跳过链头比对")
            elif path.endswith(".db") and os.path.basename(path).startswith("methodflow_"):
                msgs.append("警告：该备份没有旁注文件（manifest），无法比对链头")
            chain = audit.verify_chain(con, anchor=anchor)
            if chain.get("key_missing"):
                ok = False; msgs.append("审计密钥文件（data\\.audit_key）缺失，无法验证该备份的审计链。请先放回密钥文件")
            elif not chain["ok"]:
                ok = False
                if chain["chain_ok"]:
                    msgs.append("备份的审计链头与旁注文件不符（%s）—— 备份的末尾记录可能被删除或旁注被改动" % chain["anchor_status"])
                else:
                    msgs.append("审计哈希链校验失败（首个异常记录 id=%s）—— 该备份可能已被改动" % chain["first_bad_id"])
            else:
                u = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                p = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                m = con.execute("SELECT COUNT(*) FROM methods").fetchone()[0]
                msgs.append("备份内容：用户 %d，项目 %d，方法 %d，审计记录 %d 条（哈希链通过%s），结构版本 %d" %
                            (u, p, m, chain["count"], "，链头与旁注一致" if anchor else "", ver))
        return ok, msgs
    finally:
        con.close()


def server_running(host, port):
    probe = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    try:
        with socket.create_connection((probe, port), timeout=0.7):
            return True
    except OSError:
        return False


def db_locked(path):
    """True if another process holds the database (e.g. server still running)."""
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


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="从备份恢复 MethodFlow 数据库")
    ap.add_argument("backup", nargs="?", help="备份文件名（在 data\\backups 中）或完整路径")
    ap.add_argument("--data", help="数据目录")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    ap.add_argument("--force", action="store_true", help="忽略“服务器仍在运行”的探测（不建议）")
    ap.add_argument("--port", type=int, help="服务器端口（若启动时用了 --port，请在此同样指定，以便检测服务器是否仍在运行）")
    args = ap.parse_args()
    if args.data:
        os.environ["METHODFLOW_DATA"] = os.path.abspath(args.data)
    if args.port:
        os.environ["METHODFLOW_PORT"] = str(args.port)
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    from app import audit, config, db  # noqa: E402

    if not args.backup:
        files = sorted(config.BACKUPS.glob("methodflow_*.db"), reverse=True) + sorted(config.BACKUPS.glob("prerestore_*.db"), reverse=True)
        print("数据目录：%s" % config.DATA)
        if not files:
            print("没有找到备份文件（%s）。" % config.BACKUPS)
            return 1
        print("可用备份（新 -> 旧）：")
        for f in files:
            print("  %-52s %8.1f KB   %s" % (f.name, f.stat().st_size / 1024,
                                          dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
        print("\n用法：python tools\\restore.py <文件名>")
        return 0

    src = args.backup
    if not os.path.isabs(src) and not os.path.exists(src):
        src = str(config.BACKUPS / src)
    src = os.path.abspath(src)
    if not os.path.isfile(src):
        print("错误：找不到备份文件 %s" % src)
        return 1

    print("数据目录 : %s" % config.DATA)
    print("当前数据库: %s" % config.DB_PATH)
    print("备份文件 : %s" % src)

    # 1. server must be stopped
    if not args.force and server_running(config.get("host"), int(config.get("port"))):
        print("\n拒绝：检测到 MethodFlow 仍在运行（端口 %s 有响应）。请先关闭运行 start.bat 的窗口，再重试。" % config.get("port"))
        return 3
    if config.DB_PATH.exists() and db_locked(str(config.DB_PATH)):
        print("\n拒绝：当前数据库正被其他进程占用（服务器是否仍在运行？）。请先关闭 MethodFlow。")
        return 3

    # 2. verify the backup
    print("\n[1/4] 校验备份 ...")
    ok, msgs = verify(src, audit, db)
    for m in msgs:
        print("      " + m)
    if not ok:
        print("\n拒绝：备份未通过校验，现有数据未做任何改动。")
        return 4

    if not args.yes:
        print("\n即将用上述备份替换当前数据库。当前数据库会先另存为 prerestore_*.db 以便回退。")
        if input("确认请输入 YES：").strip() != "YES":
            print("已取消。")
            return 1

    # 3. set the current db aside
    print("[2/4] 保存当前数据库 ...")
    config.ensure_dirs()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    aside = None
    if config.DB_PATH.exists():
        aside = config.BACKUPS / ("prerestore_%s.db" % stamp)
        s = sqlite3.connect(str(config.DB_PATH))
        try:
            d = sqlite3.connect(str(aside))
            try:
                s.backup(d)
            finally:
                d.close()
        finally:
            s.close()
        print("      已另存：%s" % aside)
    else:
        print("      （当前没有数据库，跳过）")

    # 4. replace
    print("[3/4] 替换数据库 ...")
    tmp = str(config.DB_PATH) + ".restoring"
    shutil.copyfile(src, tmp)
    for ext in ("-wal", "-shm"):
        p = str(config.DB_PATH) + ext
        if os.path.exists(p):
            os.remove(p)
    os.replace(tmp, str(config.DB_PATH))
    if config.AUDIT_HEAD.exists():            # keep the old chain-head anchor next to the pre-restore copy
        shutil.copyfile(str(config.AUDIT_HEAD), str(config.BACKUPS / ("prerestore_%s.head.json" % stamp)))

    # 5. post-check
    print("[4/4] 复检 ...")
    ok2, msgs2 = verify(str(config.DB_PATH), audit, db)
    for m in msgs2:
        print("      " + m)
    if not ok2:
        print("\n错误：恢复后的数据库未通过复检！请用 %s 手动回退（复制为 methodflow.db）。" % (aside or "之前的备份"))
        return 5

    # the restored chain is (legitimately) older than the anchor of the replaced database: re-anchor it
    try:
        head = audit.write_head(force=True)
        if head:
            print("      审计链锚点已按恢复后的数据库重建（id=%s，%d 条）。" % (head["id"], head["count"]))
    except Exception as e:
        print("      警告：无法重建审计链锚点（%s）。可稍后运行 python tools\\audit_anchor.py --reset" % e)
    # compare uploads/documents with the backup's file manifest
    mp = src + ".manifest.json"
    if os.path.exists(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                files = json.load(f).get("files") or {}
            import hashlib
            missing, changed = [], []
            for rel, info in files.items():
                fp = config.DATA / rel
                if not fp.exists():
                    missing.append(rel)
                else:
                    h = hashlib.sha256()
                    with open(str(fp), "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                    if h.hexdigest() != info.get("sha256"):
                        changed.append(rel)
            print("      文件清单比对：备份时 %d 个文件；缺失 %d，内容已变 %d" % (len(files), len(missing), len(changed)))
            for rel in (missing + changed)[:20]:
                print("        - %s" % rel)
        except Exception as e:
            print("      警告：文件清单无法比对（%s）" % e)

    print("\n恢复完成。")
    print("  * uploads\\ 与 documents\\ 文件夹未被改动。若备份时间点之后上传/生成过文件，它们仍在磁盘上但不在数据库中（成为孤立文件，无害）；")
    print("    若备份中引用的附件文件已丢失，界面会提示“文件丢失”，可从 files_*.zip 或异地副本补回。")
    print("  * 请重新运行 start.bat，登录后在“管理”页执行审计链校验，并抽查附件“校验完整性”。")
    print("  * 建议由 QA 记录本次恢复（原因、使用的备份、时间、执行人）。回退文件：%s" % (aside or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
