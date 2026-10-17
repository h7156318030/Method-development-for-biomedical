"""Unit tests of app/stats.py (URS-150): distributions against published table values, criteria parsing, and every
calculator cross-checked against an independent computation (numpy when installed)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import stats  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class TestDistributions(unittest.TestCase):
    def test_quantiles_match_table_values(self):
        self.assertAlmostEqual(stats.norm_ppf(0.975), 1.959964, places=5)
        self.assertAlmostEqual(stats.t_ppf(0.975, 10), 2.228139, places=5)
        self.assertAlmostEqual(stats.t_ppf(0.95, 5), 2.015048, places=5)
        self.assertAlmostEqual(stats.t_ppf(0.975, 2), 4.302653, places=5)
        self.assertAlmostEqual(stats.t_ppf(0.5, 7), 0.0, places=6)
        self.assertAlmostEqual(stats.chi2_ppf(0.975, 9), 19.022768, places=4)
        self.assertAlmostEqual(stats.chi2_ppf(0.025, 9), 2.700389, places=4)
        self.assertAlmostEqual(stats.chi2_ppf(0.95, 1), 3.841459, places=4)

    def test_bad_probabilities_are_rejected(self):
        for f in (lambda: stats.t_ppf(0, 5), lambda: stats.t_ppf(1.2, 5), lambda: stats.chi2_ppf(-1, 3), lambda: stats.t_ppf(0.9, 0)):
            with self.assertRaises(ValueError):
                f()


class TestCriteria(unittest.TestCase):
    def test_parse_and_evaluate(self):
        cases = [("≥5", 46, "符合"), ("≥ 5", "3", "不符合"), ("≤2%", "2.5%", "不符合"), ("≤ 2 %", "1.9", "符合"), ("90–110%", "98%", "符合"),
                 ("90-110", 111, "不符合"), ("80%–120%", "80", "符合"), ("±15%", "-12", "符合"), ("±15", "16", "不符合"), (">0.99", 0.995, "符合"),
                 ("<5", 5, "不符合"), ("=5", "5.0", "符合"), ("≥5；NTD 背景 ≤2%", 6, "符合"), ("RSD ≤ 10%（每可报告结果 2 管均值）", 9, None)]
        for crit, val, want in cases:
            self.assertEqual(stats.evaluate(crit, val), want, (crit, val))

    def test_unparseable_gives_none(self):
        for crit, val in (("", 5), ("见方案", 5), ("≥5", ""), ("≥5", "n/a"), (None, None)):
            self.assertIsNone(stats.evaluate(crit, val), (crit, val))


@unittest.skipIf(np is None, "numpy not installed")
class TestCalculators(unittest.TestCase):
    def val(self, res, metric):
        return [r["value"] for r in res["rows"] if r["metric"] == metric][0]

    def assertAlmostEqual(self, a, b, places=None, msg=None, delta=None):      # values are shown with 4 significant digits
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and delta is None:
            return super().assertAlmostEqual(a, b, delta=max(abs(b) * 2e-3, 1e-6), msg=msg)
        return super().assertAlmostEqual(a, b, places=places, delta=delta, msg=msg)

    def test_summary(self):
        x = [10.1, 9.8, 10.4, 10.0, 9.9]
        res = stats.summary(x)
        self.assertAlmostEqual(self.val(res, "mean"), float(np.mean(x)), places=3)
        self.assertAlmostEqual(self.val(res, "SD"), float(np.std(x, ddof=1)), places=3)
        self.assertAlmostEqual(self.val(res, "RSD (%)"), 100 * float(np.std(x, ddof=1) / np.mean(x)), places=2)

    def test_accuracy(self):
        pairs = [(10, 9.6), (10, 10.2), (10, 9.9), (50, 51.5), (50, 48.9), (50, 50.4), (90, 92.0), (90, 88.5), (90, 90.9)]
        res = stats.accuracy(pairs, 0.90)
        bias = np.array([100 * b / a - 100 for a, b in pairs])
        half = stats.t_ppf(0.95, 8) * bias.std(ddof=1) / math.sqrt(9)
        self.assertAlmostEqual(self.val(res, "mean relative bias (%)"), float(bias.mean()), places=3)
        self.assertAlmostEqual(self.val(res, "90% CI of mean bias, upper (%)"), float(bias.mean() + half), places=3)
        self.assertAlmostEqual(self.val(res, "recovery at 50 (%)"), float(np.mean([100 * b / a for a, b in pairs if a == 50])), places=3)
        with self.assertRaises(ValueError):
            stats.accuracy([(10, 9), (10, 11)])
        with self.assertRaises(ValueError):
            stats.accuracy([(0, 1), (10, 9), (10, 11)])

    def test_precision_anova(self):
        g = [[10.0, 11.0, 10.0], [12.0, 13.0, 12.0], [9.0, 10.0, 9.0]]
        res = stats.precision(g)
        allv = np.array(sum(g, []))
        k, n = 3, 3
        msw = sum(float(np.var(x, ddof=1)) for x in g) / k                 # balanced: mean of within variances
        means = np.array([np.mean(x) for x in g])
        msb = n * float(np.var(means, ddof=1))
        s2b = max(0.0, (msb - msw) / n)
        self.assertAlmostEqual(self.val(res, "repeatability SD"), math.sqrt(msw), places=3)
        self.assertAlmostEqual(self.val(res, "between-run SD"), math.sqrt(s2b), places=3)
        self.assertAlmostEqual(self.val(res, "intermediate precision SD"), math.sqrt(msw + s2b), places=3)
        self.assertAlmostEqual(self.val(res, "grand mean"), float(allv.mean()), places=3)
        self.assertGreater(self.val(res, "95% upper limit of intermediate precision RSD (%)"), self.val(res, "intermediate precision RSD (%)"))
        with self.assertRaises(ValueError):
            stats.precision([[1, 2]])
        with self.assertRaises(ValueError):
            stats.precision([[1], [2]])                                     # no replicate anywhere

    def test_precision_unbalanced_and_no_between_variance(self):
        res = stats.precision([[5.0, 5.0, 5.0], [5.0, 5.0]])               # identical results: all SD are 0, no crash
        self.assertEqual(self.val(res, "intermediate precision SD"), 0.0)

    def test_linearity_matches_polyfit(self):
        x = [1, 2, 3, 4, 5, 6]
        y = [2.1, 3.9, 6.2, 7.8, 10.1, 12.2]
        res = stats.linearity(x, y)
        b, a = np.polyfit(x, y, 1)
        self.assertAlmostEqual(self.val(res, "slope"), float(b), places=3)
        self.assertAlmostEqual(self.val(res, "intercept"), float(a), places=3)
        self.assertAlmostEqual(self.val(res, "r"), float(np.corrcoef(x, y)[0, 1]), places=4)
        self.assertAlmostEqual(self.val(res, "r²"), float(np.corrcoef(x, y)[0, 1] ** 2), places=4)
        self.assertLess(self.val(res, "95% CI slope, lower"), self.val(res, "slope"))
        with self.assertRaises(ValueError):
            stats.linearity([1, 1, 1], [1, 2, 3])
        with self.assertRaises(ValueError):
            stats.linearity([1, 2], [1, 2])

    def test_lod_loq(self):
        res = stats.lod_loq(2.0, sigma=0.5)
        self.assertAlmostEqual(self.val(res, "LOD"), 3.3 * 0.5 / 2.0, places=4)
        self.assertAlmostEqual(self.val(res, "LOQ"), 10 * 0.5 / 2.0, places=4)
        res = stats.lod_loq(-2.0, blanks=[0.1, 0.3, 0.2, 0.25])
        self.assertAlmostEqual(self.val(res, "LOQ"), 10 * float(np.std([0.1, 0.3, 0.2, 0.25], ddof=1)) / 2.0, places=4)
        with self.assertRaises(ValueError):
            stats.lod_loq(0, sigma=1)

    def test_tost(self):
        ref, test = [10, 10, 10, 10, 10], [10.1, 9.9, 10.2, 10.0, 10.1]
        res = stats.tost(ref, test, 0.5)
        d = np.array(test) - np.array(ref)
        half = stats.t_ppf(0.95, 4) * d.std(ddof=1) / math.sqrt(5)
        self.assertAlmostEqual(self.val(res, "90% CI upper"), float(d.mean() + half), places=3)
        self.assertEqual(self.val(res, "equivalent"), "符合")
        self.assertEqual(stats.tost(ref, [11, 11.2, 10.9, 11.1, 11.0], 0.5)["rows"][-1]["value"], "不符合")

    def test_count_cv(self):
        res = stats.count_cv(5, events=10000, target_cv=10)
        self.assertAlmostEqual(self.val(res, "CV from counting (%)"), 100 * math.sqrt(0.95 / (0.05 * 10000)), places=2)
        self.assertEqual(self.val(res, "events needed"), 1900)
        for bad in ((0, 100), (100, 100), (5, -1)):
            with self.assertRaises(ValueError):
                stats.count_cv(bad[0], events=bad[1])

    def test_run_dispatch_and_garbage(self):
        self.assertEqual(stats.run("summary", {"values": [1, 2, 3]})["rows"][0]["value"], 3)
        for name, data in (("nope", {}), ("summary", {"values": ["a"]}), ("summary", "x"), ("linearity", {"x": [1, 2, 3]}), ("precision", {})):
            with self.assertRaises(ValueError):
                stats.run(name, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
