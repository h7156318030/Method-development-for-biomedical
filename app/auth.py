"""Accounts, passwords, sessions and re-authentication for electronic signatures."""
import base64
import datetime as dt
import hashlib
import json
import re
import secrets
import threading

import bcrypt

from . import audit, config, db

ROLES = ["admin", "author", "reviewer", "approver", "viewer"]
ROLE_LABELS = {"admin": "管理员", "author": "开发人员", "reviewer": "复核人", "approver": "批准人(QA)", "viewer": "只读"}

GENERIC_FAIL = "用户名或密码错误"
GENERIC_LOCK = "登录尝试过多，请稍后再试"


class AuthError(Exception):
    def __init__(self, msg, status=401, extra=None):
        super().__init__(msg)
        self.status = status
        self.extra = extra


def _prep(pw):
    # bcrypt only uses the first 72 bytes; pre-hash so long passphrases are fully used
    return base64.b64encode(hashlib.sha256(pw.encode("utf-8")).digest())


def hash_password(pw):
    return bcrypt.hashpw(_prep(pw), bcrypt.gensalt(rounds=12)).decode("ascii")


def check_password(pw, pw_hash):
    try:
        return bcrypt.checkpw(_prep(pw), pw_hash.encode("ascii"))
    except Exception:
        return False


_dummy = []


def _dummy_hash():
    """A valid bcrypt hash used so that unknown usernames cost the same time as known ones."""
    if not _dummy:
        _dummy.append(hash_password("not-a-real-password-" + secrets.token_hex(8)))
    return _dummy[0]


def validate_password(pw):
    if not isinstance(pw, str):
        raise AuthError("密码必须是文本", 400)
    n = config.get("min_password_length")
    if len(pw) < n:
        raise AuthError("密码至少 %d 位" % n, 400)
    if len(pw) > 256:
        raise AuthError("密码过长", 400)
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise AuthError("密码须同时包含字母和数字", 400)


def _parse(ts):
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


def public_user(u):
    if not u:
        return None
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"],
            "roles": db.jl(u["roles"], []) if isinstance(u["roles"], str) else u["roles"],
            "active": bool(u["active"]), "must_change": bool(u["must_change"]), "email": (u["email"] if "email" in u.keys() else u.get("email", "")) or ""}


def user_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def check_roles(roles):
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise AuthError("角色必须是文本列表", 400)
    for r in roles:
        if r not in ROLES:
            raise AuthError("未知角色：%s" % r, 400)
    return list(dict.fromkeys(roles))


def check_email(email):
    if email in (None, ""):
        return ""
    if not isinstance(email, str) or len(email) > 200 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        raise AuthError("邮箱格式不正确", 400)
    return email.strip()


def _remember_password(conn, uid, old_hash):
    """Keeps the last `password_history` hashes (the one being replaced included)."""
    n = int(config.get("password_history") or 0)
    if n <= 0 or not old_hash:
        return
    conn.execute("INSERT INTO pw_history(user_id,pw_hash,created_at) VALUES(?,?,?)", (uid, old_hash, db.now()))
    conn.execute("DELETE FROM pw_history WHERE user_id=? AND id NOT IN (SELECT id FROM pw_history WHERE user_id=? ORDER BY id DESC LIMIT ?)", (uid, uid, n))


