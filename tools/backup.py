"""创建 MethodFlow 数据库备份（可在服务器运行时执行）。

用法:
    python tools\\backup.py                 # 备份数据库到 data\\backups\\
    python tools\\backup.py --files         # 另外把 uploads 与 documents 打成 zip（files_时间戳.zip）
    python tools\\backup.py --data D:\\xxx   # 指定数据目录（默认 .\\data 或环境变量 METHODFLOW_DATA）

数据库备份使用 SQLite 在线备份接口（与程序内“手动备份”相同的 app.workflow.backup_now），
备份后立即校验：数据库完整性 + 审计哈希链。附件/文档文件不在 .db 里，需要时加 --files。
"""
import argparse
import datetime as dt
import os
import sqlite3
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="MethodFlow 数据库备份")
    ap.add_argument("--data", help="数据目录")
    ap.add_argument("--files", action="store_true", help="同时打包 uploads 与 documents 文件夹")
    ap.add_argument("--label", default="manual", help="备份文件名标签（默认 manual）")
    args = ap.parse_args()
    if args.data:
        os.environ["METHODFLOW_DATA"] = os.path.abspath(args.data)
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    from app import audit, config, workflow  # noqa: E402

    if not config.DB_PATH.exists():
        print("错误：找不到数据库 %s（尚未初始化，或 --data 路径不对）" % config.DB_PATH)
        return 1
    name = workflow.backup_now(args.label)
    dest = config.BACKUPS / name
    print("已创建备份：%s（%.1f KB）" % (dest, dest.stat().st_size / 1024))
    mp = dest.with_name(dest.name + ".manifest.json")
    if mp.exists():
        print("旁注文件（审计链头 + uploads/documents 的 SHA-256 清单）：%s" % mp)

    # verify the copy
    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % dest.as_posix(), uri=True)
    con.row_factory = sqlite3.Row
    try:
        ic = con.execute("PRAGMA integrity_check").fetchone()[0]
        chain = audit.verify_chain(con)
        users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        projects = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        methods = con.execute("SELECT COUNT(*) FROM methods").fetchone()[0]
    finally:
        con.close()
    print("校验：完整性=%s；审计链=%s（%d 条）；用户 %d；项目 %d；方法 %d" %
          (ic, "通过" if chain["ok"] else "失败(首个异常记录 id=%s)" % chain["first_bad_id"], chain["count"], users, projects, methods))
    rc = 0
    if ic != "ok" or not chain["ok"]:
        print("警告：备份校验未通过，请勿依赖该备份，并联系管理员/QA 调查。")
        rc = 2

    if args.files:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        zp = config.BACKUPS / ("files_%s.zip" % stamp)
        n = 0
        with zipfile.ZipFile(str(zp), "w", zipfile.ZIP_DEFLATED) as z:
            for folder in (config.UPLOADS, config.DOCS):
                for dirpath, _dirs, files in os.walk(str(folder)):
                    _dirs[:] = [d for d in _dirs if d != ".tmp"]      # unfinished uploads
                    for f in files:
                        full = os.path.join(dirpath, f)
                        z.write(full, os.path.relpath(full, str(config.DATA)))
                        n += 1
        print("已打包附件与文档：%s（%d 个文件）" % (zp, n))
        print("提示：files_*.zip 不会被自动清理，请自行归档/删除旧文件。")
    else:
        print("提示：本备份只含数据库；附件与已生成文档在 %s 与 %s，需另行复制（或加 --files）。" % (config.UPLOADS, config.DOCS))
    print("请把 %s 中的备份定期复制到另一块磁盘/网络位置（异地备份）。" % config.BACKUPS)
    return rc


if __name__ == "__main__":
    sys.exit(main())
