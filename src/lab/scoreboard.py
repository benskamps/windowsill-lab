"""The calibration scoreboard — one figure of *everything claimed vs theory*.

Ten-plus milestones of rigor live on ten separate report pages. There is no
single image that answers "across the whole curriculum, how close did the lab's
measurements land to the exact / benchmark values?" This module builds exactly
that: for every quantitative-benchmark milestone it re-derives the measured
value from the milestone's persisted report JSON (the same way ``checks`` grades
it — a receipt, not an echo), pairs it with the exact/benchmark value and the
check-owned tolerance, and renders one house-style "money plot".

The plot's x-axis is the **signed deviation from theory in units of the check
tolerance**, ``z = (measured − exact) / tol``. That common axis lets Onsager's
T_c, the exponents γ/ν and β/ν, the Potts T_c ladder, the XY universal-jump
crossing, Wannier's residual entropy, the Nishimori-line energy and the
Allen–Cahn coarsening exponent — quantities on wildly different scales — sit on
one chart. A shaded band at ``|z| ≤ 1`` is the tolerance; every point inside it
is a milestone whose number reproduced theory within its own gate.

Benchmark constants and grading helpers are imported from ``checks`` so the
scoreboard cannot silently disagree with ``lab verify``.
"""
from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass

from . import checks
from .checks import (
    ALLEN_CAHN_EXPONENT, ALLEN_CAHN_TOL, BETA_OVER_NU, GAMMA_OVER_NU,
    MNP_ENERGY_TOL, ONSAGER_TC, TC_3D, TC_TRI, TWO_OVER_PI, T_BKT,
    WANNIER_S0, WANNIER_S0_TOL,
)
from .publish import REPORTS_DIR

# Where the rendered figure lands. It is committed so the archive index (built by
# the stdlib-only ``archive.py``) can embed it without importing matplotlib.
SCOREBOARD_PNG = REPORTS_DIR / "scoreboard.png"

# House palette (matches render.py / archive.py).
CREAM = "#f6efe1"
PANEL = "#fbf6ea"
INK = "#3a2e21"
COPPER = "#7a4e2f"
LEAF = "#5f8b46"
AMBER = "#b06a45"
BAND = "#d7e3c6"
RULE = "#d6c0a2"


@dataclass(frozen=True)
class ScoreEntry:
    """One measured-vs-theory row on the scoreboard."""
    milestone: str
    observable: str
    measured: float
    exact: float
    tol: float
    unit: str = ""

    @property
    def deviation(self) -> float:
        return self.measured - self.exact

    @property
    def z(self) -> float:
        """Signed deviation in units of the check tolerance."""
        return self.deviation / self.tol if self.tol else math.inf

    @property
    def passed(self) -> bool:
        return abs(self.deviation) <= self.tol

    def value_label(self) -> str:
        u = f" {self.unit}" if self.unit else ""
        return f"{self.measured:.4g} vs {self.exact:.4g}{u}  (±{self.tol:g})"


