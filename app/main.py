"""MethodFlow web API (FastAPI) + static single-page app."""
import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid

from fastapi import Body, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from . import audit, auth, compliance, config, db, docgen, kb_links, kb_seed, notifier, records, stats, templates_data, validate, workflow
from .auth import AuthError
from .workflow import WFError

COOKIE = "mf_session"
MUST_CHANGE_OK = ("/api/me", "/api/me/password", "/api/logout")      # everything else needs a fresh password first
LOOPBACK = ("127.0.0.1", "localhost", "::1")
log = logging.getLogger("methodflow")


# ------------------------------------------------------------------ startup
def _seed_kb():
    """Built-in knowledge base: insert the items that are missing (by title).  Idempotent; never overwrites."""
    with db.tx() as conn:
        res = workflow.sync_builtin_kb(conn)
        if res["added"]:
            audit.log(conn, "system", "kb.sync", "kb", None, None, res)
        n_links = kb_links.sync_builtin(conn)
        if n_links:
            audit.log(conn, "system", "kb.links.sync", "kb_links", None, None, {"added": n_links})
    return res


def _backup_loop():
    while True:
        time.sleep(24 * 3600)
        try:
            workflow.backup_now("daily")
        except Exception as e:  # pragma: no cover
            print("backup failed:", e)


@contextlib.asynccontextmanager
async def lifespan(app):
    db.init_db()
    _seed_kb()
    try:
        workflow.backup_now("startup")
    except Exception as e:  # pragma: no cover
        print("startup backup failed:", e)
    threading.Thread(target=_backup_loop, daemon=True).start()
    yield


app = FastAPI(title="MethodFlow", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


# ------------------------------------------------------------------ error handling (M8): never leak a stack trace
@app.exception_handler(WFError)
async def _wf_err(request, exc):
    return JSONResponse({"error": str(exc), "detail": exc.detail}, status_code=exc.status)


@app.exception_handler(AuthError)
async def _auth_err(request, exc):
    body = {"error": str(exc)}
    if exc.extra:
        body.update(exc.extra)
    return JSONResponse(body, status_code=exc.status)


@app.exception_handler(validate.Invalid)
async def _invalid(request, exc):
    return JSONResponse({"error": str(exc), "detail": None}, status_code=400)


@app.exception_handler(RequestValidationError)
async def _req_invalid(request, exc):
    return JSONResponse({"error": "请求格式或参数无效", "detail": None}, status_code=400)


async def _bad_input(request, exc):
    log.warning("bad input on %s %s: %r", request.method, request.url.path, exc)
    return JSONResponse({"error": "请求内容无效", "detail": None}, status_code=400)


for _exc_type in (TypeError, ValueError, AttributeError, KeyError, OverflowError):
    app.add_exception_handler(_exc_type, _bad_input)


async def _server_err(request, exc):
    log.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse({"error": "服务器内部错误", "detail": None}, status_code=500)


app.add_exception_handler(sqlite3.Error, _server_err)


# ------------------------------------------------------------------ request body limits (M5)
UPLOAD_RE = re.compile(r"^/api/methods/\d+/attachments$")


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Pure ASGI middleware: JSON endpoints accept at most `max_json_mb`; the upload endpoint at most
    `max_upload_mb` (+1 MB slack, the handler enforces the exact limit while streaming)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            return await self.app(scope, receive, send)
        if scope["method"] == "POST" and UPLOAD_RE.match(scope["path"]):
            limit = (int(config.get("max_upload_mb")) + 1) * 1024 * 1024
        else:
            limit = int(config.get("max_json_mb")) * 1024 * 1024
        cl = dict(scope["headers"]).get(b"content-length")
        started = False

        async def reply_413():
            body = json.dumps({"error": "请求体过大", "detail": None}, ensure_ascii=False).encode("utf-8")
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        if cl and cl.isdigit() and int(cl) > limit:
            return await reply_413()
        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    raise _TooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await reply_413()


app.add_middleware(BodyLimitMiddleware)       # innermost: closest to the endpoints


def _host_ok(host_header):
    """L7: Host header validation (DNS-rebinding protection).  Automatic: loopback deployments accept loopback
    names only; LAN deployments accept anything unless `allowed_hosts` is configured."""
    h = (host_header or "").strip().lower()
    name = (h.split("]")[0] + "]") if h.startswith("[") else h.split(":")[0]
    allowed = config.get("allowed_hosts")
    if allowed:
        return name in [str(a).lower() for a in allowed]
    if config.get("host") in LOOPBACK:
        return name in ("127.0.0.1", "localhost", "[::1]", "testserver")
    return True


def _cookie_secure():
    v = config.get("cookie_secure")
    if v is None:
        return config.get("host") not in LOOPBACK
    return bool(v)


CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"


@app.middleware("http")
async def _security(request: Request, call_next):
    if not _host_ok(request.headers.get("host")):
        return JSONResponse({"error": "不允许的主机名"}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
        if request.headers.get("x-requested-with") != "MethodFlow":
            return JSONResponse({"error": "缺少请求标头"}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Content-Security-Policy"] = CSP
    return resp


# ------------------------------------------------------------------ sessions
def current_user(request: Request):
    """Authenticate from the session cookie.  Read-only connection; `last_seen` is only written when older
    than 60 s.  A user who must change the password may only call /api/me, /api/me/password, /api/logout."""
    token = request.cookies.get(COOKIE)
    with db.read() as conn:
        u, act = auth.lookup_session(conn, token)
    if act:
        try:
            with db.tx() as conn:
                auth.apply_session_action(conn, token, act)
        except sqlite3.OperationalError:       # database busy: the touch can wait for the next request
            pass
    if not u:
        raise AuthError("未登录或会话已过期", 401)
    if u["must_change"] and request.url.path.rstrip("/") not in MUST_CHANGE_OK:
        raise AuthError("须先修改密码", 403, {"must_change": True})
    return u


def _roles_required(u, *roles):
    if not (set(u["roles"]) & set(roles)):
        raise AuthError("权限不足", 403)


def _pub(u):
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "roles": u["roles"], "must_change": bool(u["must_change"]),
            "email": (u["email"] if "email" in u.keys() else "") or ""}


def _client_ip(request):
    return request.client.host if request.client else ""


def _set_cookie(response, token):
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/",
                        max_age=int(config.get("session_hours")) * 3600, secure=_cookie_secure())


def _str_field(payload, key, name, default=""):
    v = payload.get(key, default)
    if v is None:
        return default
    if not isinstance(v, str):
        raise validate.Invalid("%s 必须是文本" % name)
    return v


# ------------------------------------------------------------------ auth endpoints
@app.get("/api/state")
def state():
    with db.read() as conn:
        n = auth.user_count(conn)
    return {"needs_setup": n == 0, "app": "MethodFlow", "version": "0.4.0", "require_change_reason": bool(config.get("require_change_reason")), "rpn_threshold": config.get("rpn_threshold"),
            "severity_threshold": config.get("severity_threshold"), "min_password_length": config.get("min_password_length"),
            "setup_token_required": bool(config.get("setup_token"))}


@app.post("/api/setup")
def setup(request: Request, response: Response, payload: dict = Body(...)):
    tok = config.get("setup_token")
    with db.tx() as conn:
        if auth.user_count(conn) > 0:
            raise AuthError("系统已初始化", 409)
        if tok:
            given = payload.get("setup_token")
            if not isinstance(given, str) or not hmac.compare_digest(given.encode("utf-8"), str(tok).encode("utf-8")):
                raise AuthError("初始化口令（setup_token）不正确", 403)
        auth.create_user(conn, "system", payload.get("username"), payload.get("display_name"), payload.get("password", ""), ["admin", "author", "reviewer", "approver"])
    token, u = auth.login(payload.get("username"), payload.get("password"), _client_ip(request))
    _set_cookie(response, token)
    u["roles"] = db.jl(u["roles"], [])
    return {"user": _pub(u)}


@app.post("/api/login")
def login(request: Request, response: Response, payload: dict = Body(...)):
    token, u = auth.login(payload.get("username"), payload.get("password"), _client_ip(request))
    _set_cookie(response, token)
    u["roles"] = db.jl(u["roles"], [])
    return {"user": _pub(u)}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    with db.tx() as conn:
        u = auth.user_for_token(conn, token)
        auth.logout(conn, token, u)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"user": _pub(current_user(request))}


