"""Statistics for analytical method development (pure Python, no third-party dependency).

Contents
  - distributions: normal / Student t / chi-square quantiles (self-implemented, cross-checked in tests/test_stats.py)
  - parse_criterion / evaluate: acceptance criteria written like "≥5", "≤ 2%", "90–110%", "±15%" are parsed and a measured
    value is judged against them
  - calculators used by the "statistics calculator" of the experiment page:
      summary, accuracy, precision (repeatability + intermediate precision by one-way ANOVA variance components),
      linearity (ordinary least squares), lod_loq, tost (paired equivalence), count_cv (event-count CV)
Every calculator returns {"inputs": ..., "rows": [{"metric", "value", "note"}], "details": {...}}; `rows` can be copied
into the results table of an experiment.  The numerical results are conventional textbook formulas; they support, but do
not replace, the statistical plan of the method (see docs).  Verification: tests/test_stats.py.
"""
import math
import re

# ------------------------------------------------------------------ special functions


def _betacf(a, b, x, itmax=300, eps=3e-14):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def gammainc_lower(a, x):
    """Regularised lower incomplete gamma P(a, x)."""
    if x <= 0:
        return 0.0
    if x < a + 1.0:
        ap, s, term = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            s += term
            if abs(term) < abs(s) * 1e-15:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b = x + 1.0 - a
    c, d = 1e300, 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = d if abs(d) > 1e-300 else 1e-300
        c = b + an / c
        c = c if abs(c) > 1e-300 else 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return 1.0 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bisect(f, lo, hi, target, n=200):
    for _ in range(n):
        mid = (lo + hi) / 2.0
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def norm_ppf(p):
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    return _bisect(norm_cdf, -12.0, 12.0, p)


