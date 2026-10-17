"""Append-only audit trail with a keyed hash chain.

Chain versions
  hv=1  hash = SHA-256(prev_hash + canonical JSON of the record body)           (legacy, no secret)
  hv=2  hash = HMAC-SHA256(key, prev_hash + canonical JSON of the record body)  (key in data/.audit_key)
  hv=3  as hv=2, but the record body also carries `method_id` (data model v2: a record belongs to a project,
        to a method of that project, or to neither)
Only a database converted by tools/migrate_v1_to_v2.py contains hv=1/2 records (the old single-level model);
they stay in the chain untouched and are verified with the body format that created them (their `project_id`
is the id of the old project, which the migration turned into the method with the same id; the migration
fills the unhashed `method_id` column of those records with that id).  hv may never go back to a smaller value.

Anchor
  After every committed transaction that wrote audit records, the chain head (id, count, hash, HMAC) is
  written to data/audit_head.json and, at every backup, to the backup's side-car file.  verify() requires
  the live chain to still contain the anchored record and to be at least as long as the anchored count, so
  deleting the newest records (which no hash chain can detect on its own) is detected.

The database triggers (db.TRIGGERS), the key and the anchor are independent layers: someone who can only
edit the database file cannot forge a valid chain (no key) nor hide a truncation (anchor); someone who can
also read the key file is outside what a single-machine program can defend against - keep the key
file's ACL tight and copy it, with the backups, to another place.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import threading

from . import config, db

GENESIS = "0" * 64
_key_cache = {}
_head_lock = threading.Lock()


class AuditKeyError(RuntimeError):
    pass


# ------------------------------------------------------------------ key handling
def _restrict(path):
    """Best effort: owner-only access."""
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass
    if os.name == "nt":
        try:
            user = os.environ.get("USERNAME")
            if user:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "%s:F" % user],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        except Exception:
            pass


def _db_has_v2(conn):
    """True when the log already holds keyed (HMAC) records, i.e. hv >= 2."""
    try:
        return conn.execute("SELECT 1 FROM audit_log WHERE hv>=2 LIMIT 1").fetchone() is not None
    except sqlite3.OperationalError:
        return False


def load_key(create=False, conn=None):
    """Return the HMAC key (bytes) or None.  With create=True a missing key is generated - unless the
    database already contains hv=2 records, in which case a new key could never verify them."""
    path = config.AUDIT_KEY
    sp = str(path)
    if not path.exists():
        _key_cache.pop(sp, None)
        if not create:
            return None
        if conn is not None and _db_has_v2(conn):
            raise AuditKeyError("审计密钥文件缺失（%s），但数据库已含密钥链记录。请从备份恢复 .audit_key；"
                                "没有它无法验证或继续写入审计链。" % path)
        path.parent.mkdir(parents=True, exist_ok=True)
        key_hex = secrets.token_hex(32)
        try:
            with open(sp, "x", encoding="ascii") as f:
                f.write(key_hex)
        except FileExistsError:
            pass
        else:
            _restrict(path)
    k = _key_cache.get(sp)
    if k:
        return k
    try:
        txt = path.read_text(encoding="ascii").strip()
        k = bytes.fromhex(txt)
    except Exception:
        raise AuditKeyError("审计密钥文件损坏：%s" % path)
    if len(k) < 16:
        raise AuditKeyError("审计密钥文件损坏：%s" % path)
    _key_cache[sp] = k
    return k


def _chain_hash(hv, key, prev, body_json):
    data = (prev + body_json).encode("utf-8")
    if hv == 1:
        return hashlib.sha256(data).hexdigest()
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def log(conn, user, action, entity_type=None, entity_id=None, method_id=None, details=None, reason=None, project_id=None):
    """Write one audit record. Must be called inside db.tx() so chain order matches commit order.
    `method_id` is the method the record belongs to (None for project-level / system events); `project_id` is
    derived from the method when not given (explicit for project-level events)."""
    key = load_key(create=True, conn=conn)
    last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["hash"] if last else GENESIS
    uid = user["id"] if isinstance(user, dict) and user else None
    uname = user["username"] if isinstance(user, dict) and user else (user if isinstance(user, str) else "system")
    if project_id is None and method_id is not None:
        m = conn.execute("SELECT project_id FROM methods WHERE id=?", (method_id,)).fetchone()
        project_id = m["project_id"] if m else None
    ts = db.now()
    body = {
        "ts": ts, "user_id": uid, "username": uname, "action": action,
        "entity_type": entity_type, "entity_id": None if entity_id is None else str(entity_id),
        "project_id": project_id, "method_id": method_id, "details": details or {}, "reason": reason,
    }
    h = _chain_hash(3, key, prev, db.canon(body))
    conn.execute(
        "INSERT INTO audit_log(ts,user_id,username,action,entity_type,entity_id,project_id,method_id,details,reason,prev_hash,hash,hv)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,3)",
        (ts, uid, uname, action, body["entity_type"], body["entity_id"], project_id, method_id,
         db.canon(body["details"]), reason, prev, h),
    )
    conn.audit_dirty = True
    return h


# ------------------------------------------------------------------ anchor
def _head_mac(key, head):
    return hmac.new(key, ("%d|%d|%s" % (head["id"], head["count"], head["hash"])).encode("ascii"), hashlib.sha256).hexdigest()


def compute_head(conn):
    """Signed head of the chain in `conn`, or None if the log is empty / no key."""
    key = load_key(create=False)
    r = conn.execute("SELECT id, hash, (SELECT COUNT(*) FROM audit_log) AS n FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if r is None or key is None:
        return None
    head = {"id": r["id"], "count": r["n"], "hash": r["hash"], "ts": db.now()}
    head["mac"] = _head_mac(key, head)
    return head


def head_valid(head):
    key = load_key(create=False)
    try:
        return bool(key) and hmac.compare_digest(head.get("mac", ""), _head_mac(key, head))
    except Exception:
        return False


def read_head(path=None):
    """Parsed anchor file, None if absent, {'_invalid': True} if unreadable."""
    p = path or config.AUDIT_HEAD
    try:
        if not os.path.exists(str(p)):
            return None
        with open(str(p), encoding="utf-8") as f:
            h = json.load(f)
        if not isinstance(h, dict) or not all(k in h for k in ("id", "count", "hash", "mac")):
            return {"_invalid": True}
        return h
    except Exception:
        return {"_invalid": True}


def _write_json_atomic(path, obj):
    tmp = str(path) + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f)
    os.replace(tmp, str(path))


def write_head(force=False):
    """Advance data/audit_head.json to the current chain head.  Unless force=True an existing valid anchor
    is only advanced when the chain still contains it (so a truncated chain never overwrites the evidence)."""
    with _head_lock:
        c = sqlite3.connect(str(config.DB_PATH), timeout=15)
        c.row_factory = sqlite3.Row
        try:
            head = compute_head(c)
            if head is None:
                return None
            if not force:
                cur = read_head()
                if cur is None:
                    # An anchor file that vanished after it was once created is NOT silently recreated from a
                    # possibly truncated log: verify() reports it as missing until tools/audit_anchor.py --reset.
                    m = c.execute("SELECT value FROM settings WHERE key='audit_anchor'").fetchone()
                    if m is not None:
                        return None
                else:
                    if cur.get("_invalid") or not head_valid(cur):
                        return cur               # leave tampered anchors in place; verify() reports them
                    r = c.execute("SELECT hash FROM audit_log WHERE id=?", (cur["id"],)).fetchone()
                    if r is None or r["hash"] != cur["hash"] or head["count"] < cur["count"]:
                        return cur
                    if cur["id"] >= head["id"]:
                        return cur
            _write_json_atomic(config.AUDIT_HEAD, head)
            c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('audit_anchor', ?)", (head["ts"],))
            c.commit()
            return head
        finally:
            c.close()


# ------------------------------------------------------------------ verification
def verify_chain(conn, anchor=None, live_anchor=False):
    """Recompute every hash from genesis.  `anchor` (a head dict) or live_anchor=True additionally checks
    that the chain still contains the anchored record and is not shorter than the anchored count.
    Returns {ok, chain_ok, count, first_bad_id, key_missing, anchor_ok, anchor_status}."""
    key = load_key(create=False)
    prev = GENESIS
    count = 0
    last_hv = 1
    found = {}
    anchor_id = None
    if live_anchor:
        anchor = read_head()
        anchor_missing = anchor is None
    else:
        anchor_missing = False
    if isinstance(anchor, dict) and not anchor.get("_invalid"):
        try:
            anchor_id = int(anchor["id"])
        except Exception:
            anchor_id = None
    res = {"ok": True, "chain_ok": True, "count": 0, "first_bad_id": None, "key_missing": False,
           "anchor_ok": None, "anchor_status": "not_checked"}
    cols = None
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        if cols is None:
            cols = r.keys()
        hv = r["hv"] if "hv" in cols else 1
        body = {
            "ts": r["ts"], "user_id": r["user_id"], "username": r["username"], "action": r["action"],
            "entity_type": r["entity_type"], "entity_id": r["entity_id"], "project_id": r["project_id"],
            "details": db.jl(r["details"], {}), "reason": r["reason"],
        }
        if hv == 3:
            body["method_id"] = r["method_id"]
        if hv not in (1, 2, 3) or hv < last_hv:
            res.update(ok=False, chain_ok=False, first_bad_id=r["id"])
            return res
        if hv >= 2 and key is None:
            res.update(ok=False, chain_ok=False, first_bad_id=r["id"], key_missing=True)
            return res
        expect = _chain_hash(hv, key, prev, db.canon(body))
        if r["prev_hash"] != prev or not hmac.compare_digest(r["hash"], expect):
            res.update(ok=False, chain_ok=False, first_bad_id=r["id"])
            return res
        prev = r["hash"]
        last_hv = hv
        count += 1
        if anchor_id is not None and r["id"] == anchor_id:
            found["hash"] = r["hash"]
    res["count"] = count
    # ---- anchor
    if live_anchor or anchor is not None:
        if anchor_missing:
            st = "missing" if count > 0 else "ok"
        elif anchor is None or anchor.get("_invalid") or not head_valid(anchor):
            st = "tampered"
        elif count < int(anchor["count"]):
            st = "shorter"
        elif found.get("hash") != anchor["hash"]:
            st = "mismatch"
        else:
            st = "ok"
        res["anchor_status"] = st
        res["anchor_ok"] = (st == "ok")
        if st != "ok":
            res["ok"] = False
    return res


def triggers_present(conn):
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    return all(n in have for n in db.TRIGGER_NAMES)


def signatures(conn):
    """Check every approved/completed stage's signatures against the live data.  Returns (ok, bad_list)."""
    from . import workflow
    bad = []
    for s in conn.execute("SELECT s.*, m.code AS mcode, m.name AS mname, m.project_id AS pid, p.code AS pcode "
                          "FROM stages s JOIN methods m ON m.id=s.method_id JOIN projects p ON p.id=m.project_id "
                          "WHERE s.status IN ('approved','completed') ORDER BY s.method_id, s.ord"):
        st = workflow._loads(s)
        ok, problems = workflow.stage_signature_status(conn, s["method_id"], st)
        if not ok:
            bad.append({"method_id": s["method_id"], "method": s["mcode"], "method_name": s["mname"],
                        "project_id": s["pid"], "project": s["pcode"], "stage": s["key"], "stage_title": st["title"],
                        "revision": s["revision"], "problems": problems})
    return (not bad), bad


def verify(conn):
    """Full integrity report used by /api/audit/verify: chain + anchor + triggers + signatures."""
    res = verify_chain(conn, live_anchor=True)
    res["triggers_ok"] = triggers_present(conn)
    sig_ok, bad = signatures(conn)
    res["signatures_ok"] = sig_ok
    res["bad_signatures"] = bad
    res["ok"] = bool(res["chain_ok"] and res["anchor_ok"] is not False and res["triggers_ok"] and sig_ok)
    return res