def _check_history(conn, uid, new):
    n = int(config.get("password_history") or 0)
    if n <= 0:
        return
    for r in conn.execute("SELECT pw_hash FROM pw_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, n)):
        if check_password(new, r["pw_hash"]):
            raise AuthError("新密码不能与最近 %d 次使用过的密码相同" % n, 400)


def create_user(conn, actor, username, display_name, password, roles, must_change=False, email=""):
    if not isinstance(username, str):
        raise AuthError("用户名必须是文本", 400)
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{3,32}", username):
        raise AuthError("用户名需 3–32 位，仅限字母、数字、_ . -", 400)
    if not isinstance(display_name, str) or not display_name.strip():
        raise AuthError("请填写姓名", 400)
    if len(display_name.strip()) > 100:
        raise AuthError("姓名过长", 400)
    roles = check_roles(roles)
    validate_password(password)
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise AuthError("用户名已存在", 409)
    email = check_email(email)
    cur = conn.execute(
        "INSERT INTO users(username,display_name,roles,pw_hash,must_change,created_at,email,pw_changed_at) VALUES(?,?,?,?,?,?,?,?)",
        (username, display_name.strip(), json.dumps(roles), hash_password(password), 1 if must_change else 0, db.now(), email, db.now()))
    uid = cur.lastrowid
    audit.log(conn, actor or "system", "user.create", "user", uid, None,
              {"username": username, "display_name": display_name.strip(), "roles": roles})
    return uid


# ------------------------------------------------------------------ login throttling (M4)
_state_lock = threading.Lock()
_fails = {}            # (username.lower(), ip) -> [timestamps of failures in the last minute]
_pseudo = {}           # username.lower() -> {"n": failures, "until": datetime|None}   (names that do not exist)
_pseudo_logged = {}    # username.lower() -> datetime of the last audit record for an unknown name


def reset_limits():
    with _state_lock:
        _fails.clear(); _pseudo.clear(); _pseudo_logged.clear()


def _purge(now):
    if len(_fails) > 4000:
        for k in [k for k, v in _fails.items() if not v or (now - v[-1]).total_seconds() > 60]:
            _fails.pop(k, None)
    if len(_pseudo) > 4000:
        for k in [k for k, v in _pseudo.items() if not v["until"] or v["until"] < now]:
            _pseudo.pop(k, None)
    if len(_pseudo_logged) > 4000:
        _pseudo_logged.clear()


def _rate_limited(key, now):
    with _state_lock:
        lst = [t for t in _fails.get(key, []) if (now - t).total_seconds() < 60]
        _fails[key] = lst
        return len(lst) >= config.get("login_rate_max")


def _note_fail(key, now):
    with _state_lock:
        _fails.setdefault(key, []).append(now)
        _purge(now)


def login(username, password, ip=None):
    """Authenticate.  Failure counters / audit are committed BEFORE the error is raised (outside the tx).
    Every outcome except success and throttling costs one bcrypt comparison, and an unknown user, a wrong
    password and a deactivated user's wrong password all return the same message and status."""
    uname = (username if isinstance(username, str) else "")[:128]
    pw = password if isinstance(password, str) else ""
    key = (uname.lower(), ip or "")
    now = _utcnow()
    if _rate_limited(key, now):
        raise AuthError("尝试过于频繁，请稍后再试", 429)
    with db.read() as conn:
        u0 = conn.execute("SELECT pw_hash FROM users WHERE username=?", (uname,)).fetchone()
    pw_ok = check_password(pw, u0["pw_hash"] if u0 else _dummy_hash()) and u0 is not None   # bcrypt outside any lock
    err = None
    result = None
    with db.tx() as conn:
        now = _utcnow()
        conn.execute("DELETE FROM sessions WHERE expires_at<?", (db.now(),))        # L13
        u = conn.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
        if u is None:
            lname = uname.lower()
            with _state_lock:
                ps = _pseudo.setdefault(lname, {"n": 0, "until": None})
                locked_now = bool(ps["until"] and ps["until"] > now)
                if not locked_now:
                    ps["n"] += 1
                    if ps["n"] >= config.get("max_failed_logins"):
                        ps["until"] = now + dt.timedelta(minutes=config.get("lock_minutes"))
                        ps["n"] = 0
                last = _pseudo_logged.get(lname)
                do_log = (not locked_now) and (last is None or (now - last).total_seconds() > config.get("lock_minutes") * 60)
                if do_log:
                    _pseudo_logged[lname] = now
            if do_log:
                audit.log(conn, "anonymous", "login.fail", "user", None, None, {"username": uname[:64], "why": "unknown"})
            err = AuthError(GENERIC_LOCK, 423) if locked_now else AuthError(GENERIC_FAIL)
        elif u["locked_until"] and _parse(u["locked_until"]) > now:
            err = AuthError(GENERIC_LOCK, 423)
        elif not pw_ok:
            n = u["failed_count"] + 1
            locked = None
            if n >= config.get("max_failed_logins"):
                locked = _iso(now + dt.timedelta(minutes=config.get("lock_minutes")))
                n = 0
            conn.execute("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (n, locked, u["id"]))
            audit.log(conn, u["username"], "login.fail", "user", u["id"], None, {"locked": bool(locked)})
            err = AuthError(GENERIC_FAIL)
        elif not u["active"]:
            err = AuthError("账号已停用，请联系管理员", 403)         # only reached with a correct password
        else:
            conn.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (u["id"],))
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions(token_hash,user_id,created_at,last_seen,expires_at) VALUES(?,?,?,?,?)",
                         (db.sha256(token), u["id"], db.now(), db.now(),
                          _iso(now + dt.timedelta(hours=config.get("session_hours")))))
            audit.log(conn, dict(u), "login", "user", u["id"], None, {})
            u = dict(u)
            maxd = int(config.get("password_max_days") or 0)
            if maxd:                                                     # password expiry: force a change at login
                if not u.get("pw_changed_at"):
                    conn.execute("UPDATE users SET pw_changed_at=? WHERE id=?", (db.now(), u["id"]))
                elif (now - _parse(u["pw_changed_at"])).days >= maxd and not u["must_change"]:
                    conn.execute("UPDATE users SET must_change=1 WHERE id=?", (u["id"],))
                    u["must_change"] = 1
                    audit.log(conn, u, "user.password_expired", "user", u["id"], None, {"max_days": maxd})
            result = (token, u)
    if err:
        if err.status in (401, 423):
            _note_fail(key, _utcnow())
        raise err
    return result


