"""Structural and type validation of everything a client can send (M8 / L1).

Every function raises Invalid (a ValueError subclass mapped to HTTP 400 with the message) and returns the
normalised value.  Stored data is therefore always of the shape that workflow.py / docgen.py expect."""
import datetime as dt
import math
import re


class Invalid(ValueError):
    pass


MAX_TEXT = 500_000          # one long free-text section
MAX_CELL = 10_000
MAX_ROWS = 500

_INT_RE = re.compile(r"^[+-]?\d{1,6}(\.0+)?$")
_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def text(v, name, max_len=MAX_CELL, required=False):
    """str (or None -> '') with a length cap."""
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise Invalid("%s 必须是文本" % name)
    if len(v) > max_len:
        raise Invalid("%s 过长（最多 %d 个字符）" % (name, max_len))
    if required and not v.strip():
        raise Invalid("请填写%s" % name)
    return v


def integer(v, name, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, int):
        raise Invalid("%s 必须是整数" % name)
    if lo is not None and v < lo or hi is not None and v > hi:
        raise Invalid("%s 超出范围" % name)
    return v


def boolean(v, name):
    if not isinstance(v, bool):
        raise Invalid("%s 必须是 true/false" % name)
    return v


def date_or_none(v, name):
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise Invalid("%s 必须是日期文本（YYYY-MM-DD）" % name)
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        raise Invalid("%s 不是有效日期（YYYY-MM-DD）" % name)
    if len(v) != 10:
        raise Invalid("%s 不是有效日期（YYYY-MM-DD）" % name)
    return v


def text_list(v, name, max_items=100, max_len=200):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > max_items or not all(isinstance(x, str) and len(x) <= max_len for x in v):
        raise Invalid("%s 必须是文本列表" % name)
    return v


def _scalar(v, name):
    """None / str / finite number; never bool, list or dict."""
    if v is None:
        return ""
    if isinstance(v, bool):
        raise Invalid("%s 的值类型不正确" % name)
    if isinstance(v, str):
        if len(v) > MAX_CELL:
            raise Invalid("%s 的内容过长（最多 %d 个字符）" % (name, MAX_CELL))
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            raise Invalid("%s 的数值无效" % name)
        if isinstance(v, int) and abs(v) > 10 ** 15:
            raise Invalid("%s 的数值过大" % name)
        return v
    raise Invalid("%s 的值类型不正确" % name)


def number_or_blank(v, name, lo=-1e9, hi=1e9):
    """Number, numeric string or blank (kept as sent); anything else is rejected."""
    v = _scalar(v, name)
    if v == "":
        return v
    if isinstance(v, str):
        if not _NUM_RE.match(v.strip()):
            raise Invalid("%s 必须是数字" % name)
        x = float(v)
    else:
        x = float(v)
    if not math.isfinite(x) or x < lo or x > hi:
        raise Invalid("%s 超出范围" % name)
    return v


