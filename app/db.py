"""SQLite access, schema, migrations and small helpers.

Data model v2 (project / method split) = SCHEMA_VERSION 3.  Version numbers 1 and 2 belong to the earlier
"project = method" model; such a database is refused by init_db() with a clear message (see OldSchemaError)
and can be converted with tools/migrate_v1_to_v2.py."""
import contextlib
import datetime as dt
import hashlib
import json
import logging
import sqlite3

from . import config

log = logging.getLogger("methodflow.db")

SCHEMA_VERSION = 5          # v3 = "data model v2" (project/method split); v4 adds notifications + kb_links; v5 adds records (see _migrate_4_to_5)
MIN_SUPPORTED_VERSION = 3   # user_version 1/2 = the old single-level project model (needs tools/migrate_v1_to_v2.py)


class OldSchemaError(RuntimeError):
    """The database was written by a release that did not separate projects from methods."""


DDL = """
CREATE TABLE users(
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  roles TEXT NOT NULL DEFAULT '[]',
  pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  failed_count INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  must_change INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  pw_changed_at TEXT
);
CREATE TABLE sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE projects(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  product TEXT, indication TEXT, phase TEXT, description TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  planned_start TEXT, planned_end TEXT,
  owner_id INTEGER REFERENCES users(id),
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE TABLE project_members(
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  role TEXT NOT NULL,
  PRIMARY KEY(project_id, user_id, role)
);
CREATE TABLE methods(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  technique TEXT NOT NULL,
  template_key TEXT NOT NULL,
  template_version TEXT,
  analyte TEXT, matrix TEXT, intended_use TEXT, phase TEXT,
  method_version TEXT NOT NULL DEFAULT 'V0.1',
  lifecycle TEXT NOT NULL DEFAULT 'development',
  status TEXT NOT NULL DEFAULT 'active',
  planned_start TEXT, planned_end TEXT,
  owner_id INTEGER REFERENCES users(id),
  created_by INTEGER, created_at TEXT, updated_at TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  revision_of INTEGER,
  revision_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE method_members(
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  role TEXT NOT NULL,
  PRIMARY KEY(method_id, user_id, role)
);
CREATE TABLE stages(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  ord INTEGER NOT NULL,
  def TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started',
  revision INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1,
  stale INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  editors TEXT NOT NULL DEFAULT '[]',
  contributors TEXT NOT NULL DEFAULT '[]',
  planned_start TEXT, planned_end TEXT, actual_start TEXT, actual_end TEXT,
  submitted_at TEXT, updated_at TEXT,
  UNIQUE(method_id, key)
);
CREATE TABLE stage_revisions(
  id INTEGER PRIMARY KEY,
  stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  data TEXT NOT NULL,
  data_hash TEXT NOT NULL,
  created_by INTEGER, created_at TEXT, reason TEXT,
  hv INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE reviews(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL,
  stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  role TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  decision TEXT NOT NULL,
  comment TEXT,
  signed_at TEXT NOT NULL,
  data_hash TEXT NOT NULL,
  meaning TEXT
);
CREATE TABLE experiments(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  stage_key TEXT,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  objective TEXT, design TEXT, acceptance TEXT,
  planned_start TEXT, planned_end TEXT, actual_start TEXT, actual_end TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  owner_id INTEGER,
  results TEXT NOT NULL DEFAULT '[]',
  conclusion TEXT, deviations TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT, updated_at TEXT,
  added_after_plan INTEGER NOT NULL DEFAULT 0,
  UNIQUE(method_id, code)
);
CREATE TABLE attachments(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  stage_key TEXT, experiment_id INTEGER,
  filename TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL,
  description TEXT,
  uploaded_by INTEGER, uploaded_at TEXT,
  deleted INTEGER NOT NULL DEFAULT 0, deleted_by INTEGER, deleted_at TEXT, delete_reason TEXT
);
CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_id INTEGER, username TEXT,
  action TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT,
  project_id INTEGER,
  method_id INTEGER,
  details TEXT NOT NULL DEFAULT '{}',
  reason TEXT,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  hv INTEGER NOT NULL DEFAULT 3
);
CREATE TABLE kb_items(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  techniques TEXT NOT NULL DEFAULT '[]',
  stages TEXT NOT NULL DEFAULT '[]',
  source TEXT,
  origin_method_id INTEGER,
  builtin INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE TABLE generated_docs(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  format TEXT NOT NULL DEFAULT 'docx',
  filename TEXT NOT NULL, path TEXT NOT NULL,
  version_label TEXT, status_label TEXT,
  data_hash TEXT, created_by INTEGER, created_at TEXT, summary TEXT
);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE notifications(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  method_id INTEGER, stage_key TEXT,
  title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
  read INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_notif_user ON notifications(user_id, read, id);
CREATE TABLE materials(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'reagent',
  supplier TEXT NOT NULL DEFAULT '', catalog_no TEXT NOT NULL DEFAULT '', lot TEXT NOT NULL DEFAULT '',
  grade TEXT NOT NULL DEFAULT '', concentration TEXT NOT NULL DEFAULT '', storage TEXT NOT NULL DEFAULT '',
  received_at TEXT, expiry_at TEXT,
  critical INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  notes TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE TABLE equipment(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '', serial_no TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
  last_calibration TEXT, calibration_due TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  notes TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE TABLE runs(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  experiment_id INTEGER REFERENCES experiments(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  run_date TEXT, analyst_id INTEGER,
  equipment TEXT NOT NULL DEFAULT '[]', materials TEXT NOT NULL DEFAULT '[]',
  outcome TEXT NOT NULL DEFAULT 'valid',
  summary TEXT NOT NULL DEFAULT '',
  verified_by INTEGER, verified_at TEXT,
  version INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE INDEX idx_runs_method ON runs(method_id);
CREATE INDEX idx_runs_exp ON runs(experiment_id);
CREATE TABLE deviations(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  classification TEXT NOT NULL DEFAULT 'minor',
  stage_key TEXT, experiment_id INTEGER,
  impact TEXT NOT NULL DEFAULT '', root_cause TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  opened_by INTEGER, opened_at TEXT,
  closed_by INTEGER, closed_at TEXT, close_note TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_dev_method ON deviations(method_id);
CREATE TABLE audit_reviews(
  id INTEGER PRIMARY KEY,
  reviewer_id INTEGER NOT NULL,
  scope TEXT NOT NULL DEFAULT 'all',
  method_id INTEGER,
  period_from TEXT, period_to TEXT,
  entries_checked INTEGER NOT NULL DEFAULT 0,
  chain_ok INTEGER NOT NULL DEFAULT 1,
  conclusion TEXT NOT NULL DEFAULT 'no_issue',
  findings TEXT NOT NULL DEFAULT '',
  signed_at TEXT NOT NULL
);
CREATE TABLE comments(
  id INTEGER PRIMARY KEY,
  method_id INTEGER NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
  stage_key TEXT NOT NULL,
  section_key TEXT NOT NULL DEFAULT '',
  user_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0, resolved_by INTEGER, resolved_at TEXT
);
CREATE INDEX idx_comments_method ON comments(method_id, stage_key);
CREATE TABLE pw_history(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pw_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_pwh_user ON pw_history(user_id);
CREATE TABLE kb_links(
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,
  title TEXT NOT NULL, title_en TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL UNIQUE,
  org TEXT NOT NULL DEFAULT '', language TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '', description_en TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  builtin INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  status_code INTEGER, checked_at TEXT, check_note TEXT,
  created_by INTEGER, created_at TEXT, updated_at TEXT
);
CREATE INDEX idx_methods_project ON methods(project_id);
CREATE INDEX idx_pmembers_user ON project_members(user_id);
CREATE INDEX idx_mmembers_user ON method_members(user_id);
CREATE INDEX idx_stages_method ON stages(method_id);
CREATE INDEX idx_exp_method ON experiments(method_id);
CREATE INDEX idx_att_method ON attachments(method_id);
CREATE INDEX idx_audit_project ON audit_log(project_id);
CREATE INDEX idx_audit_method ON audit_log(method_id);
CREATE INDEX idx_reviews_stage ON reviews(stage_id);
"""

