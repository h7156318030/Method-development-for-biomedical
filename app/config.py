"""MethodFlow configuration. Values may be overridden by config.json in the project root
or by environment variables (METHODFLOW_DATA, METHODFLOW_HOST, METHODFLOW_PORT)."""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
STATIC = APP / "static"

_defaults = {
    "host": "127.0.0.1",
    "port": 8780,
    "session_hours": 12,          # absolute session lifetime
    "idle_minutes": 60,           # idle timeout
    "max_failed_logins": 5,
    "lock_minutes": 15,
    "login_rate_max": 10,         # failed logins per (username, source IP) per minute before HTTP 429
    "backup_keep": 30,            # kept per label group: manual / daily / other
    "backup_keep_startup": 10,    # startup backups are kept separately
    "audit_review_days": 90,      # the audit trail should be reviewed at least this often (0 = no reminder)
    "max_dossier_mb": 2000,       # size cap of the inspection pack (zip)
    "require_change_reason": False,   # True: changes to a step that was already returned / reopened need a written reason
    "password_max_days": 0,       # password expiry in days (0 = never expires)
    "password_history": 5,        # a new password must differ from the last N passwords (0 = off)
    "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": "", "smtp_from": "", "smtp_tls": True,   # e-mail notifications
    "webhook_url": "", "webhook_kind": "generic",   # generic | wecom | feishu | dingtalk
    "public_url": "",             # e.g. http://lab-pc:8780  (links inside notifications)
    "strict_completeness": False, # False: only core content blocks submission, other required items warn (progressive completion)
    "enforce_stage_order": True,  # standard flow: a stage opens for editing only after its prerequisite stages passed
    "rpn_threshold": 120,         # FMEA: RPN at/above this needs mitigation before a gate
    "severity_threshold": 8,      # FMEA: severity at/above this needs a specific control
    "min_password_length": 10,
    "max_upload_mb": 200,
    "max_json_mb": 20,            # request body limit for every non-upload API call
    "docs_per_minute": 6,         # generated documents per METHOD per minute
    "setup_token": "",            # if set, POST /api/setup must carry the same token
    "allowed_hosts": None,        # list of accepted Host header names; None = automatic (see main._host_ok)
    "cookie_secure": None,        # None = automatic (Secure when the listen host is not loopback)
    "soffice_path": "",           # LibreOffice executable for PDF output (admin setting overrides; "" = PATH / default install dirs)
    "pdf_enabled": True,          # False = never run LibreOffice, Word output only
    "pdf_timeout_sec": 120,       # one LibreOffice conversion (the first start with a fresh profile can take ~20 s)
}

_cfg = dict(_defaults)
_cfg_file = ROOT / "config.json"
if _cfg_file.exists():
    try:
        _cfg.update(json.loads(_cfg_file.read_text(encoding="utf-8")))
    except Exception as e:  # pragma: no cover
        print("WARNING: config.json unreadable:", e)

if os.environ.get("METHODFLOW_HOST"):
    _cfg["host"] = os.environ["METHODFLOW_HOST"]
if os.environ.get("METHODFLOW_PORT"):
    _cfg["port"] = int(os.environ["METHODFLOW_PORT"])

DATA = pathlib.Path(os.environ.get("METHODFLOW_DATA", ROOT / "data"))
DB_PATH = DATA / "methodflow.db"
UPLOADS = DATA / "uploads"
BACKUPS = DATA / "backups"
DOCS = DATA / "documents"
AUDIT_KEY = DATA / ".audit_key"
AUDIT_HEAD = DATA / "audit_head.json"


def set_data(path):
    """Point every data location at another folder (used by tests that need an isolated database)."""
    global DATA, DB_PATH, UPLOADS, BACKUPS, DOCS, AUDIT_KEY, AUDIT_HEAD
    DATA = pathlib.Path(path)
    DB_PATH = DATA / "methodflow.db"
    UPLOADS = DATA / "uploads"
    BACKUPS = DATA / "backups"
    DOCS = DATA / "documents"
    AUDIT_KEY = DATA / ".audit_key"
    AUDIT_HEAD = DATA / "audit_head.json"


def get(key):
    return _cfg[key]


def override(key, value):
    """Runtime override (tests)."""
    _cfg[key] = value


def ensure_dirs():
    for p in (DATA, UPLOADS, BACKUPS, DOCS):
        p.mkdir(parents=True, exist_ok=True)
