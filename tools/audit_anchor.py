"""查看或重建审计链锚点（data\\audit_head.json）。

用法:
    python tools\\audit_anchor.py                # 显示审计链、锚点与触发器状态
    python tools\\audit_anchor.py --reset --yes  # 在审计链校验通过的前提下，以当前链头重建锚点（写入一条审计记录）

锚点丢失/损坏、或从旧备份整体拷贝数据库后，审计校验会报告“锚点缺失/被改动”。只有在审计链本身校验通过时，
才允许重建；重建动作本身会被记录。审计密钥文件 data\\.audit_key 丢失时无法重建（须从备份取回密钥）。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="MethodFlow 审计锚点")
    ap.add_argument("--data", help="数据目录")
    ap.add_argument("--reset", action="store_true", help="重建锚点")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    args = ap.parse_args()
    if args.data:
        os.environ["METHODFLOW_DATA"] = os.path.abspath(args.data)
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    from app import audit, config, db  # noqa: E402

    if not config.DB_PATH.exists():
        print("错误：找不到数据库 %s" % config.DB_PATH)
        return 1
    with db.read() as conn:
        res = audit.verify_chain(conn, live_anchor=True)
        trig = audit.triggers_present(conn)
    print("审计记录 %d 条；链校验 %s；锚点状态 %s；防篡改触发器 %s"
          % (res["count"], "通过" if res["chain_ok"] else "失败(首个异常 id=%s%s)" % (res["first_bad_id"], "，密钥缺失" if res["key_missing"] else ""),
             res["anchor_status"], "齐全" if trig else "缺失"))
    if not args.reset:
        return 0 if res["ok"] and trig else 2
    if not res["chain_ok"]:
        print("拒绝：审计链本身校验失败，不能重建锚点。请先调查并从可信备份恢复。")
        return 4
    if not args.yes and input("确认以当前链头重建锚点请输入 YES：").strip() != "YES":
        print("已取消。")
        return 1
    with db.tx() as conn:
        audit.log(conn, "system:audit_anchor", "audit.anchor_reset", "system", None, None,
                  {"previous_anchor_status": res["anchor_status"], "tool": "tools/audit_anchor.py"}, "重建审计锚点")
    head = audit.write_head(force=True)
    print("锚点已重建：id=%s，记录数=%s" % (head["id"], head["count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