# Tamper-resistance triggers (M1).  They stop ordinary SQL (including a buggy program or a casual
# editor) from changing or deleting the evidence tables; a determined person with file access can still
# DROP them, which is why the audit chain is HMAC-keyed and anchored outside the database.
# audit_log / stage_revisions / reviews have no legitimate UPDATE or DELETE anywhere in the program.
TRIGGER_NAMES = ["trg_audit_no_update", "trg_audit_no_delete", "trg_rev_no_update", "trg_rev_no_delete",
                 "trg_reviews_no_update", "trg_reviews_no_delete"]
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_rev_no_update BEFORE UPDATE ON stage_revisions
BEGIN SELECT RAISE(ABORT, 'stage_revisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_rev_no_delete BEFORE DELETE ON stage_revisions
BEGIN SELECT RAISE(ABORT, 'stage_revisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_reviews_no_update BEFORE UPDATE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_reviews_no_delete BEFORE DELETE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews is append-only'); END;
"""


def now():
    """UTC ISO-8601 with seconds, e.g. 2026-10-14T08:15:30Z"""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canon(obj):
    """Canonical JSON used for hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(text):
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def jl(s, default=None):
    if s is None or s == "":
        return default
    return json.loads(s)


class _Conn(sqlite3.Connection):
    """sqlite3 connection that remembers whether this transaction wrote audit records."""
    audit_dirty = False


def connect():
    config.ensure_dirs()
    conn = sqlite3.connect(str(config.DB_PATH), timeout=15, isolation_level=None, factory=_Conn)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


@contextlib.contextmanager
def tx():
    """One write transaction (BEGIN IMMEDIATE) -> commit / rollback.  After a successful commit that wrote
    audit records, the signed audit-chain head is written to data/audit_head.json (outside the database)."""
    conn = connect()
    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
        committed = True
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        dirty = conn.audit_dirty
        conn.close()
    if committed and dirty:
        try:
            from . import audit
            audit.write_head()
        except Exception as e:  # pragma: no cover - the anchor is best effort, verify() reports a stale one
            log.warning("could not write audit head: %s", e)


@contextlib.contextmanager
def read():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------ schema management (L6)
def split_sql(script):
    """Split a script into complete statements (triggers contain ';' inside BEGIN..END)."""
    out, buf = [], ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


# key = schema version migrated FROM.  The old single-level model (versions 1 and 2) cannot be upgraded by a
# plain ALTER sequence; tools/migrate_v1_to_v2.py rebuilds the database.  Future in-place upgrades go here.
def _migrate_3_to_4(conn):
    """v4: in-app notifications and the editable resource-link library (kb_links)."""
    for stmt in split_sql(DDL):
        s = stmt.strip()
        if s.startswith("CREATE TABLE notifications") or s.startswith("CREATE TABLE kb_links") or s.startswith("CREATE INDEX idx_notif_user"):
            conn.execute(s.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1).replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1))


