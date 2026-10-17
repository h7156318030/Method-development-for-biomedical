"""离线重置管理员口令（忘记管理员口令且没有其他管理员可用时使用）。

用法:
    python tools\\reset_admin.py                      # 只有一个管理员时自动选择；否则列出管理员后要求 --username
    python tools\\reset_admin.py --username admin     # 指定账号
    python tools\\reset_admin.py --data D:\\xxx        # 指定数据目录（默认 .\\data 或环境变量 METHODFLOW_DATA）
    python tools\\reset_admin.py --yes                 # 不再询问确认
    python tools\\reset_admin.py --port 8790           # 服务器若用了非默认端口，请同样指定，以便检测服务器是否仍在运行

要求先关闭 MethodFlow 服务器（探测端口与数据库占用，仍在运行则拒绝）。
结果：生成随机临时口令（只在屏幕显示一次）、账号启用并解锁、清除其全部会话、下次登录必须修改口令，
并在审计追踪中写入 user.password_reset_offline 记录（含执行该工具的操作系统账号与主机名）。
"""
import argparse
import getpass
import os
import platform
import secrets
import socket
import sqlite3
import string
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


def temp_password(n=16):
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="离线重置 MethodFlow 管理员口令")
    ap.add_argument("--data", help="数据目录")
    ap.add_argument("--username", help="要重置的管理员账号")
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

    from app import audit, auth, config, db  # noqa: E402

    if not config.DB_PATH.exists():
        print("错误：找不到数据库 %s（--data 路径不对？）" % config.DB_PATH)
        return 1
    if not args.force and server_running(config.get("host"), int(config.get("port"))):
        print("拒绝：检测到 MethodFlow 仍在运行（端口 %s 有响应）。请先关闭服务器再重试。" % config.get("port"))
        return 3
    if db_locked(str(config.DB_PATH)):
        print("拒绝：数据库正被其他进程占用（服务器是否仍在运行？）。")
        return 3

    with db.read() as conn:
        admins = [dict(r) for r in conn.execute("SELECT id, username, display_name, roles, active FROM users ORDER BY id")
                  if "admin" in db.jl(r["roles"], [])]
    if not admins:
        print("错误：数据库中没有拥有管理员角色的账号。")
        return 1
    if args.username:
        target = next((a for a in admins if a["username"] == args.username), None)
        if not target:
            print("错误：%r 不是管理员账号。管理员账号：%s" % (args.username, "、".join(a["username"] for a in admins)))
            return 1
    elif len(admins) == 1:
        target = admins[0]
    else:
        print("有多个管理员账号，请用 --username 指定：")
        for a in admins:
            print("  %-20s %s%s" % (a["username"], a["display_name"], "" if a["active"] else "（已停用）"))
        return 1

    print("数据目录 : %s" % config.DATA)
    print("将重置账号: %s（%s）" % (target["username"], target["display_name"]))
    if not args.yes and input("确认请输入 YES：").strip() != "YES":
        print("已取消。")
        return 1

    pw = temp_password()
    with db.tx() as conn:
        conn.execute("UPDATE users SET pw_hash=?, must_change=1, failed_count=0, locked_until=NULL, active=1 WHERE id=?",
                     (auth.hash_password(pw), target["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (target["id"],))
        audit.log(conn, "system:reset_admin", "user.password_reset_offline", "user", target["id"], None,
                  {"username": target["username"], "os_user": getpass.getuser(), "host": platform.node(), "tool": "tools/reset_admin.py"},
                  "离线重置管理员口令")
    print("\n已重置。临时口令（只显示这一次，请立即登录并修改）：\n\n    %s\n" % pw)
    print("该账号已启用并解锁，所有旧会话已清除，登录后必须先修改口令。审计追踪已记录本次重置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