def sod(v, label):
    """FMEA severity / occurrence / detection: integer 1-10 (or blank while not yet scored)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return ""
    if isinstance(v, bool):
        raise Invalid("%s 必须是 1–10 的整数" % label)
    if isinstance(v, float):
        if not math.isfinite(v) or v != int(v):
            raise Invalid("%s 必须是 1–10 的整数" % label)
        n = int(v)
    elif isinstance(v, int):
        n = v
    elif isinstance(v, str):
        s = v.strip()
        if not _INT_RE.match(s):
            raise Invalid("%s 必须是 1–10 的整数" % label)
        n = int(float(s))
    else:
        raise Invalid("%s 必须是 1–10 的整数" % label)
    if not 1 <= n <= 10:
        raise Invalid("%s 须在 1–10 之间（收到 %s）" % (label, n))
    return n


def _row(r, name):
    if not isinstance(r, dict):
        raise Invalid("%s 的每一行必须是对象" % name)
    if len(r) > 60:
        raise Invalid("%s 的列数过多" % name)
    return r


# ------------------------------------------------------------------ stage sections
def section(sec, val):
    """Validate / normalise one section value against its template definition."""
    t = sec["type"]
    name = "章节“%s”" % sec.get("title", sec["key"])
    if t == "text":
        return text(val, name, MAX_TEXT)
    if t == "fields":
        if val is None:
            val = {}
        if not isinstance(val, dict):
            raise Invalid("%s 必须是对象" % name)
        keys = {f["key"] for f in sec["fields"]}
        out = {}
        for k, v in val.items():
            if k not in keys:
                raise Invalid("%s 含未知字段：%s" % (name, str(k)[:40]))
            out[k] = _scalar(v, "%s/%s" % (name, k))
        return out
    if t == "table":
        if val is None:
            val = []
        if not isinstance(val, list) or len(val) > MAX_ROWS:
            raise Invalid("%s 必须是行列表（最多 %d 行）" % (name, MAX_ROWS))
        out = []
        for r in val:
            r = _row(r, name)
            out.append({str(k)[:100]: _scalar(v, "%s/%s" % (name, k)) for k, v in r.items()})
        return out
    if t == "matrix":
        if val is None:
            val = {}
        if not isinstance(val, dict):
            raise Invalid("%s 必须是对象" % name)
        out = {}
        for k, v in val.items():
            if k == "options":
                if v is None:
                    v = []
                if not isinstance(v, list) or len(v) > 20 or not all(isinstance(x, str) and 0 < len(x) <= 100 for x in v):
                    raise Invalid("%s 的候选项必须是文本列表（最多 20 项）" % name)
                if len(set(v)) != len(v):
                    raise Invalid("%s 的候选项不能重复" % name)
                out[k] = v
            elif k == "selected":
                out[k] = text(v, name + "的选定项", 100)
            elif k == "criteria":
                if v is None:
                    v = []
                if not isinstance(v, list) or len(v) > 50:
                    raise Invalid("%s 的准则必须是列表（最多 50 项）" % name)
                crit = []
                for c in v:
                    c = _row(c, name)
                    cc = {}
                    for ck, cv in c.items():
                        if ck == "name":
                            cc[ck] = text(cv, name + "的准则名称", 200)
                        elif ck == "weight":
                            cc[ck] = number_or_blank(cv, name + "的权重", 0, 1000)
                        elif ck == "scores":
                            if cv is None:
                                cv = {}
                            if not isinstance(cv, dict) or len(cv) > 20:
                                raise Invalid("%s 的得分必须是对象" % name)
                            cc[ck] = {str(sk)[:100]: number_or_blank(sv, name + "的得分", -1000, 1000) for sk, sv in cv.items()}
                        else:
                            cc[str(ck)[:100]] = _scalar(cv, name)
                    crit.append(cc)
                out[k] = crit
            else:
                out[str(k)[:100]] = _scalar(v, name)
        return out
    if t == "fmea":
        if val is None:
            val = []
        if not isinstance(val, list) or len(val) > 200:
            raise Invalid("%s 必须是行列表（最多 200 行）" % name)
        out = []
        for i, r in enumerate(val, 1):
            r = _row(r, name)
            row = {}
            for k, v in r.items():
                if k in ("S", "O", "D"):
                    row[k] = sod(v, "FMEA 第 %d 行的 %s" % (i, k))
                elif k in ("mode", "cause", "effect", "control", "owner"):
                    row[k] = text(v, "FMEA 第 %d 行的 %s" % (i, k), 5000)
                else:
                    row[str(k)[:100]] = _scalar(v, name)
            out.append(row)
        return out
    raise Invalid("未知章节类型")


def checklist_item(v, key):
    if not isinstance(v, dict):
        raise Invalid("检查项 %s 必须是对象" % key)
    st = v.get("status")
    if st not in ("todo", "done", "na"):
        raise Invalid("检查项状态无效")
    return {"status": st, "note": text(v.get("note"), "检查项说明", 5000)}


# ------------------------------------------------------------------ results of an experiment
def results(v):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_ROWS:
        raise Invalid("实验结果必须是行列表（最多 %d 行）" % MAX_ROWS)
    out = []
    for r in v:
        r = _row(r, "实验结果")
        out.append({str(k)[:100]: _scalar(x, "实验结果/%s" % k) for k, x in r.items()})
    return out


def sod_or_none(v):
    """Lenient reader used by the gate checks / documents for data stored before validation existed."""
    try:
        if isinstance(v, bool):
            return None
        n = int(float(v))
        return n if 1 <= n <= 10 and float(v) == n else None
    except (TypeError, ValueError, OverflowError):
        return None


def fnum(v, default=0.0):
    """Tolerant float() for documents: junk becomes `default`."""
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default