# ── report access ────────────────────────────────────────────────────────────
def _repo_reports_newest_first() -> list:
    """Committed archive report JSONs (``reports/`` + ``reports/receipts/``), newest-first.

    Deliberately excludes ``~/.lab`` (unlike ``checks._reports_newest_first``): the
    published scoreboard must be a function of the committed archive alone, so the
    figure a clean CI checkout renders equals the one committed here — no local run
    history can perturb it. Ordering mirrors the checks' date-key sort so the newest
    gradable report per milestone wins (e.g. the passing M07 over an earlier attempt).
    """
    from .publish import REPORTS_DIR
    paths = list(REPORTS_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*.json"))
    receipts = REPORTS_DIR / "receipts"
    if receipts.exists():
        paths += receipts.glob("run-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.json")

    def sort_key(path):
        is_receipt = path.parent.name == "receipts"
        date = path.stem[4:14] if is_receipt else path.stem[:10]
        return date, not is_receipt   # same date: full report before its receipt

    return sorted(paths, key=sort_key, reverse=True)


def _load_reports(reports: list[dict] | None = None) -> list[dict]:
    if reports is not None:
        return reports
    import json
    out: list[dict] = []
    for p in _repo_reports_newest_first():
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _tagged(reports: list[dict], tag: str) -> list[dict]:
    """All reports whose ``experiment`` starts with ``tag``, newest-first.

    Extractors iterate these and use the first one they can actually read, exactly
    as ``checks._grade`` grades the newest report a check *understands* (so a tiny
    local smoke run tagged for the same milestone can't shadow the real report).
    """
    return [r for r in reports if str(r.get("experiment") or "").startswith(tag)]


def _arr(report: dict, key: str) -> list[float] | None:
    v = report.get(key)
    return v if isinstance(v, list) and v else None


# ── per-milestone extractors: each returns 0+ ScoreEntry ─────────────────────
def _m01(reports):
    # 2D Ising: χ-peak T_c vs Onsager (check_m01 uses the raw argmax, tol ±0.1).
    for r in reports:
        exp = str(r.get("experiment") or "")
        if exp and not exp.startswith("M01"):
            continue
        T, chi = _arr(r, "T"), _arr(r, "chi")
        if not T or not chi or len(T) != len(chi):
            continue
        peak = T[max(range(len(chi)), key=lambda i: chi[i])]
        return [ScoreEntry("M01", "2D Ising T_c (χ peak)", peak, ONSAGER_TC, 0.1)]
    return []


def _m02(reports):
    for r in _tagged(reports, "M02"):
        curves = r.get("curves") or []
        Ls = [c.get("L") for c in curves]
        chimax = [c.get("chi_max") for c in curves]
        if len(Ls) < 3 or any(v is None or v <= 0 for v in Ls + chimax):
            continue
        slope, _ = checks._loglog_slope(Ls, chimax)
        return [ScoreEntry("M02", "2D Ising γ/ν (FSS)", slope, GAMMA_OVER_NU, 0.15)]
    return []


def _m03(reports):
    for r in _tagged(reports, "M03"):
        curves = []
        for c in r.get("curves") or []:
            L, T, M = c.get("L"), c.get("T"), c.get("M")
            if L and T and M and len(T) == len(M):
                curves.append((L, list(T), list(M)))
        if len(curves) < 3:
            continue
        bon, _ = checks._fit_beta_over_nu(curves)
        return [ScoreEntry("M03", "2D Ising β/ν (collapse)", bon, BETA_OVER_NU, 0.03)]
    return []


def _peak_entry(reports, tag, arr_key, milestone, label, exact, tol):
    for r in _tagged(reports, tag):
        T, y = _arr(r, "T"), _arr(r, arr_key)
        if not T or not y or len(T) != len(y) or len(T) < 3:
            continue
        peak = checks._refine_peak_stdlib(T, y)
        return [ScoreEntry(milestone, label, peak, exact, tol)]
    return []


def _m04(reports):
    return _peak_entry(reports, "M04", "specific_heat", "M04", "2D Ising T_c (C peak)", ONSAGER_TC, 0.1)


def _m05(reports):
    return _peak_entry(reports, "M05", "chi", "M05", "Triangular Ising T_c", TC_TRI, 0.15)


def _m06(reports):
    return _peak_entry(reports, "M06", "chi", "M06", "3D Ising T_c", TC_3D, 0.15)


def _m07(reports):
    for r in _tagged(reports, "M07"):
        entries = []
        for entry in r.get("per_q") or []:
            q = entry.get("q")
            T, chi = entry.get("T"), entry.get("chi")
            if not q or not T or not chi or len(T) != len(chi) or len(T) < 3:
                continue
            peak = checks._refine_peak_stdlib(T, chi)
            tc = 1.0 / math.log(1.0 + math.sqrt(q))
            tol = 0.1 if q <= 4 else 0.15   # mirrors check_m07 (first-order q≥5 wider)
            entries.append(ScoreEntry("M07", f"Potts q={q} T_c", peak, tc, tol))
        if entries:
            return entries
    return []


def _m08(reports):
    for r in _tagged(reports, "M08"):
        T, Y = _arr(r, "T"), _arr(r, "helicity_modulus")
        if not T or not Y or len(T) != len(Y) or len(T) < 3:
            continue
        # First downward crossing of Υ(T) with the (2/π)·T universal-jump line
        # (mirrors check_m08).
        g = [Y[i] - TWO_OVER_PI * T[i] for i in range(len(T))]
        crossing = None
        for i in range(len(T) - 1):
            if g[i] >= 0.0 and g[i + 1] < 0.0:
                frac = g[i] / (g[i] - g[i + 1])
                crossing = T[i] + frac * (T[i + 1] - T[i])
                break
        if crossing is None:
            continue
        return [ScoreEntry("M08", "XY BKT T_BKT (Υ jump)", crossing, T_BKT, 0.07)]
    return []


def _m10(reports):
    return _peak_entry(reports, "M10", "chi_staggered", "M10", "AFM Ising T_N", ONSAGER_TC, 0.1)


def _m13(reports):
    from .entropy import LN2, residual_entropy
    for r in _tagged(reports, "M13"):
        T, C = _arr(r, "T"), _arr(r, "specific_heat")
        if not T or not C or len(T) != len(C) or len(T) < 3:
            continue
        s0 = residual_entropy(T, C, s_inf=LN2, add_high_t_tail=True)
        return [ScoreEntry("M13", "Triangular AFM S₀/N", s0, WANNIER_S0, WANNIER_S0_TOL, "k_B")]
    return []


def _m14(reports):
    for r in _tagged(reports, "M14"):
        pts = r.get("calibration_points") or []
        worst = None
        for pt in pts:
            p, T, e = pt.get("p"), pt.get("T"), pt.get("energy")
            if p is None or T is None or e is None or T <= 0:
                continue
            if abs(math.tanh(1.0 / T) - (1.0 - 2.0 * p)) > 1e-2:   # off the Nishimori line
                continue
            e_exact = -2.0 * math.tanh(1.0 / T)
            if worst is None or abs(e - e_exact) > abs(worst.deviation):
                worst = ScoreEntry("M14", "Nishimori-line E/N (worst p)", e, e_exact, MNP_ENERGY_TOL)
        if worst:
            return [worst]
    return []


def _m15(reports):
    for r in _tagged(reports, "M15"):
        t, L = _arr(r, "times"), _arr(r, "L_corr")
        L_box = r.get("L")
        if not t or not L or len(t) != len(L) or not L_box:
            continue
        t_fit_min = r.get("t_fit_min", checks.M15_T_FIT_MIN)
        l_min_fit = r.get("l_min_fit", checks.M15_L_MIN_FIT)
        sat_frac = r.get("sat_frac", checks.M15_SAT_FRAC)
        xs, ys = [], []
        for ti, Li in zip(t, L):
            if Li is None or ti is None or Li <= 0 or not math.isfinite(Li):
                continue
            if ti >= t_fit_min and l_min_fit <= Li <= sat_frac * L_box:
                xs.append(float(ti)); ys.append(float(Li))
        if len(xs) < 5:
            continue
        slope, _r2, _n = checks._loglog_slope_r2(xs, ys)
        return [ScoreEntry("M15", "Glauber coarsening n", slope, ALLEN_CAHN_EXPONENT, ALLEN_CAHN_TOL)]
    return []


# Ordered by the curriculum so the plot reads top-to-bottom as the lab grew.
_EXTRACTORS = [_m01, _m02, _m03, _m04, _m05, _m06, _m07, _m08, _m10, _m13, _m14, _m15]


def collect_entries(reports: list[dict] | None = None) -> list[ScoreEntry]:
    """Every scoreboard row we can build from the reports on record.

    Milestones without a readable report are simply skipped, so the scoreboard
    degrades gracefully (a fresh checkout with only receipts still renders).
    """
    reports = _load_reports(reports)
    entries: list[ScoreEntry] = []
    for extract in _EXTRACTORS:
        entries.extend(extract(reports))
    return entries


# ── the figure ───────────────────────────────────────────────────────────────
def build_figure(entries: list[ScoreEntry] | None = None):
    """Render the scoreboard to a matplotlib Figure (house cream/serif style)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if entries is None:
        entries = collect_entries()

    n = len(entries)
    fig, ax = plt.subplots(figsize=(9.6, max(3.0, 0.62 * n + 1.8)))
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(PANEL)

    if not entries:
        ax.text(0.5, 0.5, "no calibrated milestones on record yet",
                ha="center", va="center", fontsize=13, color=INK, alpha=0.6,
                transform=ax.transAxes)
        ax.axis("off")
        return fig

    # Row 0 at the top → reverse for a top-down curriculum read.
    ys = list(range(n))[::-1]

    # The tolerance band (|z| ≤ 1) and the theory line at 0.
    ax.axvspan(-1, 1, color=BAND, alpha=0.7, lw=0, zorder=0)
    ax.axvline(0, color=COPPER, lw=1.6, zorder=1)
    ax.axvline(-1, color=RULE, lw=1.0, ls="--", zorder=1)
    ax.axvline(1, color=RULE, lw=1.0, ls="--", zorder=1)

    zs = [max(-1.6, min(1.6, e.z)) for e in entries]   # clamp for display only
    for y, e, z in zip(ys, entries, zs):
        color = LEAF if e.passed else AMBER
        ax.plot([0, z], [y, y], color=color, lw=1.2, alpha=0.5, zorder=2)
        ax.plot(z, y, "o", ms=9, color=color, markeredgecolor=INK,
                markeredgewidth=0.7, zorder=3)
        # The real measured-vs-exact numbers in the right gutter.
        ax.annotate(e.value_label(), xy=(1.02, y), xycoords=("axes fraction", "data"),
                    va="center", ha="left", fontsize=8.5, color=INK, alpha=0.85,
                    family="monospace")

    ax.set_yticks(ys)
    ax.set_yticklabels([f"{e.milestone} · {e.observable}" for e in entries], fontsize=9.5)
    ax.set_ylim(-0.8, n - 0.2)
    ax.set_xlim(-1.75, 1.75)
    ax.set_xlabel("deviation from exact / benchmark  (in units of the check tolerance,  z = (measured − theory) / tol)",
                  fontsize=9.5, color=INK)
    n_pass = sum(1 for e in entries if e.passed)
    ax.set_title(
        f"windowsill-lab · calibration scoreboard — {n_pass}/{n} within tolerance",
        fontsize=13, color=INK, pad=12,
    )

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(RULE)
    ax.tick_params(colors=INK)
    for lbl in ax.get_yticklabels():
        lbl.set_color(INK)

    # A quiet caption on the shaded band's meaning.
    fig.text(0.012, 0.012,
             "shaded band = each milestone's own check tolerance (|z| ≤ 1). "
             "Every tolerance is check-owned and physically justified; a point inside the band "
             "means the measurement reproduced theory within its gate.",
             fontsize=7.6, color=INK, alpha=0.6, ha="left")

    fig.subplots_adjust(left=0.28, right=0.68, top=0.9, bottom=0.14)
    return fig


def figure_png_bytes(entries: list[ScoreEntry] | None = None) -> bytes:
    """The scoreboard figure as PNG bytes (cream background baked in)."""
    fig = build_figure(entries)
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=CREAM, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def figure_data_uri(entries: list[ScoreEntry] | None = None) -> str:
    return "data:image/png;base64," + base64.b64encode(figure_png_bytes(entries)).decode("ascii")


def write_scoreboard(path=None, entries: list[ScoreEntry] | None = None):
    """Write the scoreboard PNG to ``reports/scoreboard.png`` and return its path."""
    path = path or SCOREBOARD_PNG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(figure_png_bytes(entries))
    return path
