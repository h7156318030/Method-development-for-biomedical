"""Outgoing notifications (optional): e-mail through SMTP and/or a webhook (generic JSON, WeCom, Feishu, DingTalk).

In-app notifications are always created by workflow.notify(); this module forwards them when config.json has
`smtp_host` and/or `webhook_url`.  Delivery runs in one background thread, two seconds after the notification was
created and only if the row still exists (so a rolled-back transaction never sends anything).  A failure is logged and
never affects the workflow.  Secrets (smtp_password) live in config.json only; they are never stored in the database."""
import json
import logging
import queue
import smtplib
import threading
import time
import urllib.request
from email.message import EmailMessage

from . import config, db

log = logging.getLogger("methodflow.notifier")
_q = queue.Queue()
_thread = None
_lock = threading.Lock()


def configured():
    return {"smtp": bool(config.get("smtp_host")), "webhook": bool(config.get("webhook_url")), "webhook_kind": config.get("webhook_kind") or "generic"}


def enqueue(notification_id):
    global _thread
    c = configured()
    if not (c["smtp"] or c["webhook"]):
        return
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, name="mf-notifier", daemon=True)
            _thread.start()
    _q.put(notification_id)


def _loop():
    while True:
        nid = _q.get()
        time.sleep(2)
        try:
            deliver(nid)
        except Exception as e:  # pragma: no cover - network errors
            log.warning("notification %s not delivered: %s", nid, e)


def link_for(n):
    base = (config.get("public_url") or "").rstrip("/")
    if not base or not n.get("method_id"):
        return ""
    return "%s/#/m/%d%s" % (base, n["method_id"], ("/stage/" + n["stage_key"]) if n.get("stage_key") else "")


def deliver(nid):
    with db.read() as conn:
        n = conn.execute("SELECT n.*, u.email, u.display_name FROM notifications n JOIN users u ON u.id=n.user_id WHERE n.id=?", (nid,)).fetchone()
    if not n:
        return False
    n = dict(n)
    text = n["title"] + ("\n" + n["body"] if n["body"] else "")
    link = link_for(n)
    if link:
        text += "\n" + link
    sent = False
    if config.get("smtp_host") and n["email"]:
        send_mail(n["email"], "[MethodFlow] " + n["title"], text)
        sent = True
    if config.get("webhook_url"):
        send_webhook("%s（%s）\n%s" % (n["title"], n["display_name"], n["body"] + (("\n" + link) if link else "")))
        sent = True
    return sent


def send_mail(to, subject, text):
    host, port = config.get("smtp_host"), int(config.get("smtp_port") or 587)
    msg = EmailMessage()
    msg["From"] = config.get("smtp_from") or config.get("smtp_user") or "methodflow@localhost"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        s = smtplib.SMTP(host, port, timeout=15)
        if config.get("smtp_tls", True):
            s.starttls()
    try:
        if config.get("smtp_user"):
            s.login(config.get("smtp_user"), config.get("smtp_password") or "")
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:
            pass


def webhook_payload(text):
    kind = config.get("webhook_kind") or "generic"
    if kind == "feishu":
        return {"msg_type": "text", "content": {"text": text}}
    if kind in ("wecom", "dingtalk"):
        return {"msgtype": "text", "text": {"content": text}}
    return {"title": text.split("\n", 1)[0], "text": text}


def send_webhook(text):
    url = config.get("webhook_url")
    if not url.startswith(("http://", "https://")):
        raise ValueError("webhook_url must start with http:// or https://")
    req = urllib.request.Request(url, data=json.dumps(webhook_payload(text), ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read(256)