def t_cdf(t, df):
    x = df / (df + t * t)
    ib = betainc(df / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t > 0 else 0.5 * ib


def t_ppf(p, df):
    """Quantile of Student's t distribution (df > 0)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if df <= 0:
        raise ValueError("df must be positive")
    return _bisect(lambda t: t_cdf(t, df), -2000.0, 2000.0, p)


def chi2_cdf(x, df):
    return gammainc_lower(df / 2.0, x / 2.0)


def chi2_ppf(p, df):
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    return _bisect(lambda x: chi2_cdf(x, df), 0.0, max(10.0, df * 20.0), p)


# ------------------------------------------------------------------ descriptive helpers


def _nums(values, name="values", minimum=1):
    out = []
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("%s: not a number: %r" % (name, v))
        if math.isnan(f) or math.isinf(f):
            raise ValueError("%s: not a finite number" % name)
        out.append(f)
    if len(out) < minimum:
        raise ValueError("%s: at least %d value(s) needed" % (name, minimum))
    return out


def mean(x):
    return sum(x) / len(x)


def sd(x):
    n = len(x)
    if n < 2:
        return float("nan")
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))


def _r(v, nd=4):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if v == 0:
        return 0.0
    digits = nd - int(math.floor(math.log10(abs(v)))) - 1
    return round(v, max(digits, 0)) if abs(v) < 1e6 else round(v, 0)


def _row(metric, value, note=""):
    return {"metric": metric, "value": _r(value) if isinstance(value, float) else value, "note": note}


# ------------------------------------------------------------------ criteria

_NUM = r"[-+]?\d+(?:\.\d+)?"
_NORMALISE = [("≥", ">="), ("≦", "<="), ("≤", "<="), ("＞", ">"), ("＜", "<"), ("，", ","), ("～", "~"), ("–", "-"), ("—", "-"), ("－", "-"),
              ("％", "%"), ("＝", "="), ("到", "-"), ("至", "-")]


def _clean(text):
    t = str(text or "")
    for a, b in _NORMALISE:
        t = t.replace(a, b)
    return t.replace(" ", "").replace("　", "")


def parse_criterion(text):
    """{'kind': 'ge'|'gt'|'le'|'lt'|'between'|'abs_le'|'eq', 'lo', 'hi', 'x'} or None when the text is not a simple numeric criterion."""
    t = _clean(text)
    if not t:
        return None
    t = re.split(r"[;；,(（]", t)[0].rstrip("。.")        # only the first clause counts: "≥5; NTD 背景 ≤2%" -> "≥5"
    m = re.fullmatch(r"(?:(>=|<=|>|<|=|==)(%s)%%?(?:[a-zA-Z/]*)?)" % _NUM, t)
    if m:
        op, x = m.group(1), float(m.group(2))
        return {"kind": {">=": "ge", "<=": "le", ">": "gt", "<": "lt", "=": "eq", "==": "eq"}[op], "x": x}
    m = re.fullmatch(r"(%s)%%?[-~](%s)%%?(?:[a-zA-Z/]*)?" % (_NUM, _NUM), t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo <= hi:
            return {"kind": "between", "lo": lo, "hi": hi}
    m = re.fullmatch(r"±(%s)%%?(?:[a-zA-Z/]*)?" % _NUM, t)
    if m:
        return {"kind": "abs_le", "x": abs(float(m.group(1)))}
    return None


def parse_value(text):
    """Leading number of a measured value ("98%", "46.2 (n=3)", "SI 12" -> 12)."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    t = _clean(text)
    m = re.search(_NUM, t)
    return float(m.group(0)) if m else None


def evaluate(criterion, value):
    """-> '符合' / '不符合' / None (criterion or value not machine-readable)."""
    c = parse_criterion(criterion)
    v = parse_value(value)
    if c is None or v is None:
        return None
    k = c["kind"]
    if k == "ge":
        ok = v >= c["x"]
    elif k == "gt":
        ok = v > c["x"]
    elif k == "le":
        ok = v <= c["x"]
    elif k == "lt":
        ok = v < c["x"]
    elif k == "eq":
        ok = abs(v - c["x"]) < 1e-9
    elif k == "between":
        ok = c["lo"] <= v <= c["hi"]
    else:                      # abs_le
        ok = abs(v) <= c["x"]
    return "符合" if ok else "不符合"


# ------------------------------------------------------------------ calculators


def summary(values):
    x = _nums(values, "values", 1)
    n, m, s = len(x), mean(x), sd(x)
    rows = [_row("n", n), _row("mean", m), _row("SD", s), _row("RSD (%)", 100 * s / m if m else float("nan")),
            _row("min", min(x)), _row("max", max(x)), _row("median", sorted(x)[n // 2] if n % 2 else (sorted(x)[n // 2 - 1] + sorted(x)[n // 2]) / 2)]
    return {"inputs": {"n": n}, "rows": rows, "details": {}}


def accuracy(pairs, level=0.90):
    """pairs: [(nominal, measured), ...] (>= 3).  Recovery (%) and relative bias per level and overall, with the two-sided
    `level` confidence interval of the mean bias (default 90 %, the usual equivalence-type presentation)."""
    p = [(float(a), float(b)) for a, b in pairs]
    if len(p) < 3:
        raise ValueError("accuracy: at least 3 (nominal, measured) pairs needed")
    if any(a == 0 for a, _ in p):
        raise ValueError("accuracy: nominal values must not be 0")
    rec = [100.0 * b / a for a, b in p]
    bias = [r - 100.0 for r in rec]
    n = len(bias)
    mb, sb = mean(bias), sd(bias)
    t = t_ppf(0.5 + level / 2.0, n - 1)
    half = t * sb / math.sqrt(n)
    levels = {}
    for a, b in p:
        levels.setdefault(a, []).append(100.0 * b / a)
    rows = [_row("mean recovery (%)", mean(rec)), _row("mean relative bias (%)", mb), _row("SD of bias (%)", sb),
            _row("%d%% CI of mean bias, lower (%%)" % round(level * 100), mb - half), _row("%d%% CI of mean bias, upper (%%)" % round(level * 100), mb + half)]
    for a in sorted(levels):
        rows.append(_row("recovery at %g (%%)" % a, mean(levels[a]), "n=%d" % len(levels[a])))
    return {"inputs": {"n": n, "level": level}, "rows": rows, "details": {"t": t, "levels": {str(k): mean(v) for k, v in levels.items()}}}


def precision(groups, level=0.95):
    """groups: list of runs (or days / analysts), each a list of replicate results (>= 2 runs, balanced or not).
    One-way random-effects ANOVA: repeatability SD (within runs), between-run SD, intermediate precision SD
    (= sqrt(within + between)), RSD (%) for each and an upper `level` confidence limit of the intermediate-precision SD
    (chi-square, approximate)."""
    g = [_nums(x, "run %d" % (i + 1), 1) for i, x in enumerate(groups or [])]
    if len(g) < 2:
        raise ValueError("precision: at least 2 runs needed")
    k = len(g)
    N = sum(len(x) for x in g)
    grand = sum(sum(x) for x in g) / N
    ssw = sum(sum((v - mean(x)) ** 2 for v in x) for x in g)
    dfw = N - k
    if dfw < 1:
        raise ValueError("precision: at least one run needs 2 or more replicates")
    msw = ssw / dfw
    ssb = sum(len(x) * (mean(x) - grand) ** 2 for x in g)
    msb = ssb / (k - 1)
    n0 = (N - sum(len(x) ** 2 for x in g) / N) / (k - 1)
    s2b = max(0.0, (msb - msw) / n0)
    s_r, s_b, s_ip = math.sqrt(msw), math.sqrt(s2b), math.sqrt(msw + s2b)
    # Satterthwaite effective degrees of freedom for the intermediate-precision variance
    num = (msw + s2b) ** 2
    den = (msw ** 2) / dfw + ((s2b ** 2) / (k - 1) if s2b > 0 else 0.0)
    dfe = max(1.0, num / den) if den > 0 else float(dfw)
    upper = s_ip * math.sqrt(dfe / chi2_ppf(1.0 - level, dfe))
    rsd = lambda s: 100.0 * s / grand if grand else float("nan")   # noqa: E731
    rows = [_row("grand mean", grand), _row("repeatability SD", s_r), _row("repeatability RSD (%)", rsd(s_r)), _row("between-run SD", s_b),
            _row("intermediate precision SD", s_ip), _row("intermediate precision RSD (%)", rsd(s_ip)),
            _row("%d%% upper limit of intermediate precision RSD (%%)" % round(level * 100), rsd(upper), "chi-square, df≈%.1f" % dfe)]
    return {"inputs": {"runs": k, "n": N, "level": level}, "rows": rows, "details": {"msw": msw, "msb": msb, "n0": n0, "df_eff": dfe}}


def linearity(x, y, level=0.95):
    """Ordinary least squares y = a + b x (>= 3 points)."""
    xs, ys = _nums(x, "x", 3), _nums(y, "y", 3)
    if len(xs) != len(ys):
        raise ValueError("linearity: x and y need the same number of points")
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    sxx = sum((a - mx) ** 2 for a in xs)
    if sxx == 0:
        raise ValueError("linearity: all x values are identical")
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    syy = sum((b - my) ** 2 for b in ys)
    slope = sxy / sxx
    icpt = my - slope * mx
    sse = sum((b - (icpt + slope * a)) ** 2 for a, b in zip(xs, ys))
    s_res = math.sqrt(sse / (n - 2)) if n > 2 else float("nan")
    r2 = 1.0 - sse / syy if syy else float("nan")
    r = math.copysign(math.sqrt(max(0.0, r2)), slope) if not math.isnan(r2) else float("nan")
    t = t_ppf(0.5 + level / 2.0, n - 2)
    se_b = s_res / math.sqrt(sxx)
    se_a = s_res * math.sqrt(1.0 / n + mx * mx / sxx)
    rows = [_row("slope", slope), _row("intercept", icpt), _row("r", r), _row("r²", r2), _row("residual SD", s_res),
            _row("%d%% CI slope, lower" % round(level * 100), slope - t * se_b), _row("%d%% CI slope, upper" % round(level * 100), slope + t * se_b),
            _row("%d%% CI intercept, lower" % round(level * 100), icpt - t * se_a), _row("%d%% CI intercept, upper" % round(level * 100), icpt + t * se_a)]
    return {"inputs": {"n": n}, "rows": rows, "details": {"slope": slope, "intercept": icpt, "s_res": s_res}}


def lod_loq(slope, sigma=None, blanks=None):
    """ICH Q2 calibration-curve approach: LOD = 3.3 σ / S, LOQ = 10 σ / S.  σ is given directly (residual SD of the
    regression or SD of the intercept) or computed as the SD of replicate blanks."""
    s = float(slope)
    if s == 0:
        raise ValueError("lod_loq: slope must not be 0")
    if sigma is None:
        b = _nums(blanks, "blanks", 3)
        sg = sd(b)
        note = "σ = SD of %d blanks" % len(b)
    else:
        sg = float(sigma)
        note = "σ given"
    if sg < 0:
        raise ValueError("lod_loq: σ must not be negative")
    return {"inputs": {"slope": s, "sigma": sg}, "rows": [_row("σ", sg, note), _row("LOD", 3.3 * sg / abs(s), "3.3 σ / S"), _row("LOQ", 10.0 * sg / abs(s), "10 σ / S")], "details": {}}


def tost(reference, test, margin, level=0.90):
    """Paired equivalence (two one-sided tests): the mean paired difference (test - reference) with a two-sided
    `level` CI (default 90 %) is compared with ±margin (in the unit of the data).  Equivalent when the CI lies inside."""
    a, b = _nums(reference, "reference", 3), _nums(test, "test", 3)
    if len(a) != len(b):
        raise ValueError("tost: reference and test need the same number of pairs")
    m = float(margin)
    if m <= 0:
        raise ValueError("tost: margin must be positive")
    d = [y - x for x, y in zip(a, b)]
    n = len(d)
    md, sdd = mean(d), sd(d)
    t = t_ppf(0.5 + level / 2.0, n - 1)
    half = t * sdd / math.sqrt(n)
    lo, hi = md - half, md + half
    ok = lo > -m and hi < m
    rows = [_row("mean difference (test − reference)", md), _row("SD of differences", sdd), _row("%d%% CI lower" % round(level * 100), lo),
            _row("%d%% CI upper" % round(level * 100), hi), _row("equivalence margin", m, "±"), _row("equivalent", "符合" if ok else "不符合", "CI inside ±margin" if ok else "CI not inside ±margin")]
    return {"inputs": {"n": n, "level": level, "margin": m}, "rows": rows, "details": {"equivalent": ok}}


def count_cv(p_percent, events=None, target_cv=None):
    """Counting statistics of a percentage measured by events: CV ≈ sqrt((1−p)/(p·N)).  Give the event count N to get
    the CV, and/or a target CV (%) to get the number of events needed."""
    p = float(p_percent) / 100.0
    if not 0.0 < p < 1.0:
        raise ValueError("count_cv: percentage must be between 0 and 100 (exclusive)")
    rows = []
    if events is not None:
        n = float(events)
        if n <= 0:
            raise ValueError("count_cv: events must be positive")
        rows.append(_row("CV from counting (%)", 100.0 * math.sqrt((1 - p) / (p * n)), "N=%d events, p=%.3g%%" % (n, p * 100)))
        rows.append(_row("positive events", p * n))
    if target_cv is not None:
        c = float(target_cv) / 100.0
        if c <= 0:
            raise ValueError("count_cv: target CV must be positive")
        rows.append(_row("events needed", math.ceil((1 - p) / (p * c * c)), "for CV ≤ %g%%" % float(target_cv)))
    if not rows:
        raise ValueError("count_cv: give the number of events and/or a target CV")
    return {"inputs": {"p_percent": float(p_percent)}, "rows": rows, "details": {}}


CALCULATORS = {
    "summary": lambda d: summary(d.get("values")),
    "accuracy": lambda d: accuracy(d.get("pairs"), float(d.get("level") or 0.90)),
    "precision": lambda d: precision(d.get("groups"), float(d.get("level") or 0.95)),
    "linearity": lambda d: linearity(d.get("x"), d.get("y"), float(d.get("level") or 0.95)),
    "lod_loq": lambda d: lod_loq(d.get("slope"), d.get("sigma"), d.get("blanks")),
    "tost": lambda d: tost(d.get("reference"), d.get("test"), d.get("margin"), float(d.get("level") or 0.90)),
    "count_cv": lambda d: count_cv(d.get("p_percent"), d.get("events"), d.get("target_cv")),
}


def run(name, data):
    if name not in CALCULATORS:
        raise ValueError("unknown calculator: %s" % name)
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    try:
        return CALCULATORS[name](data)
    except (TypeError, KeyError) as e:
        raise ValueError("invalid input (%s)" % type(e).__name__)