@app.post("/api/me/password")
def change_pw(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    old, new = payload.get("old", ""), payload.get("new", "")
    if not isinstance(new, str):
        raise AuthError("新密码必须是文本", 400)
    # the old password is checked in its own transaction so that failures count towards the lockout (M3)
    auth.reauthenticate(u, old, "user.password_check_fail", "原密码不正确", 400)
    with db.tx() as conn:
        auth.change_password(conn, u, new, keep_token=request.cookies.get(COOKIE))
    return {"ok": True}


# ------------------------------------------------------------------ users (admin)
@app.get("/api/users")
def users(request: Request):
    u = current_user(request)
    with db.read() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY display_name").fetchall()
    is_admin = "admin" in u["roles"]
    # L9: ordinary users only see the active accounts they may pick as team members
    return [{"id": r["id"], "username": r["username"], "display_name": r["display_name"], "roles": db.jl(r["roles"], []), "active": bool(r["active"]),
             "email": (r["email"] or "") if is_admin else ""} for r in rows if is_admin or r["active"]]


@app.post("/api/users")
def users_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "admin")
    roles = payload.get("roles")
    with db.tx() as conn:
        uid = auth.create_user(conn, u, payload.get("username"), payload.get("display_name"), payload.get("password", ""),
                               roles if roles else ["author"], must_change=True, email=payload.get("email", ""))
    return {"id": uid}


@app.patch("/api/users/{uid}")
def users_patch(uid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "admin")
    with db.tx() as conn:
        t = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not t:
            raise WFError("用户不存在", 404)
        changes = {}
        if "display_name" in payload:
            dn = _str_field(payload, "display_name", "姓名").strip()
            if len(dn) > 100:
                raise validate.Invalid("姓名过长")
            if dn:
                conn.execute("UPDATE users SET display_name=? WHERE id=?", (dn, uid)); changes["display_name"] = dn
        if "email" in payload:
            em = auth.check_email(payload["email"])
            conn.execute("UPDATE users SET email=? WHERE id=?", (em, uid)); changes["email"] = em
        if "roles" in payload:
            roles = auth.check_roles(payload["roles"])
            if uid == u["id"] and "admin" not in roles:
                raise WFError("不能移除自己的管理员角色")
            conn.execute("UPDATE users SET roles=? WHERE id=?", (json.dumps(roles), uid)); changes["roles"] = roles
        if "active" in payload:
            active = validate.boolean(payload["active"], "active")
            if uid == u["id"] and not active:
                raise WFError("不能停用自己")
            conn.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, uid)); changes["active"] = active
            if not active:
                conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        if payload.get("reset_password"):
            auth.admin_reset_password(conn, u, uid, payload["reset_password"]); changes["password"] = "reset"
        audit.log(conn, u, "user.update", "user", uid, None, changes)
    return {"ok": True}


# ------------------------------------------------------------------ templates / config
@app.get("/api/templates")
def templates(request: Request):
    current_user(request)
    return templates_data.list_templates()


# ------------------------------------------------------------------ dashboard
@app.get("/api/dashboard")
def dashboard(request: Request):
    u = current_user(request)
    with db.read() as conn:
        return workflow.dashboard(conn, u)


# ------------------------------------------------------------------ notifications (in-app)
@app.get("/api/notifications")
def notifications(request: Request, unread: int = 0, limit: int = 60):
    u = current_user(request)
    limit = max(1, min(int(limit), 200))
    with db.read() as conn:
        n_unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (u["id"],)).fetchone()[0]
        q = "SELECT id, created_at, kind, method_id, stage_key, title, body, read FROM notifications WHERE user_id=?"
        if unread:
            q += " AND read=0"
        rows = [dict(r) for r in conn.execute(q + " ORDER BY id DESC LIMIT ?", (u["id"], limit))]
    return {"unread": n_unread, "items": rows}


@app.post("/api/notifications/read")
def notifications_read(request: Request, payload: dict = Body(default={})):
    u = current_user(request)
    ids = payload.get("ids")
    with db.tx() as conn:
        if payload.get("all"):
            conn.execute("UPDATE notifications SET read=1 WHERE user_id=?", (u["id"],))
        elif isinstance(ids, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in ids) and len(ids) <= 500:
            conn.executemany("UPDATE notifications SET read=1 WHERE user_id=? AND id=?", [(u["id"], i) for i in ids])
        else:
            raise WFError("请提供 ids（整数列表）或 all=true")
        n = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (u["id"],)).fetchone()[0]
    return {"unread": n}


# ------------------------------------------------------------------ projects
@app.get("/api/projects")
def project_list(request: Request, q: str = "", status: str = ""):
    u = current_user(request)
    with db.read() as conn:
        return workflow.list_projects(conn, u, q, status)


