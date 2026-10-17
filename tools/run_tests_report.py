"""运行 MethodFlow 自动测试并生成 docs\\自动化测试报告.md。

用法:  python tools\\run_tests_report.py [--no-write]

测试在临时数据目录中运行（各测试模块自行创建并在结束时删除），不会触碰真实的 data\\ 文件夹。
报告内容：日期、Python 与依赖版本、逐项结果（含 URS 编号及需求摘要）、汇总、未被自动测试覆盖的需求、
被测文件（app、tests、tools）的 SHA-256 指纹（程序未使用 git，用指纹标识“测的是哪一版代码”）。
"""
import argparse
import datetime as dt
import hashlib
import io
import os
import platform
import re
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URS_DOC = os.path.join(ROOT, "docs", "URS_需求与测试追溯.md")
REPORT = os.path.join(ROOT, "docs", "自动化测试报告.md")
PACKAGES = ["fastapi", "starlette", "pydantic", "uvicorn", "python-docx", "lxml", "matplotlib", "numpy", "Pillow", "bcrypt", "pypdf", "httpx"]


class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []          # dicts: id, status, secs, detail
        self._t0 = {}

    def startTest(self, test):
        super().startTest(test)
        self._t0[test.id()] = time.time()

    def _add(self, test, status, detail=""):
        self.rows.append({"id": test.id(), "status": status, "secs": time.time() - self._t0.get(test.id(), time.time()), "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test); self._add(test, "通过")

    def addFailure(self, test, err):
        super().addFailure(test, err); self._add(test, "失败", self._exc_text(err))

    def addError(self, test, err):
        super().addError(test, err); self._add(test, "错误", self._exc_text(err))

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._add(test, "跳过", reason)

    @staticmethod
    def _exc_text(err):
        import traceback
        return "".join(traceback.format_exception(*err))[-1500:]


def read_urs():
    """Parse docs\\URS_需求与测试追溯.md -> {number: (requirement, method)}"""
    out = {}
    if not os.path.exists(URS_DOC):
        return out
    with open(URS_DOC, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*URS-(\d+)\s*\|(.+?)\|(.+?)\|(.+?)\|", line)
            if m:
                out[int(m.group(1))] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
    return out


def fingerprint():
    h = {}
    files = []
    for folder in ("app", "tests", "tools"):
        for dp, dn, fn in os.walk(os.path.join(ROOT, folder)):
            dn[:] = [d for d in dn if d != "__pycache__"]
            for f in fn:
                if f.endswith((".py", ".js", ".css", ".html")):
                    files.append(os.path.join(dp, f))
    for p in sorted(files):
        with open(p, "rb") as fh:
            h[os.path.relpath(p, ROOT).replace("\\", "/")] = hashlib.sha256(fh.read()).hexdigest()
    total = hashlib.sha256("".join(k + v for k, v in sorted(h.items())).encode()).hexdigest()
    return h, total


def pkg_versions():
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover
        return {}
    out = {}
    for p in PACKAGES:
        try:
            out[p] = metadata.version(p)
        except Exception:
            out[p] = "未安装"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true", help="只运行，不写报告")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "tests"))

    started = dt.datetime.now()
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=os.path.join(ROOT, "tests"))
    res = Result()
    t0 = time.time()
    suite.run(res)
    elapsed = time.time() - t0

    urs = read_urs()
    n = len(res.rows)
    passed = sum(1 for r in res.rows if r["status"] == "通过")
    failed = sum(1 for r in res.rows if r["status"] == "失败")
    errors = sum(1 for r in res.rows if r["status"] == "错误")
    skipped = sum(1 for r in res.rows if r["status"] == "跳过")
    verdict = "全部通过" if (n and passed == n) else "存在未通过项"
    print("%s：共 %d 项，通过 %d，失败 %d，错误 %d，跳过 %d，用时 %.1f s" % (verdict, n, passed, failed, errors, skipped, elapsed))
    for r in res.rows:
        if r["status"] != "通过":
            print("  [%s] %s\n%s" % (r["status"], r["id"], r["detail"]))

    covered = set()
    lines = []
    for r in sorted(res.rows, key=lambda x: x["id"]):
        short = r["id"].split(".", 1)[-1]               # Class.test_name
        m = re.search(r"test_URS(\d+)", short)
        num = int(m.group(1)) if m else None
        if num is not None:
            covered.add(num)
        req = urs.get(num, ("", "", ""))[0] if num is not None else ""
        req = (req[:48] + "…") if len(req) > 48 else req
        lines.append("| %s | %s | %s | %s | %.2f |" % (("URS-%02d" % num) if num is not None else "—", "`%s`" % short, req or "—", r["status"], r["secs"]))

    if args.no_write:
        return 0 if (n and passed == n) else 1

    fp, total = fingerprint()
    uncovered = [(k, v) for k, v in sorted(urs.items()) if k not in covered]
    py = sys.version.replace("\n", " ")
    pk = pkg_versions()

    md = []
    md.append("# MethodFlow 自动化测试报告")
    md.append("")
    md.append("> 由 `tools\\run_tests_report.py` 自动生成，请勿手工修改。**本报告是开发者回归测试证据，不是 IQ/OQ/PQ 验证报告；程序不是已验证的 GxP 系统**（见 `URS_需求与测试追溯.md` 第 5 节）。")
    md.append("")
    md.append("## 1. 结论")
    md.append("")
    md.append("- **结果：%s** —— 共 %d 项，通过 %d，失败 %d，错误 %d，跳过 %d" % (verdict, n, passed, failed, errors, skipped))
    md.append("- 执行时间：%s（用时 %.1f 秒）" % (started.strftime("%Y-%m-%d %H:%M:%S"), elapsed))
    md.append("- 测试在临时数据目录运行，结束后删除，不影响真实 `data\\` 文件夹")
    md.append("")
    md.append("## 2. 环境")
    md.append("")
    md.append("| 项目 | 内容 |")
    md.append("|---|---|")
    md.append("| 操作系统 | %s |" % platform.platform())
    md.append("| Python | %s |" % py)
    md.append("| 机器 / 处理器 | %s |" % (platform.machine() or "—"))
    for k, v in pk.items():
        md.append("| %s | %s |" % (k, v))
    md.append("| 版本管理 | 未使用 git；以下用文件 SHA-256 指纹标识被测代码 |")
    md.append("| 被测代码总指纹 | `%s` |" % total)
    md.append("")
    md.append("## 3. 逐项结果")
    md.append("")
    md.append("| URS | 测试 | 需求摘要 | 结果 | 用时(s) |")
    md.append("|---|---|---|---|---|")
    md.extend(lines)
    md.append("")
    bad = [r for r in res.rows if r["status"] in ("失败", "错误")]
    if bad:
        md.append("## 4. 失败详情")
        md.append("")
        for r in bad:
            md.append("### %s（%s）" % (r["id"], r["status"]))
            md.append("```")
            md.append(r["detail"])
            md.append("```")
        md.append("")
    md.append("## %d. 需求覆盖情况" % (5 if bad else 4))
    md.append("")
    md.append("- 需求总数 %d；有自动测试覆盖（测试名含 URS 编号）的 %d 项" % (len(urs), len(covered & set(urs))))
    if uncovered:
        md.append("- 无自动测试（须人工/UI 验证，见需求表“验证方式”）：")
        md.append("")
        md.append("| URS | 需求 | 验证方式 |")
        md.append("|---|---|---|")
        for k, (req, method, _tests) in uncovered:
            md.append("| URS-%02d | %s | %s |" % (k, req[:60], method))
    md.append("")
    md.append("“部分自动”的需求（如 URS-01/03/19/22/33/51）自动测试只覆盖其中一部分，余下部分的说明见需求表。")
    md.append("")
    md.append("## %d. 被测文件指纹（SHA-256）" % (6 if bad else 5))
    md.append("")
    md.append("| 文件 | SHA-256 |")
    md.append("|---|---|")
    for k, v in fp.items():
        md.append("| `%s` | `%s` |" % (k, v[:16] + "…" + v[-8:]))
    md.append("")
    md.append("## 局限")
    md.append("")
    md.append("- 测试用 FastAPI `TestClient` 在进程内调用接口，未经过真实网络、浏览器与前端代码（`app\\static\\*`）。")
    md.append("- 没有性能、并发压力、安全渗透、浏览器兼容性测试。")
    md.append("- 测试之间有顺序依赖：URS-30 篡改临时库后，同模块后续用例不应再校验审计链。")
    md.append("")
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))
    print("报告已写入：%s" % REPORT)
    return 0 if (n and passed == n) else 1


if __name__ == "__main__":
    sys.exit(main())