def _columns(conn, table):
    return {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}


def _migrate_4_to_5(conn):
    """v5: run records, material / equipment registry, deviations, audit-trail reviews, section comments,
    method revisions (methods.revision_of), user e-mail and password history.  Idempotent."""
    if "email" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if "pw_changed_at" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN pw_changed_at TEXT")
    if "revision_of" not in _columns(conn, "methods"):
        conn.execute("ALTER TABLE methods ADD COLUMN revision_of INTEGER")
    if "revision_note" not in _columns(conn, "methods"):
        conn.execute("ALTER TABLE methods ADD COLUMN revision_note TEXT NOT NULL DEFAULT ''")
    names = ("materials", "equipment", "runs", "deviations", "audit_reviews", "comments", "pw_history")
    for stmt in split_sql(DDL):
        t = stmt.strip()
        if any(t.startswith("CREATE TABLE %s(" % n) for n in names):
            conn.execute(t.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
        elif t.startswith("CREATE INDEX") and any((" ON %s(" % n) in t for n in names):
            conn.execute(t.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1))


MIGRATIONS = {3: _migrate_3_to_4, 4: _migrate_4_to_5}


def old_schema_message(ver):
    return ("数据库 %s 是旧版结构（user_version=%d：项目与方法尚未分离），本程序（结构版本 %d）不能直接使用。\n"
            "请先停止服务并备份整个 data 文件夹，然后二选一：\n"
            "  1) 开发期数据可丢弃：删除 data 文件夹后重新启动（将重新初始化管理员）；\n"
            "  2) 保留数据：运行  python tools\\migrate_v1_to_v2.py  把每个旧项目转换为一个方法（并自动建同名项目）。"
            % (config.DB_PATH, ver, SCHEMA_VERSION))


def detect_version(conn):
    """(user_version, has_user_tables)."""
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone() is not None
    return ver, has_tables


def init_db():
    """Create or upgrade the database inside ONE transaction (all or nothing).  A database of the old
    single-level (project = method) model is refused before anything is touched."""
    from . import audit
    config.ensure_dirs()
    conn = connect()
    migrated = False
    try:
        ver, has_tables = detect_version(conn)
        if ver > SCHEMA_VERSION:
            raise RuntimeError("Database is newer than this program (user_version=%d)" % ver)
        if 0 < ver < MIN_SUPPORTED_VERSION or (ver == 0 and has_tables):
            raise OldSchemaError(old_schema_message(ver))
        if MIN_SUPPORTED_VERSION <= ver < SCHEMA_VERSION:   # in-place upgrade: keep a copy of the database as it was before
            try:
                import shutil, datetime as _dt
                config.ensure_dirs()
                dst = config.BACKUPS / ("premigrate_v%d_%s.db" % (ver, _dt.datetime.now().strftime("%Y%m%d_%H%M%S")))
                src = sqlite3.connect(str(config.DB_PATH))
                try:
                    out = sqlite3.connect(str(dst))
                    try:
                        src.backup(out)
                    finally:
                        out.close()
                finally:
                    src.close()
            except Exception as e:        # a failed courtesy copy must not block the start
                log.warning("pre-migration backup failed: %s", e)
        audit.load_key(create=True, conn=conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if ver == 0:
                for stmt in split_sql(DDL):
                    conn.execute(stmt)
                migrated = True
            else:
                v = ver
                while v < SCHEMA_VERSION:
                    MIGRATIONS[v](conn)
                    v += 1
                    migrated = True
            for stmt in split_sql(TRIGGERS):
                conn.execute(stmt)
            if ver < SCHEMA_VERSION:
                conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
    finally:
        conn.close()
    if migrated:
        audit.write_head(force=True)      # first anchor of a new / upgraded database


def row(r):
    return dict(r) if r is not None else None


def rows(rs):
    return [dict(r) for r in rs]