@app.post("/api/projects")
def project_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "author", "admin")
    with db.tx() as conn:
        pid = workflow.create_project(conn, u, payload)
    return {"id": pid}


@app.get("/api/projects/{pid}")
def project_get(pid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view_project(conn, u, pid)
        return workflow.project_detail(conn, u, workflow.get_project(conn, pid))


@app.patch("/api/projects/{pid}")
def project_patch(pid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    # M2: putting a paused / completed / archived project back to 'active' needs a reason AND the password
    with db.read() as conn:
        workflow.require_view_project(conn, u, pid)
        p = workflow.get_project(conn, pid)
        is_owner = "owner" in workflow.project_roles(conn, pid, u["id"])
    if is_owner and payload.get("status") == "active" and p["status"] != "active":
        if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
            raise WFError("将项目恢复为进行中须填写原因")
        auth.reauthenticate(u, payload.get("password", ""))
    with db.tx() as conn:
        workflow.require_view_project(conn, u, pid)
        workflow.update_project(conn, u, pid, payload)
    return {"ok": True}


@app.put("/api/projects/{pid}/members")
def project_members(pid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view_project(conn, u, pid)
        workflow.set_project_members(conn, u, pid, payload.get("members") or [])
    return {"ok": True}


@app.get("/api/projects/{pid}/methods")
def project_methods(pid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view_project(conn, u, pid)
        return workflow.project_methods(conn, u, pid)


@app.post("/api/projects/{pid}/methods")
def project_method_create(pid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "author", "admin")
    with db.tx() as conn:
        workflow.require_view_project(conn, u, pid)
        mid = workflow.create_method(conn, u, pid, payload)
    return {"id": mid}


# ------------------------------------------------------------------ methods
@app.get("/api/methods")
def method_list(request: Request, q: str = "", status: str = "", project_id: int = 0, technique: str = "", lifecycle: str = ""):
    u = current_user(request)
    with db.read() as conn:
        return workflow.list_methods(conn, u, q, status, project_id or None, technique, lifecycle)


@app.get("/api/methods/{mid}")
def method_get(mid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return workflow.method_detail(conn, u, workflow.get_method(conn, mid))


@app.patch("/api/methods/{mid}")
def method_patch(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        m = workflow.get_method(conn, mid)
        is_owner = "owner" in workflow.method_roles(conn, mid, u["id"])
    if is_owner and payload.get("status") == "active" and m["status"] != "active":
        if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
            raise WFError("将方法恢复为进行中须填写原因")
        auth.reauthenticate(u, payload.get("password", ""))
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.update_method(conn, u, mid, payload)
    return {"ok": True}


@app.put("/api/methods/{mid}/members")
def method_members(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.set_members(conn, u, mid, payload.get("members") or [])
    return {"ok": True}


@app.post("/api/methods/{mid}/clone")
def method_clone(mid: int, request: Request, payload: dict = Body(default={})):
    u = current_user(request)
    _roles_required(u, "author", "admin")
    with db.tx() as conn:
        nid = workflow.clone_method(conn, u, mid, payload.get("title"), payload.get("project_id"))
    return {"id": nid}


@app.post("/api/methods/{mid}/lifecycle")
def method_lifecycle(mid: int, request: Request, payload: dict = Body(...)):
    """Record a lifecycle change.  Needs the method owner / approver, a reason and the password (re-authentication)."""
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        workflow.check_lifecycle_allowed(conn, u, mid)
    lifecycle, reason = payload.get("lifecycle"), payload.get("reason")
    if not isinstance(lifecycle, str) or lifecycle not in workflow.LIFECYCLE_LABELS:
        raise WFError("无效的生命周期（%s）" % " / ".join(workflow.LIFECYCLE_LABELS))
    if not isinstance(reason, str) or not reason.strip():
        raise WFError("变更生命周期须填写原因")
    auth.reauthenticate(u, payload.get("password", ""))
    with db.tx() as conn:
        workflow.set_lifecycle(conn, u, mid, lifecycle, reason)
    return {"ok": True}


# ------------------------------------------------------------------ stages
@app.get("/api/methods/{mid}/stages/{key}")
def stage_get(mid: int, key: str, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        p = workflow.get_method(conn, mid)
        return workflow.stage_detail(conn, u, p, workflow.get_stage(conn, mid, key))


@app.put("/api/methods/{mid}/stages/{key}")
def stage_put(mid: int, key: str, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.save_stage(conn, u, mid, key, payload)
        p = workflow.get_method(conn, mid)
        return workflow.stage_detail(conn, u, p, workflow.get_stage(conn, mid, key))


@app.get("/api/methods/{mid}/stages/{key}/checks")
def stage_checks(mid: int, key: str, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return workflow.gate_checks(conn, workflow.get_method(conn, mid), workflow.get_stage(conn, mid, key))


@app.get("/api/methods/{mid}/stages/{key}/diff")
def stage_diff(mid: int, key: str, request: Request, rev_from: int = 0, rev_to: int = 0):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return workflow.stage_diff(conn, mid, key, rev_from or None, rev_to or None)


@app.post("/api/methods/{mid}/stages/{key}/submit")
def stage_submit(mid: int, key: str, request: Request, payload: dict = Body(default={})):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.submit_stage(conn, u, mid, key, payload.get("comment", ""))
    return {"ok": True}


@app.post("/api/methods/{mid}/stages/{key}/withdraw")
def stage_withdraw(mid: int, key: str, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.withdraw_stage(conn, u, mid, key, payload.get("reason", ""))
    return {"ok": True}


@app.post("/api/methods/{mid}/stages/{key}/review")
def stage_review(mid: int, key: str, request: Request, payload: dict = Body(...)):
    """E-signature.  The request must carry the `revision` and `expected_hash` (stage_detail's `revision` and
    `hash`) of the content the reviewer actually looked at (H5); a mismatch is 409."""
    u = current_user(request)
    revision, expected_hash = payload.get("revision"), payload.get("expected_hash")
    if isinstance(revision, bool) or not isinstance(revision, int) or not isinstance(expected_hash, str) or not expected_hash:
        raise WFError("签名请求须带 revision（整数）和 expected_hash（字符串）")
    decision, comment = payload.get("decision"), payload.get("comment", "")
    if comment is not None and not isinstance(comment, str):
        raise WFError("意见必须是文本")
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        p = workflow.get_method(conn, mid)
        s = workflow.get_stage(conn, mid, key)
        role, why = workflow.pending_role_for(conn, u, p, s)
        if not role:
            raise WFError(why, 403)
        if not isinstance(decision, str) or decision not in ("approve", "reject"):
            raise WFError("决定无效")
        workflow.check_binding(conn, mid, s, revision, expected_hash)
    if decision == "reject" and not (comment or "").strip():
        raise WFError("退回须填写原因")
    auth.reauthenticate(u, payload.get("password", ""))   # electronic-signature authentication
    with db.tx() as conn:
        workflow.review_stage(conn, u, mid, key, decision, comment or "", revision, expected_hash)
    return {"ok": True}


@app.post("/api/methods/{mid}/stages/{key}/reopen")
def stage_reopen(mid: int, key: str, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise WFError("原因必须是文本")
    if not (reason or "").strip():
        raise WFError("重新打开须填写原因")
    auth.reauthenticate(u, payload.get("password", ""))
    with db.tx() as conn:
        affected = workflow.reopen_stage(conn, u, mid, key, reason)
    return {"ok": True, "affected": affected}


@app.post("/api/methods/{mid}/stages/{key}/recertify")
def stage_recertify(mid: int, key: str, request: Request, payload: dict = Body(default={})):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        workflow.recertify_stage(conn, u, mid, key, payload.get("comment", ""))
    return {"ok": True}


# ------------------------------------------------------------------ experiments
@app.get("/api/methods/{mid}/experiments")
def exp_list(mid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return workflow.list_experiments(conn, mid)


@app.post("/api/methods/{mid}/experiments")
def exp_create(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        eid = workflow.create_experiment(conn, u, mid, payload)
    return {"id": eid}


@app.post("/api/methods/{mid}/experiments/bulk")
def exp_bulk(mid: int, request: Request, payload: dict = Body(...)):
    """Start or cancel several experiments at once; each one is checked on its own, failures are reported per experiment."""
    u = current_user(request)
    ids = payload.get("ids")
    action = payload.get("action")
    if not isinstance(ids, list) or not ids or len(ids) > 100 or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        raise WFError("请提供要操作的实验 ids（1–100 个整数）")
    if action not in ("start", "cancel", "confirm_examples"):
        raise WFError("action 须为 start、cancel 或 confirm_examples")
    reason = payload.get("reason", "")
    done, failed = [], []
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        for eid in ids:
            conn.execute("SAVEPOINT bulk_one")
            try:
                e = workflow.get_experiment(conn, eid)
                if e["method_id"] != mid:
                    raise WFError("实验不属于该方法", 404)
                if action == "confirm_examples":
                    workflow.confirm_experiment_examples(conn, u, e)
                else:
                    workflow.set_experiment_status(conn, u, eid, "running" if action == "start" else "cancelled", reason)
                conn.execute("RELEASE bulk_one")
                done.append(eid)
            except WFError as err:
                conn.execute("ROLLBACK TO bulk_one")
                conn.execute("RELEASE bulk_one")
                failed.append({"id": eid, "error": str(err)})
    return {"done": done, "failed": failed}


@app.post("/api/methods/{mid}/reschedule")
def method_reschedule(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        moved = workflow.reschedule(conn, u, mid, payload.get("from_stage"), payload.get("start_date"))
    return {"moved": moved}


@app.post("/api/calc/{name}")
def calculator(name: str, request: Request, payload: dict = Body(...)):
    """Statistics calculators (app/stats.py).  Pure computation: nothing is stored; the user copies rows to a result table."""
    current_user(request)
    try:
        return stats.run(name, payload)
    except ValueError as e:
        raise WFError(str(e))
    except (OverflowError, ZeroDivisionError):
        raise WFError("计算失败：输入的数值超出范围或会导致除以零")


# ------------------------------------------------------------------ registry (materials, equipment)
@app.get("/api/materials")
def materials_list(request: Request, q: str = "", kind: str = "", state: str = "", all: int = 0):
    u = current_user(request)
    with db.read() as conn:
        return records.list_materials(conn, q, kind, state, bool(all) and bool({"admin", "approver"} & set(u["roles"])))


@app.post("/api/materials")
def materials_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        return {"id": records.create_material(conn, u, payload)}


@app.put("/api/materials/{mid}")
def materials_update(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        records.update_material(conn, u, mid, payload)
    return {"ok": True}


@app.delete("/api/materials/{mid}")
def materials_delete(mid: int, request: Request, restore: int = 0):
    u = current_user(request)
    with db.tx() as conn:
        records.set_material_active(conn, u, mid, bool(restore))
    return {"ok": True}


@app.get("/api/equipment")
def equipment_list(request: Request, q: str = "", state: str = "", all: int = 0):
    u = current_user(request)
    with db.read() as conn:
        return records.list_equipment(conn, q, state, bool(all) and bool({"admin", "approver"} & set(u["roles"])))


@app.post("/api/equipment")
def equipment_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        return {"id": records.create_equipment(conn, u, payload)}


@app.put("/api/equipment/{eid}")
def equipment_update(eid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        records.update_equipment(conn, u, eid, payload)
    return {"ok": True}


@app.delete("/api/equipment/{eid}")
def equipment_delete(eid: int, request: Request, restore: int = 0):
    u = current_user(request)
    with db.tx() as conn:
        records.set_equipment_active(conn, u, eid, bool(restore))
    return {"ok": True}


@app.get("/api/registry/alerts")
def registry_alerts(request: Request):
    current_user(request)
    with db.read() as conn:
        return records.registry_alerts(conn)


@app.get("/api/registry/options")
def registry_options(request: Request):
    current_user(request)
    return {"material_kinds": [{"key": k, "label": v} for k, v in records.MATERIAL_KINDS.items()],
            "material_status": [{"key": k, "label": v} for k, v in records.MATERIAL_STATUS.items()],
            "equipment_status": [{"key": k, "label": v} for k, v in records.EQUIPMENT_STATUS.items()],
            "run_outcomes": [{"key": k, "label": v} for k, v in records.RUN_OUTCOMES.items()],
            "deviation_classes": [{"key": k, "label": v} for k, v in records.DEV_CLASS.items()],
            "deviation_status": [{"key": k, "label": v} for k, v in records.DEV_STATUS.items()]}


# ------------------------------------------------------------------ run records and deviations
@app.get("/api/methods/{mid}/runs")
def runs_list(mid: int, request: Request, experiment_id: int = 0):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return records.list_runs(conn, mid, experiment_id or None)


@app.post("/api/methods/{mid}/runs")
def runs_create(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        return {"id": records.create_run(conn, u, mid, payload)}


@app.put("/api/runs/{rid}")
def runs_update(rid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        records.update_run(conn, u, rid, payload)
    return {"ok": True}


@app.post("/api/runs/{rid}/verify")
def runs_verify(rid: int, request: Request):
    u = current_user(request)
    with db.tx() as conn:
        records.verify_run(conn, u, rid)
    return {"ok": True}


@app.get("/api/methods/{mid}/deviations")
def deviations_list(mid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return records.list_deviations(conn, mid)


@app.post("/api/methods/{mid}/deviations")
def deviations_create(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        return {"id": records.create_deviation(conn, u, mid, payload)}


@app.put("/api/deviations/{did}")
def deviations_update(did: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        records.update_deviation(conn, u, did, payload)
    return {"ok": True}


@app.post("/api/deviations/{did}/close")
def deviations_close(did: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    auth.reauthenticate(u, payload.get("password", ""))          # closing is an electronic signature
    with db.tx() as conn:
        records.close_deviation(conn, u, did, payload.get("note", ""))
    return {"ok": True}


@app.post("/api/deviations/{did}/reopen")
def deviations_reopen(did: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    auth.reauthenticate(u, payload.get("password", ""))
    with db.tx() as conn:
        records.reopen_deviation(conn, u, did, payload.get("reason", ""))
    return {"ok": True}


@app.get("/api/experiments/{eid}")
def exp_get(eid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        e = workflow.get_experiment(conn, eid)
        workflow.require_view(conn, u, e["method_id"])
        e["attachments_list"] = workflow.list_attachments(conn, e["method_id"], experiment_id=eid)
        return e


@app.put("/api/experiments/{eid}")
def exp_put(eid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        e = workflow.get_experiment(conn, eid)
        workflow.require_view(conn, u, e["method_id"])
        workflow.update_experiment(conn, u, eid, payload)
        return workflow.get_experiment(conn, eid)


@app.post("/api/experiments/{eid}/status")
def exp_status(eid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        e = workflow.get_experiment(conn, eid)
        workflow.require_view(conn, u, e["method_id"])
        workflow.set_experiment_status(conn, u, eid, payload.get("status"), payload.get("reason", ""))
    return {"ok": True}


@app.delete("/api/experiments/{eid}")
def exp_delete(eid: int, request: Request, reason: str = ""):
    u = current_user(request)
    with db.tx() as conn:
        e = workflow.get_experiment(conn, eid)
        workflow.require_view(conn, u, e["method_id"])
        workflow.delete_experiment(conn, u, eid, reason)
    return {"ok": True}


# ------------------------------------------------------------------ attachments
@app.post("/api/methods/{mid}/attachments")
async def att_upload(mid: int, request: Request, filename: str, stage_key: str = "", experiment_id: int = 0, description: str = ""):
    """Streams the body to a temp file (size-capped, hashed on the fly).  All database work happens in worker
    threads; permissions and locks are checked BEFORE the body is read, and again when the record is committed.
    `filename` arrives already percent-decoded by the framework (the client sends it single-encoded)."""
    u = await run_in_threadpool(current_user, request)
    sk, eid = stage_key or None, experiment_id or None

    def precheck():
        with db.read() as conn:
            workflow.require_view(conn, u, mid)
            workflow.check_attachment_target(conn, u, mid, sk, eid)

    def commit(tmp, size, sha):
        with db.tx() as conn:
            workflow.require_view(conn, u, mid)
            return workflow.add_attachment_file(conn, u, mid, sk, eid, filename, tmp, size, sha, description)

    await run_in_threadpool(precheck)
    limit = int(config.get("max_upload_mb")) * 1024 * 1024
    too_big = WFError("文件超过 %d MB 限制" % config.get("max_upload_mb"), 413)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        raise too_big
    tmp_dir = config.UPLOADS / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / uuid.uuid4().hex
    sha, size = hashlib.sha256(), 0
    f = open(str(tmp), "wb")
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            if size > limit:
                raise too_big
            sha.update(chunk)
            await run_in_threadpool(f.write, chunk)
        f.close()
        aid = await run_in_threadpool(commit, tmp, size, sha.hexdigest())
    except BaseException:
        try:
            f.close()
        except Exception:
            pass
        try:
            os.remove(str(tmp))
        except OSError:
            pass
        raise
    return {"id": aid}


@app.get("/api/attachments/{aid}/download")
def att_download(aid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        a = workflow.get_attachment(conn, aid)
        workflow.require_view(conn, u, a["method_id"])
    p = config.DATA / a["path"]
    if not p.exists():
        raise WFError("文件丢失，请从备份恢复", 410)
    return FileResponse(str(p), filename=a["filename"], media_type="application/octet-stream")


@app.post("/api/attachments/{aid}/verify")
def att_verify(aid: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        a = workflow.get_attachment(conn, aid)
        workflow.require_view(conn, u, a["method_id"])
    return {"intact": workflow.verify_attachment(a), "sha256": a["sha256"]}


@app.delete("/api/attachments/{aid}")
def att_delete(aid: int, request: Request, reason: str = ""):
    u = current_user(request)
    with db.tx() as conn:
        a = workflow.get_attachment(conn, aid)
        workflow.require_view(conn, u, a["method_id"])
        workflow.delete_attachment(conn, u, aid, reason)
    return {"ok": True}


# ------------------------------------------------------------------ audit
def _audit_rows(conn, where="", args=(), limit=300):
    out = []
    limit = max(1, min(int(limit), 2000))          # L3
    for r in conn.execute("SELECT a.*, m.code AS method_code FROM audit_log a LEFT JOIN methods m ON m.id=a.method_id %s ORDER BY a.id DESC LIMIT ?" % where,
                          list(args) + [limit]):
        d = dict(r)
        d["details"] = db.jl(d["details"], {})
        out.append(d)
    return out


@app.get("/api/methods/{mid}/audit")
def method_audit(mid: int, request: Request, limit: int = 300):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return _audit_rows(conn, "WHERE a.method_id=?", (mid,), limit)


@app.get("/api/projects/{pid}/audit")
def project_audit(pid: int, request: Request, limit: int = 300):
    """Project-level aggregation: the project's own records plus those of all its methods."""
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view_project(conn, u, pid)
        return _audit_rows(conn, "WHERE a.project_id=? OR a.method_id IN (SELECT id FROM methods WHERE project_id=?)", (pid, pid), limit)


@app.get("/api/audit")
def global_audit(request: Request, limit: int = 300):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    with db.read() as conn:
        return _audit_rows(conn, "", (), limit)


@app.get("/api/audit/verify")
def audit_verify(request: Request):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    with db.read() as conn:
        return audit.verify(conn)


# ------------------------------------------------------------------ knowledge base
@app.get("/api/kb")
def kb_list(request: Request, q: str = "", kind: str = "", technique: str = "", stage: str = ""):
    current_user(request)
    with db.read() as conn:
        out = []
        for r in conn.execute("SELECT * FROM kb_items WHERE active=1 ORDER BY kind, id"):
            d = dict(r)
            d["tags"] = db.jl(d["tags"], []); d["techniques"] = db.jl(d["techniques"], []); d["stages"] = db.jl(d["stages"], [])
            if kind and d["kind"] != kind:
                continue
            if technique and d["techniques"] and technique not in d["techniques"] and "all" not in d["techniques"]:
                continue
            if stage and d["stages"] and stage not in d["stages"]:
                continue
            if q and q.lower() not in (d["title"] + d["body"] + " ".join(d["tags"]) + (d["source"] or "")).lower():
                continue
            out.append(d)
        return out


@app.post("/api/kb")
def kb_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "author", "admin")
    title = validate.text(payload.get("title"), "标题", 200, required=True).strip()
    body = validate.text(payload.get("body"), "内容", 50000, required=True).strip()
    kind = validate.text(payload.get("kind", "lesson"), "类型", 40) or "lesson"
    tags = validate.text_list(payload.get("tags"), "标签")
    techniques = validate.text_list(payload.get("techniques"), "适用技术") or ["all"]
    stages = validate.text_list(payload.get("stages"), "适用阶段")
    source = validate.text(payload.get("source", ""), "来源", 500)
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO kb_items(kind,title,body,tags,techniques,stages,source,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (kind, title, body, json.dumps(tags, ensure_ascii=False), json.dumps(techniques), json.dumps(stages), source, u["id"], db.now(), db.now()))
        audit.log(conn, u, "kb.create", "kb", cur.lastrowid, None, {"title": title})
    return {"id": cur.lastrowid}


@app.delete("/api/kb/{kid}")
def kb_delete(kid: int, request: Request):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    with db.tx() as conn:
        conn.execute("UPDATE kb_items SET active=0, updated_at=? WHERE id=?", (db.now(), kid))
        audit.log(conn, u, "kb.deactivate", "kb", kid, None, {})
    return {"ok": True}


@app.get("/api/methods/{mid}/kb")
def method_kb(mid: int, request: Request, stage: str = ""):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return workflow.kb_for(conn, workflow.get_method(conn, mid), stage or None)


@app.post("/api/methods/{mid}/lessons")
def method_lesson(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        p = workflow.get_method(conn, mid)
        kid = workflow.add_lesson(conn, u, p, payload.get("title"), payload.get("body"), payload.get("stage_key"))
    return {"id": kid}


# ------------------------------------------------------------------ documents
@app.post("/api/methods/{mid}/docs")
def doc_generate(mid: int, request: Request, payload: dict = Body(default={})):
    """Generate the Word AND (when LibreOffice is available) the PDF of one document.
    -> {gen_id, docs:[{id, format, filename}], pdf_available, pdf_note}; `id` / `filename` (the .docx) are kept
    for older clients."""
    u = current_user(request)
    kind = payload.get("kind", "plan")
    lang = payload.get("lang", "zh")
    if payload.get("async"):
        # document generation takes 10-60 s (PDF conversion): run it in the background; poll GET /api/jobs/{job_id}
        def work():
            res = docgen.generate(u, mid, kind, lang)
            res["id"], res["filename"] = res["docs"][0]["id"], res["docs"][0]["filename"]
            return res
        return {"job_id": _start_job(u, work)}
    res = docgen.generate(u, mid, kind, lang)
    res["id"], res["filename"] = res["docs"][0]["id"], res["docs"][0]["filename"]
    return res


@app.get("/api/methods/{mid}/docs")
def doc_list(mid: int, request: Request):
    """One row per file (docx / pdf), newest generation first, .docx before .pdf inside a generation."""
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        ok, bad = workflow.method_signatures(conn, mid)
        out = []
        for r in conn.execute("SELECT d.id, d.kind, d.format, d.filename, d.version_label, d.status_label, d.data_hash, d.created_at, d.summary, u.display_name FROM generated_docs d "
                              "LEFT JOIN users u ON u.id=d.created_by WHERE d.method_id=?", (mid,)):
            d = dict(r)
            summ = db.jl(d.pop("summary"), {}) or {}
            d["gen_id"] = summ.get("gen_id") or d["id"]
            d["file_sha256"] = summ.get("file_sha256")
            d["generated_signatures_ok"] = bool(summ.get("signatures_ok", True))     # state when the file was made
            d["signatures_ok"] = ok                                                    # state right now
            d["bad_signatures"] = bad
            out.append(d)
        out.sort(key=lambda d: (-d["gen_id"], 0 if d["format"] == "docx" else 1, d["id"]))
        return out


@app.get("/api/docs/{did}/download")
def doc_download(did: int, request: Request):
    u = current_user(request)
    with db.read() as conn:
        d = conn.execute("SELECT * FROM generated_docs WHERE id=?", (did,)).fetchone()
        if not d:
            raise WFError("文档不存在", 404)
        workflow.require_view(conn, u, d["method_id"])
    p = config.DATA / d["path"]
    if not p.exists():
        raise WFError("文件丢失，请从备份恢复", 410)
    media = "application/pdf" if d["format"] == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(str(p), filename=d["filename"], media_type=media)


@app.get("/api/system/capabilities")
def system_capabilities(request: Request):
    """Any logged-in user: can the server produce PDFs? -> {pdf, pdf_note}"""
    current_user(request)
    with db.read() as conn:
        return docgen.capabilities(conn)


# ------------------------------------------------------------------ admin
def _settings_view(conn):
    st = docgen.get_settings(conn)
    caps = docgen.capabilities(conn)
    st.update({"pdf_available": caps["pdf"], "pdf_note": caps["pdf_note"],
               "soffice_found": docgen.find_soffice(st["soffice_path"]) or "", "defaults": dict(docgen.SETTING_DEFAULTS)})
    return st


@app.get("/api/admin/settings")
def admin_settings_get(request: Request):
    u = current_user(request)
    _roles_required(u, "admin")
    with db.read() as conn:
        return _settings_view(conn)


@app.put("/api/admin/settings")
def admin_settings_put(request: Request, payload: dict = Body(...)):
    """Body: any subset of {company_name, footer_text, doc_prefix, soffice_path} (text).  Audited."""
    u = current_user(request)
    _roles_required(u, "admin")
    with db.tx() as conn:
        docgen.update_settings(conn, u, payload)
    with db.read() as conn:
        return _settings_view(conn)


@app.post("/api/admin/backup")
def admin_backup(request: Request):
    u = current_user(request)
    _roles_required(u, "admin")
    name = workflow.backup_now("manual")
    with db.tx() as conn:
        audit.log(conn, u, "backup.manual", "system", name, None, {})
    return {"name": name}


@app.get("/api/admin/backups")
def admin_backups(request: Request):
    u = current_user(request)
    _roles_required(u, "admin")
    return workflow.list_backups()


@app.post("/api/admin/kb-sync")
def admin_kb_sync(request: Request):
    """E5: add the built-in knowledge-base items that this database does not have yet (matched by title);
    user-created, edited or deactivated items are never touched.  Idempotent."""
    u = current_user(request)
    _roles_required(u, "admin")
    with db.tx() as conn:
        res = workflow.sync_builtin_kb(conn)
        audit.log(conn, u, "kb.sync", "kb", None, None, res)
    return res


# ------------------------------------------------------------------ resource links (knowledge base)
def _link_dict(r):
    d = dict(r)
    d["tags"] = db.jl(d["tags"], [])
    d["category_label"] = kb_links.CATEGORIES.get(d["category"], (d["category"], d["category"]))[0]
    d["category_label_en"] = kb_links.CATEGORIES.get(d["category"], (d["category"], d["category"]))[1]
    return d


@app.get("/api/kb/link-categories")
def kb_link_categories(request: Request):
    current_user(request)
    return [{"key": k, "label": v[0], "label_en": v[1]} for k, v in kb_links.CATEGORIES.items()]


@app.get("/api/kb/links")
def kb_links_list(request: Request, q: str = "", category: str = "", all: int = 0):
    u = current_user(request)
    show_all = bool(all) and bool({"admin", "approver"} & set(u["roles"]))
    with db.read() as conn:
        rows = [_link_dict(r) for r in conn.execute("SELECT * FROM kb_links %s ORDER BY category, id" % ("" if show_all else "WHERE active=1"))]
    out = []
    ql = (q or "").lower()
    for d in rows:
        if category and d["category"] != category:
            continue
        if ql and ql not in (d["title"] + d["title_en"] + d["url"] + d["org"] + d["description"] + d["description_en"] + " ".join(d["tags"])).lower():
            continue
        out.append(d)
    return out


@app.post("/api/kb/links")
def kb_link_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "author", "admin", "approver")
    try:
        d = kb_links.clean(payload)
    except ValueError as e:
        raise WFError(str(e))
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM kb_links WHERE url=?", (d["url"],)).fetchone():
            raise WFError("该网址已在链接库中", 409)
        cur = conn.execute("INSERT INTO kb_links(category,title,title_en,url,org,language,description,description_en,tags,builtin,active,created_by,created_at,updated_at) "
                           "VALUES(?,?,?,?,?,?,?,?,?,0,1,?,?,?)",
                           (d["category"], d["title"], d["title_en"], d["url"], d["org"], d["language"], d["description"], d["description_en"],
                            json.dumps(d["tags"], ensure_ascii=False), u["id"], db.now(), db.now()))
        audit.log(conn, u, "kb.link.create", "kb_links", cur.lastrowid, None, {"title": d["title"], "url": d["url"]})
    return {"id": cur.lastrowid}


@app.put("/api/kb/links/{lid}")
def kb_link_update(lid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    try:
        d = kb_links.clean(payload)
    except ValueError as e:
        raise WFError(str(e))
    with db.tx() as conn:
        old = conn.execute("SELECT * FROM kb_links WHERE id=?", (lid,)).fetchone()
        if not old:
            raise WFError("链接不存在", 404)
        if d["url"] != old["url"] and conn.execute("SELECT 1 FROM kb_links WHERE url=? AND id!=?", (d["url"], lid)).fetchone():
            raise WFError("该网址已在链接库中", 409)
        reset_check = d["url"] != old["url"]
        conn.execute("UPDATE kb_links SET category=?,title=?,title_en=?,url=?,org=?,language=?,description=?,description_en=?,tags=?,updated_at=?"
                     + (",status_code=NULL,checked_at=NULL,check_note=NULL" if reset_check else "") + " WHERE id=?",
                     (d["category"], d["title"], d["title_en"], d["url"], d["org"], d["language"], d["description"], d["description_en"],
                      json.dumps(d["tags"], ensure_ascii=False), db.now(), lid))
        audit.log(conn, u, "kb.link.update", "kb_links", lid, None, {"title": d["title"], "url": {"old": old["url"], "new": d["url"]}})
    return {"ok": True}


@app.delete("/api/kb/links/{lid}")
def kb_link_delete(lid: int, request: Request, restore: int = 0):
    """Deactivate (or restore) a link; links are never physically deleted, so an edit history stays in the audit log."""
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    with db.tx() as conn:
        if not conn.execute("SELECT 1 FROM kb_links WHERE id=?", (lid,)).fetchone():
            raise WFError("链接不存在", 404)
        conn.execute("UPDATE kb_links SET active=?, updated_at=? WHERE id=?", (1 if restore else 0, db.now(), lid))
        audit.log(conn, u, "kb.link.restore" if restore else "kb.link.deactivate", "kb_links", lid, None, {})
    return {"ok": True}


@app.post("/api/admin/kb-links/check")
async def kb_links_check(request: Request, payload: dict = Body(default={})):
    """Health check of the active links (server-side requests to public hosts only).  Needs internet access."""
    u = current_user(request)
    _roles_required(u, "admin")
    ids = payload.get("ids")
    with db.read() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, url FROM kb_links WHERE active=1")]
    if isinstance(ids, list):
        rows = [r for r in rows if r["id"] in ids]
    results = await run_in_threadpool(kb_links.check_links, rows)

    def work():
        with db.tx() as conn:
            for lid, (code, note) in results.items():
                conn.execute("UPDATE kb_links SET status_code=?, checked_at=?, check_note=? WHERE id=?", (code, db.now(), note or "", lid))
            ok = sum(1 for c, _ in results.values() if c and 200 <= c < 400)
            audit.log(conn, u, "kb.links.check", "kb_links", None, None, {"checked": len(results), "ok": ok})
            return {"checked": len(results), "ok": ok, "failed": len(results) - ok}
    return await run_in_threadpool(work)


@app.get("/api/methods/{mid}/export")
def method_export(mid: int, request: Request):
    import urllib.parse
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        data = workflow.export_method(conn, mid)
    return Response(json.dumps(data, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % urllib.parse.quote("%s_export.json" % data["method"]["code"])})


# ------------------------------------------------------------------ own profile, outgoing notification settings
@app.post("/api/me/email")
def me_email(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    em = auth.check_email(payload.get("email", ""))
    with db.tx() as conn:
        conn.execute("UPDATE users SET email=? WHERE id=?", (em, u["id"]))
        audit.log(conn, u, "user.email", "user", u["id"], None, {"email": em})
    return {"email": em}


@app.get("/api/admin/notify-config")
def notify_config(request: Request):
    u = current_user(request)
    _roles_required(u, "admin")
    c = notifier.configured()
    c["public_url"] = config.get("public_url") or ""
    return c


@app.post("/api/admin/notify-test")
async def notify_test(request: Request):
    """Sends a test message to the administrator's e-mail address and/or the webhook (settings in config.json)."""
    u = current_user(request)
    _roles_required(u, "admin")
    c = notifier.configured()
    if not (c["smtp"] or c["webhook"]):
        raise WFError("尚未在 config.json 中配置 smtp_host 或 webhook_url", 400)
    done = []

    def work():
        if c["smtp"]:
            if not u.get("email"):
                raise WFError("请先在“修改邮箱”中设置您自己的邮箱", 400)
            notifier.send_mail(u["email"], "[MethodFlow] test", "MethodFlow notification test.")
            done.append("smtp")
        if c["webhook"]:
            notifier.send_webhook("MethodFlow notification test (%s)" % u["display_name"])
            done.append("webhook")
    try:
        await run_in_threadpool(work)
    except WFError:
        raise
    except Exception as e:
        raise WFError("发送失败：%s: %s" % (type(e).__name__, str(e)[:200]), 502)
    return {"sent": done}


# ------------------------------------------------------------------ audit-trail reviews, inspection pack, comments, search, revisions
@app.get("/api/audit-reviews")
def audit_reviews(request: Request):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    with db.read() as conn:
        return {"items": compliance.list_audit_reviews(conn), "status": compliance.audit_review_status(conn)}


@app.post("/api/audit-reviews")
def audit_reviews_create(request: Request, payload: dict = Body(...)):
    u = current_user(request)
    _roles_required(u, "admin", "approver")
    auth.reauthenticate(u, payload.get("password", ""))               # an electronic signature
    with db.tx() as conn:
        return {"id": compliance.create_audit_review(conn, u, payload)}


@app.get("/api/methods/{mid}/dossier")
def method_dossier(mid: int, request: Request, files: int = 1):
    """Inspection pack (zip): content, experiments, runs, deviations, signatures, audit trail, attachments, documents."""
    import tempfile
    from starlette.background import BackgroundTask
    u = current_user(request)
    fd, path = tempfile.mkstemp(prefix="mf_dossier_", suffix=".zip")
    os.close(fd)
    try:
        with db.tx() as conn:
            workflow.require_view(conn, u, mid)
            code = workflow.get_method(conn, mid)["code"]
            compliance.build_dossier(conn, u, mid, path, bool(files))
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return FileResponse(path, filename="%s_inspection_pack.zip" % code, media_type="application/zip",
                        background=BackgroundTask(lambda: os.path.exists(path) and os.unlink(path)))


@app.get("/api/methods/{mid}/stages/{key}/comments")
def comments_list(mid: int, key: str, request: Request):
    u = current_user(request)
    with db.read() as conn:
        workflow.require_view(conn, u, mid)
        return compliance.list_comments(conn, mid, key)


@app.post("/api/methods/{mid}/stages/{key}/comments")
def comments_add(mid: int, key: str, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        return {"id": compliance.add_comment(conn, u, mid, key, payload.get("section_key", ""), payload.get("body"))}


@app.post("/api/comments/{cid}/resolve")
def comments_resolve(cid: int, request: Request, payload: dict = Body(default={})):
    u = current_user(request)
    with db.tx() as conn:
        compliance.resolve_comment(conn, u, cid, payload.get("resolved", True) is not False)
    return {"ok": True}


@app.get("/api/search")
def global_search(request: Request, q: str = ""):
    u = current_user(request)
    with db.read() as conn:
        return compliance.search(conn, u, q)


@app.post("/api/methods/{mid}/revise")
def method_revise(mid: int, request: Request, payload: dict = Body(...)):
    u = current_user(request)
    with db.tx() as conn:
        workflow.require_view(conn, u, mid)
        return {"id": compliance.revise_method(conn, u, mid, payload.get("note"), payload.get("version"))}


# ------------------------------------------------------------------ background jobs (document generation)
_JOBS = {}
_JOBS_LOCK = threading.Lock()


def _start_job(u, fn):
    jid = uuid.uuid4().hex[:16]
    with _JOBS_LOCK:
        if len(_JOBS) > 200:
            for k in sorted(_JOBS, key=lambda x: _JOBS[x]["t"])[:50]:
                _JOBS.pop(k, None)
        _JOBS[jid] = {"status": "running", "user_id": u["id"], "t": time.time(), "result": None, "error": None, "code": None}

    def run():
        try:
            res = fn()
            with _JOBS_LOCK:
                _JOBS[jid].update(status="done", result=res)
        except WFError as e:
            with _JOBS_LOCK:
                _JOBS[jid].update(status="error", error=str(e), code=e.status)
        except Exception as e:  # pragma: no cover
            log.exception("background job failed")
            with _JOBS_LOCK:
                _JOBS[jid].update(status="error", error="%s: %s" % (type(e).__name__, str(e)[:200]), code=500)
    threading.Thread(target=run, name="mf-job-" + jid, daemon=True).start()
    return jid


@app.get("/api/jobs/{jid}")
def job_status(jid: str, request: Request):
    u = current_user(request)
    with _JOBS_LOCK:
        j = _JOBS.get(jid)
        if not j or j["user_id"] != u["id"]:
            raise WFError("任务不存在", 404)
        return {"status": j["status"], "result": j["result"], "error": j["error"], "code": j["code"], "seconds": round(time.time() - j["t"], 1)}


# ------------------------------------------------------------------ static SPA
@app.get("/")
def index():
    return FileResponse(str(config.STATIC / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/static/{name}")
def static_file(name: str):
    p = (config.STATIC / name).resolve()
    if config.STATIC.resolve() not in p.parents or not p.is_file():
        raise WFError("not found", 404)
    return FileResponse(str(p), headers={"Cache-Control": "no-store"})


def run():
    import sys
    import uvicorn
    try:
        db.init_db()          # fail early with a readable message on an old-model database (the lifespan repeats this: idempotent)
    except db.OldSchemaError as e:
        print("\n无法启动：%s\n" % e, file=sys.stderr, flush=True)
        raise SystemExit(4)
    uvicorn.run(app, host=config.get("host"), port=config.get("port"), log_level="warning")


if __name__ == "__main__":
    run()