# ------------------------------------------------------------------ sessions (L10)
def lookup_session(conn, token):
    """Read-only session check.  Returns (user dict | None, action) where action is None, 'touch'
    (last_seen older than 60 s) or 'expire' (delete the session)."""
    if not token or not isinstance(token, str):
        return None, None
    h = db.sha256(token)
    s = conn.execute("SELECT * FROM sessions WHERE token_hash=?", (h,)).fetchone()
    if not s:
        return None, None
    now = _utcnow()
    idle = (now - _parse(s["last_seen"])).total_seconds()
    if _parse(s["expires_at"]) < now or idle > config.get("idle_minutes") * 60:
        return None, "expire"
    u = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (s["user_id"],)).fetchone()
    if not u:
        return None, None
    d = dict(u)
    d["roles"] = db.jl(d["roles"], [])
    return d, ("touch" if idle > 60 else None)


def apply_session_action(conn, token, action):
    h = db.sha256(token)
    if action == "expire":
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (h,))
    elif action == "touch":
        conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (db.now(), h))


def user_for_token(conn, token):
    """Validate a session token inside a write transaction (kept for the logout path)."""
    u, act = lookup_session(conn, token)
    if act:
        apply_session_action(conn, token, act)
    return u


def logout(conn, token, user=None):
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (db.sha256(token),))
        if user:
            audit.log(conn, user, "logout", "user", user["id"], None, {})


def change_password(conn, user, new, keep_token=None):
    """Caller must have verified the old password with reauthenticate() first (own transaction)."""
    u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    validate_password(new)
    if check_password(new, u["pw_hash"]):
        raise AuthError("新密码不能与原密码相同", 400)
    _check_history(conn, user["id"], new)
    _remember_password(conn, user["id"], u["pw_hash"])
    conn.execute("UPDATE users SET pw_hash=?, must_change=0, pw_changed_at=? WHERE id=?", (hash_password(new), db.now(), user["id"]))
    if keep_token:
        conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (user["id"], db.sha256(keep_token)))
    else:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    audit.log(conn, user, "user.password_change", "user", user["id"], None, {})


def reauthenticate(user, password, fail_action="signature.auth_fail", fail_msg="电子签名认证失败：口令不正确", fail_status=403):
    """Verify the password again (own transaction so that failure counters and the audit record are kept
    even though the caller then aborts).  Used for e-signatures, re-opening, status regression and the
    old-password check of a password change.  Raises AuthError on failure."""
    pw = password if isinstance(password, str) else ""
    err = None
    with db.read() as conn:
        u0 = conn.execute("SELECT pw_hash FROM users WHERE id=?", (user["id"],)).fetchone()
    ok = bool(u0) and check_password(pw, u0["pw_hash"])
    with db.tx() as conn:
        u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if u["locked_until"] and _parse(u["locked_until"]) > _utcnow():
            err = AuthError("账号已临时锁定", 423)
        elif not ok:
            n = u["failed_count"] + 1
            locked = None
            if n >= config.get("max_failed_logins"):
                locked = _iso(_utcnow() + dt.timedelta(minutes=config.get("lock_minutes")))
                n = 0
            conn.execute("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (n, locked, user["id"]))
            audit.log(conn, user, fail_action, "user", user["id"], None, {"locked": bool(locked)})
            err = AuthError(fail_msg, fail_status)
        else:
            conn.execute("UPDATE users SET failed_count=0 WHERE id=?", (user["id"],))
    if err:
        raise err
    return True


def admin_reset_password(conn, actor, target_id, new_password):
    validate_password(new_password)
    t = conn.execute("SELECT pw_hash FROM users WHERE id=?", (target_id,)).fetchone()
    if t:
        _remember_password(conn, target_id, t["pw_hash"])
    conn.execute("UPDATE users SET pw_hash=?, must_change=1, failed_count=0, locked_until=NULL, pw_changed_at=? WHERE id=?",
                 (hash_password(new_password), db.now(), target_id))
    conn.execute("DELETE FROM sessions WHERE user_id=?", (target_id,))
    audit.log(conn, actor, "user.password_reset", "user", target_id, None, {})
