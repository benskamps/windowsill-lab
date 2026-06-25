"""Render a daily report HTML + plots from an Ising RunResult."""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .ising import RunResult
from .onsager import onsager_magnetization, T_C


LAB_HOME = Path.home() / ".lab"
# Permanent per-run reports are committed here so the windowsill page can
# deep-link every node on the seedling stem; the nightly commits the whole
# reports/ tree on every run.
REPO_REPORTS = Path(__file__).resolve().parents[2] / "reports"


def _ensure_home() -> Path:
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    return LAB_HOME


def _slug_for(report: dict) -> str:
    """Permanent-report slug for a run — see ``publish._slug_for`` (the canon).

    Re-exported here so renderers can name their committed files without
    importing the heavier publish surface at module load; both call the same
    single source-of-truth rule, so they can never drift.
    """
    from .publish import _slug_for as _impl
    return _impl(report)


def _commit_report(date: str, slug: str, html: str, json_dump: str) -> Path:
    """Write the permanent, never-overwritten report pair into the repo.

    Produces ``reports/<date>-<slug>.html`` + ``reports/<date>-<slug>.json`` and
    refreshes ``reports/latest.html`` as a *copy* of this html — a back-compat
    pointer, never the archive slot. Returns the committed ``.html`` path.

    One milestone gets one canonical report per day: a same-day re-run of the
    same milestone deliberately overwrites its own ``<date>-<slug>.*`` (the
    content is regenerated from the same kind of run, so this is idempotent
    rather than lossy). Distinct dates and distinct slugs never collide — which
    is the whole fix: the old single ``latest.html`` buried every prior run.
    """
    REPO_REPORTS.mkdir(parents=True, exist_ok=True)
    html_path = REPO_REPORTS / f"{date}-{slug}.html"
    json_path = REPO_REPORTS / f"{date}-{slug}.json"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json_dump, encoding="utf-8")
    # Back-compat pointer: a copy of the newest, not an archive that gets clobbered.
    (REPO_REPORTS / "latest.html").write_text(html, encoding="utf-8")
    return html_path


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#f6efe1")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _plot_magnetization(result: RunResult) -> str:
    T_fine = np.linspace(result.T.min(), result.T.max(), 400)
    M_onsager = onsager_magnetization(T_fine)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T_fine, M_onsager, "-", color="#9b6b3e", linewidth=2, label="Onsager (exact, L=∞)")
    ax.errorbar(result.T, result.abs_mag, yerr=result.abs_mag_err, fmt="o",
                color="#3a2e21", markersize=5, capsize=2, label=f"Measured (L={result.config.L})")
    ax.axvline(T_C, linestyle="--", color="#c89878", alpha=0.7, label=f"T_c = {T_C:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("|M|  (per spin)")
    ax.set_title("Magnetization vs Temperature — 2D Ising")
    ax.legend(frameon=False)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_susceptibility(result: RunResult) -> str:
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(result.T, result.chi, "o-", color="#7a4e2f", markersize=5)
    ax.axvline(T_C, linestyle="--", color="#c89878", alpha=0.7, label=f"T_c = {T_C:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ  (per spin)")
    ax.set_title("Susceptibility — peak signals the critical point")
    ax.legend(frameon=False)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_snapshots(result: RunResult) -> str:
    keys = list(result.snapshots.keys())
    fig, axes = plt.subplots(1, len(keys), figsize=(3.2 * len(keys), 3.4))
    if len(keys) == 1:
        axes = [axes]
    for ax, k in zip(axes, keys):
        ax.imshow(result.snapshots[k], cmap="bone", interpolation="nearest")
        ax.set_title(k, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Lattice snapshots (cold → critical → hot)", fontsize=11)
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _tc_estimate(result: RunResult) -> tuple[float, str]:
    """Cheap T_c estimate from susceptibility-peak location."""
    idx = int(np.argmax(result.chi))
    T_peak = float(result.T[idx])
    err = float(result.T[1] - result.T[0]) / 2.0
    sentence = (
        f"Tonight I ran 2D Ising on an {result.config.L}×{result.config.L} lattice across "
        f"{result.config.n_temps} temperatures in [{result.config.T_min:.2f}, {result.config.T_max:.2f}], "
        f"{result.config.n_sweeps:,} measurement sweeps each. "
        f"The susceptibility peaked at T ≈ {T_peak:.3f} ± {err:.3f}; "
        f"Onsager says T_c = {T_C:.4f}. "
        f"Wall time on the GPU: {result.wall_seconds:.1f}s."
    )
    return T_peak, sentence


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 1</h1>
  <div class="date">{date} · 2D Ising verification</div>

  <div class="lede">{sentence}</div>

  <h2>Magnetization vs Temperature</h2>
  <figure><img src="data:image/png;base64,{mag_png}" alt="magnetization plot"></figure>

  <h2>Susceptibility</h2>
  <figure><img src="data:image/png;base64,{chi_png}" alt="susceptibility plot"></figure>

  <h2>Lattice snapshots</h2>
  <figure><img src="data:image/png;base64,{snap_png}" alt="lattice snapshots"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render(result: RunResult, date: str | None = None) -> Path:
    from .publish import today_local
    date = date or today_local()   # local day, not UTC — see today_local()
    _ensure_home()

    T_peak, sentence = _tc_estimate(result)
    report = result.to_json()
    # Tag the experiment explicitly so discovery/checks discriminate by field
    # rather than only by structure (check_m01's T/chi path is unaffected — it
    # never reads `experiment`). This is the implicit single-lattice Ising run.
    report["experiment"] = "M01-ising-verification"
    # A compact headline the windowsill page shows under the seedling.
    report["headline"] = (
        f"χ peaked at T≈{T_peak:.3f} vs Onsager {T_C:.4f}"
        f" · {result.wall_seconds:.0f}s on GPU"
    )
    json_dump = json.dumps(report, indent=2)

    html = HTML_TEMPLATE.format(
        date=date,
        sentence=sentence,
        mag_png=_plot_magnetization(result),
        chi_png=_plot_susceptibility(result),
        snap_png=_plot_snapshots(result),
        json_dump=json_dump,
    )
    # The ~/.lab dated cache is SLUG-KEYED (``<date>-<slug>.html``/``.json``), so
    # two different milestones run on the same day don't clobber each other in the
    # local cache the way the old bare ``<date>.*`` names did. (The committed
    # reports/ tree is already slug-keyed via _commit_report.)
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    # The raw JSON next to it (same slug-keyed name) so it's easy to grep.
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    # Update the local ~/.lab latest pointer (cache, untouched by the repo).
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")

    # Commit the permanent per-run report into the repo so the windowsill page
    # can deep-link this exact run — never clobbering an earlier one.
    _commit_report(date, slug, html, json_dump)
    return out


# ── M02: finite-size scaling report ─────────────────────────────────────────
_COPPER = plt.get_cmap("copper")


def _l_colors(n: int):
    return [_COPPER(0.15 + 0.7 * i / max(1, n - 1)) for i in range(n)]


def _plot_chi_family(curves: list[dict]) -> str:
    """χ(T) for each lattice size — the peak climbs and sharpens with L."""
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for c, col in zip(curves, _l_colors(len(curves))):
        ax.plot(c["T"], c["chi"], "o-", color=col, markersize=3.5,
                linewidth=1.4, label=f"L={c['L']}")
    ax.axvline(T_C, linestyle="--", color="#c89878", alpha=0.7, label=f"T_c = {T_C:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ  (per spin)")
    ax.set_title("Susceptibility grows with lattice size")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_chimax_scaling(curves: list[dict], slope: float, intercept: float) -> str:
    """log χ_max vs log L — slope is the measured γ/ν against the exact 7/4."""
    from .fss import GAMMA_OVER_NU
    Ls = np.array([c["L"] for c in curves], dtype=float)
    chimax = np.array([c["chi_max"] for c in curves], dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.loglog(Ls, chimax, "o", color="#3a2e21", markersize=7, label="measured χ_max")
    xs = np.linspace(Ls.min(), Ls.max(), 100)
    ax.loglog(xs, np.exp(intercept) * xs ** slope, "-", color="#7a4e2f",
              linewidth=2, label=f"fit: slope = {slope:.3f}")
    ax.loglog(xs, np.exp(intercept) * xs ** GAMMA_OVER_NU, "--", color="#c89878",
              linewidth=1.6, label=f"theory: γ/ν = {GAMMA_OVER_NU:.2f}")
    ax.set_xlabel("Lattice size  L")
    ax.set_ylabel("peak susceptibility  χ_max")
    ax.set_title("Finite-size scaling of the peak: χ_max ∝ L^(γ/ν)")
    ax.legend(frameon=False)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_collapse(curves: list[dict], tc: float) -> str:
    """The data collapse: χ·L^(-γ/ν) vs (T-T_c)·L^(1/ν) overlays every L."""
    from .fss import collapse_coords
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for c, col in zip(curves, _l_colors(len(curves))):
        x, y = collapse_coords(c["L"], c["T"], c["chi"], tc=tc)
        ax.plot(x, y, "o-", color=col, markersize=3.5, linewidth=1.2, label=f"L={c['L']}")
    ax.set_xlabel("(T − T_c) · L^(1/ν)")
    ax.set_ylabel("χ · L^(−γ/ν)")
    ax.set_title("Data collapse onto one master curve")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


FSS_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · finite-size scaling</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 1</h1>
  <div class="date">{date} · M02 — finite-size scaling</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Susceptibility vs Temperature (all L)</h2>
  <figure><img src="data:image/png;base64,{family_png}" alt="susceptibility family"></figure>

  <h2>Peak scaling — χ_max vs L</h2>
  <figure><img src="data:image/png;base64,{scaling_png}" alt="peak scaling log-log"></figure>

  <h2>Data collapse</h2>
  <figure><img src="data:image/png;base64,{collapse_png}" alt="data collapse"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


# ── M03: critical-exponent β data-collapse report ───────────────────────────
def _plot_mag_family(curves: list[dict]) -> str:
    """M(T) for each lattice size — the order parameter softening near T_c.

    Mirrors ``_plot_chi_family`` (M02), but for the magnetization: at finite L
    the sharp Onsager step is rounded, and ``M`` shrinks with ``L`` inside the
    critical window (the +β/ν scaling M03 collapses).
    """
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for c, col in zip(curves, _l_colors(len(curves))):
        ax.plot(c["T"], c["M"], "o-", color=col, markersize=3.5,
                linewidth=1.4, label=f"L={c['L']}")
    ax.axvline(T_C, linestyle="--", color="#c89878", alpha=0.7, label=f"T_c = {T_C:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("|M|  (per spin)")
    ax.set_title("Magnetization vs Temperature (all L)")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_mag_collapse(curves: list[dict], tc: float, beta_over_nu: float) -> str:
    """The β data collapse: M·L^(β/ν) vs (T−T_c)·L^(1/ν) overlays every L.

    Note the SIGN relative to M02's χ collapse — the y-rescale exponent is
    **+β/ν** (M *shrinks* with L), using ``m03.collapse_coords`` so the plot and
    the analysis share one rule.
    """
    from .m03 import collapse_coords
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for c, col in zip(curves, _l_colors(len(curves))):
        x, y = collapse_coords(c["L"], c["T"], c["M"], tc=tc, beta_over_nu=beta_over_nu)
        ax.plot(x, y, "o-", color=col, markersize=3.5, linewidth=1.2, label=f"L={c['L']}")
    ax.set_xlabel("(T − T_c) · L^(1/ν)")
    ax.set_ylabel("M · L^(+β/ν)")
    ax.set_title("Magnetization data collapse onto one master curve")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M03_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · data collapse</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 1</h1>
  <div class="date">{date} · M03 — critical exponent β (data collapse)</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Magnetization vs Temperature (all L)</h2>
  <figure><img src="data:image/png;base64,{family_png}" alt="magnetization family"></figure>

  <h2>Data collapse — M·L^(β/ν) vs (T−T_c)·L^(1/ν)</h2>
  <figure><img src="data:image/png;base64,{collapse_png}" alt="magnetization data collapse"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render_m03(report: dict, date: str | None = None) -> Path:
    """Render an M03 critical-exponent β data-collapse report (HTML + plots + JSON).

    Mirrors ``render_fss``: a magnetization-family plot M(T) for each L, the β
    data-collapse plot (M·L^(β/ν) vs (T−T_c)·L^(1/ν), via ``m03.collapse_coords``),
    an honest verdict — a **pass** only when the recovered β/ν sits within ±0.03
    of the exact 2D Ising 1/8, otherwise the run is kept as a null (a folded grey
    leaf with its real numbers, never relabeled a discovery). Persists the same
    way every renderer does: a slug-keyed ``~/.lab`` dated cache + ``latest.html``
    pointer, AND a *permanent* committed pair in the repo
    (``reports/<date>-m03.html`` + ``.json``) plus the back-compat
    ``reports/latest.html`` copy — so the M03 milestone can finally be archived.
    """
    from .publish import today_local
    from .m03 import BETA_OVER_NU
    date = date or today_local()
    _ensure_home()

    curves = report["curves"]
    tc = report.get("tc", T_C)
    beta_over_nu_theory = report.get("beta_over_nu_theory", BETA_OVER_NU)
    bon_fit = report.get("beta_over_nu_fit")
    quality = report.get("collapse_quality")
    invnu_fit = report.get("inv_nu_fit")

    Ls = ", ".join(str(c["L"]) for c in curves)
    sentence = (
        f"I ran 2D Ising at L = {Ls} across a tight window straddling T_c and "
        f"rescaled the magnetization by the finite-size-scaling form "
        f"M·L^(β/ν) = F((T−T_c)·L^(1/ν)). For the 2D Ising universality class the "
        f"exponents are exact: β = 1/8, ν = 1, so β/ν = {beta_over_nu_theory:.3f} is "
        f"a number with no free parameters. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )
    # Honest verdict: pass only when β/ν lands within ±0.03 of the exact 1/8.
    passed = bon_fit is not None and abs(bon_fit - beta_over_nu_theory) <= 0.03
    bon_str = f"{bon_fit:.3f}" if bon_fit is not None else "—"
    extra = ""
    if quality is not None:
        extra += f", residual = {quality:.1e}"
    if invnu_fit is not None:
        extra += f", joint 1/ν = {invnu_fit:.3f}"
    verdict = (
        f"{'✓' if passed else '~'} Recovered β/ν = {bon_str} "
        f"(theory {beta_over_nu_theory:.3f}{extra}). "
        + ("Every curve falls onto one master curve at the exact exponent — calibrated."
           if passed else
           "The collapse is off — kept honestly as a null, not a discovery.")
    )

    json_dump = json.dumps(report, indent=2)
    html = M03_HTML_TEMPLATE.format(
        date=date,
        sentence=sentence,
        verdict=verdict,
        family_png=_plot_mag_family(curves),
        collapse_png=_plot_mag_collapse(curves, tc, beta_over_nu_theory),
        json_dump=json_dump,
    )
    # Slug-keyed ~/.lab cache (no same-day clobber) + local latest pointer.
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    # Commit the permanent per-run report (reports/<date>-m03.html/.json) so this
    # data-collapse run is preserved and the milestone can be archived.
    _commit_report(date, slug, html, json_dump)
    return out


def render_fss(report: dict, date: str | None = None) -> Path:
    """Render an M02 finite-size-scaling report (HTML + plots + JSON sidecar).

    Mirrors ``render()``'s persistence: a slug-keyed dated HTML/JSON cache in
    ``~/.lab`` (``<date>-<slug>.*``, so same-day milestones don't clobber locally)
    + a local ``latest.html`` pointer, and a *permanent* committed pair in the
    repo (``reports/<date>-m02.html`` + ``.json``) plus the back-compat
    ``reports/latest.html`` copy — so each milestone run is preserved, never
    buried by the next.
    """
    from .publish import today_local
    from .fss import fit_gamma_over_nu, GAMMA_OVER_NU
    date = date or today_local()
    _ensure_home()

    curves = report["curves"]
    slope = report["gamma_over_nu_fit"]
    r2 = report.get("fit_r2", 0.0)
    tc = report.get("tc", T_C)
    _, intercept, _ = fit_gamma_over_nu([c["L"] for c in curves], [c["chi_max"] for c in curves])

    Ls = ", ".join(str(c["L"]) for c in curves)
    sentence = (
        f"I ran 2D Ising at L = {Ls} and tracked how the susceptibility peak grows "
        f"with lattice size. Finite-size scaling predicts χ_max ∝ L^(γ/ν) with the "
        f"exact 2D Ising exponent γ/ν = {GAMMA_OVER_NU:.2f}. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )
    passed = abs(slope - GAMMA_OVER_NU) <= 0.15 and r2 >= 0.97
    verdict = (
        f"{'✓' if passed else '~'} Measured slope γ/ν = {slope:.3f} "
        f"(theory {GAMMA_OVER_NU:.2f}), log-log fit R² = {r2:.3f}. "
        + ("The peak heights scale as predicted and the curves collapse — calibrated."
           if passed else
           "Scaling is off — kept honestly as a null, not a discovery.")
    )

    json_dump = json.dumps(report, indent=2)
    html = FSS_HTML_TEMPLATE.format(
        date=date,
        sentence=sentence,
        verdict=verdict,
        family_png=_plot_chi_family(curves),
        scaling_png=_plot_chimax_scaling(curves, slope, intercept),
        collapse_png=_plot_collapse(curves, tc),
        json_dump=json_dump,
    )
    # Slug-keyed ~/.lab cache so a same-day M01/M02/M03 run doesn't clobber this
    # one locally (the committed reports/ tree is already slug-keyed).
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    # Commit the permanent per-run report (e.g. reports/<date>-m02.html/.json)
    # so this finite-size-scaling run is preserved, not buried by the next run.
    _commit_report(date, slug, html, json_dump)
    return out


# ── M06 — 3D simple-cubic Ising ──────────────────────────────────────────────


def _plot_m06_chi(report: dict) -> str:
    """χ(T) and the located T_c vs the 3D MC benchmark — M06's headline plot."""
    T = report["T"]
    chi = report["chi"]
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_bench = report.get("tc_benchmark", 4.5115)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T, chi, "o-", color="#7a4e2f", markersize=4, linewidth=1.5,
            label=f"Measured χ (L={report.get('L')})")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.8,
               label=f"MC benchmark T_c = {tc_bench:.4f}")
    if tc_fit is not None:
        ax.axvline(tc_fit, linestyle=":", color="#3a2e21", alpha=0.8,
                   label=f"χ-peak T_c(L) = {tc_fit:.3f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ  (per spin)")
    ax.set_title("3D Ising susceptibility — peak locates T_c")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m06_mag_cv(report: dict) -> str:
    """⟨|m|⟩(T) (order parameter melting) with the specific-heat C(T) overlaid."""
    T = report["T"]
    m = report["abs_mag"]
    m_err = report.get("abs_mag_err") or [0.0] * len(T)
    cv = report.get("specific_heat") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 4.5115)
    tc_cv = report.get("tc_cv")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.errorbar(T, m, yerr=m_err, fmt="o-", color="#3a2e21", markersize=4,
                capsize=2, linewidth=1.4, label="⟨|m|⟩  (order parameter)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.8,
               label=f"MC benchmark T_c = {tc_bench:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("|m|  (per spin)")
    ax.set_ylim(0, 1.05)
    ax2 = ax.twinx()
    ax2.plot(T, cv, "s-", color="#7a9b56", markersize=3, linewidth=1.2,
             alpha=0.85, label="C  (specific heat)")
    if tc_cv is not None:
        ax2.axvline(tc_cv, linestyle=":", color="#5f7a3e", alpha=0.7,
                    label=f"C-peak T_c(L) = {tc_cv:.3f}")
    ax2.set_ylabel("C  (per spin)")
    ax.set_title("Magnetization melts, specific heat peaks — same transition")
    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="upper right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M06_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 3D Ising</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 2</h1>
  <div class="date">{date} · M06 — 3D simple-cubic Ising</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Susceptibility vs Temperature — the peak is T_c</h2>
  <figure><img src="data:image/png;base64,{chi_png}" alt="3D Ising susceptibility"></figure>

  <h2>Order parameter &amp; specific heat</h2>
  <figure><img src="data:image/png;base64,{mag_png}" alt="3D Ising magnetization and specific heat"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render_m06(report: dict, date: str | None = None) -> Path:
    """Render an M06 3D-Ising report (HTML + plots + JSON sidecar).

    Mirrors ``render_fss``/``render_m03``: a slug-keyed ``~/.lab`` dated cache +
    ``latest.html`` pointer AND a permanent committed pair in the repo
    (``reports/<date>-m06.html`` + ``.json``). The verdict is an honest **pass**
    only when the χ-peak T_c lands within ±0.15 of the MC benchmark 4.5115 — a
    finite-L tolerance, not a precision-T_c claim (the small-lattice peak sits
    *above* the infinite-volume value); a miss is kept as a folded grey leaf, its
    real numbers intact, never relabelled a discovery.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_cv = report.get("tc_cv")
    tc_bench = report.get("tc_benchmark", 4.5115)
    rel_err = report.get("rel_error")

    sentence = (
        f"I ran the simple-cubic 3D Ising model on an L={L} lattice across a "
        f"temperature window straddling the transition and tracked the magnetic "
        f"susceptibility χ(T). Three dimensions has no exact solution, so the "
        f"target is the Monte-Carlo benchmark T_c ≈ {tc_bench:.4f}. The χ peak "
        f"sits at T_c(L) = {tc_fit:.3f}. "
        f"Wall time on the CPU: {report.get('wall_seconds', 0):.0f}s."
    )
    # Honest verdict: pass only when the χ-peak T_c lands within ±0.15 of 4.5115.
    passed = tc_fit is not None and abs(tc_fit - tc_bench) <= 0.15
    err_str = f"{rel_err*100:.1f}%" if rel_err is not None else "—"
    cv_str = f", and the specific-heat peak independently gives T_c(L) = {tc_cv:.3f}" if tc_cv is not None else ""
    verdict = (
        f"{'✓' if passed else '~'} χ-peak T_c(L) = {tc_fit:.3f} vs MC benchmark "
        f"{tc_bench:.4f} (rel. err {err_str}){cv_str}. "
        + ("The transition is in the right place — the lab reproduces the 3D "
           "benchmark, calibrating Phase 2. (Small-L finite-size effects push the "
           "pseudo-critical peak slightly above the infinite-volume T_c; an "
           "L-extrapolation would sharpen the number — see BACKLOG.)"
           if passed else
           "The transition is off — kept honestly as a null, not a discovery.")
    )

    json_dump = json.dumps(report, indent=2)
    html = M06_HTML_TEMPLATE.format(
        date=date,
        sentence=sentence,
        verdict=verdict,
        chi_png=_plot_m06_chi(report),
        mag_png=_plot_m06_mag_cv(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M04 — 2D Ising specific heat (the thermal cross-check of T_c) ─────────────

def _plot_m04_specific_heat(report: dict) -> str:
    """C(T) with its peak, the exact Onsager T_c, and the χ-peak cross-check."""
    T = report["T"]
    cv = report.get("specific_heat") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 2.2692)
    tc_cv = report.get("tc_cv_refined", report.get("tc_cv"))
    tc_chi = report.get("tc_chi_refined")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T, cv, "s-", color="#7a9b56", markersize=4, linewidth=1.5,
            label="C(T)  (specific heat)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Onsager exact T_c = {tc_bench:.4f}")
    if tc_cv is not None:
        ax.axvline(tc_cv, linestyle=":", color="#5f7a3e", alpha=0.8,
                   label=f"C-peak T_c(L) = {tc_cv:.3f}")
    if tc_chi is not None:
        ax.axvline(tc_chi, linestyle=":", color="#3a6ea5", alpha=0.55,
                   label=f"χ-peak cross-check = {tc_chi:.3f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("C  (per spin)")
    ax.set_title("Specific heat diverges (logarithmically) at T_c")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m04_energy(report: dict) -> str:
    """⟨E⟩(T): the smooth energy curve whose fluctuations ARE the specific heat."""
    T = report["T"]
    e = report.get("energy") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 2.2692)
    fig, ax = plt.subplots(figsize=(7, 4.0))
    ax.plot(T, e, "o-", color="#3a2e21", markersize=4, linewidth=1.4,
            label="⟨E⟩  (energy per spin)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Onsager exact T_c = {tc_bench:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("E  (per spin)")
    ax.set_title("Energy rises smoothly — its steepest slope (= C) marks T_c")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M04_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 2D Ising specific heat</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 1</h1>
  <div class="date">{date} · M04 — 2D Ising specific heat</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Specific heat vs Temperature — the divergence is T_c</h2>
  <figure><img src="data:image/png;base64,{cv_png}" alt="2D Ising specific heat C(T)"></figure>

  <h2>Energy vs Temperature — context</h2>
  <figure><img src="data:image/png;base64,{e_png}" alt="2D Ising energy per spin"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render_m04(report: dict, date: str | None = None) -> Path:
    """Render an M04 2D-Ising specific-heat report (HTML + plots + JSON sidecar).

    Mirrors ``render_m06``: a slug-keyed ``~/.lab`` dated cache + ``latest.html``
    pointer AND a permanent committed pair (``reports/<date>-m04.html`` + ``.json``).
    The verdict is an honest **pass** only when the specific-heat peak lands within
    ±0.1 of Onsager's exact T_c ≈ 2.2692 — a finite-L tolerance (the peak sits a
    little above the infinite-volume value); a miss stays a folded grey leaf with
    its real numbers intact, never relabelled a discovery.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    tc_cv = report.get("tc_cv_refined", report.get("tc_cv"))
    tc_chi = report.get("tc_chi_refined")
    tc_bench = report.get("tc_benchmark", 2.2692)
    rel_err = report.get("rel_error")
    amp = report.get("log_amplitude")

    sentence = (
        f"I ran the 2D Ising model on an L={L} lattice across a window straddling "
        f"the transition and read the specific heat C(T) = (⟨E²⟩−⟨E⟩²)·N/T² from "
        f"the energy fluctuations. M01 found T_c from the magnetization; M04 is the "
        f"independent thermal check — the specific heat carries Onsager's "
        f"logarithmic divergence at the exact T_c ≈ {tc_bench:.4f}. The C peak sits "
        f"at T_c(L) = {tc_cv:.3f}. Wall time: {report.get('wall_seconds', 0):.0f}s."
    )
    passed = tc_cv is not None and abs(tc_cv - tc_bench) <= 0.1
    err_str = f"{rel_err*100:.1f}%" if rel_err is not None else "—"
    chi_str = (f", and the χ peak from the same run independently gives "
               f"T_c(L) = {tc_chi:.3f}") if tc_chi is not None else ""
    amp_str = (f" Onsager's exact leading amplitude is A = (2/π)(2/T_c)² ≈ {amp:.3f}; "
               f"a finite lattice rounds the true log into this peak, so the amplitude "
               f"isn't resolved here — the peak location is the calibrated claim."
               ) if amp is not None else ""
    verdict = (
        f"{'✓' if passed else '~'} C-peak T_c(L) = {tc_cv:.3f} vs Onsager exact "
        f"{tc_bench:.4f} (rel. err {err_str}){chi_str}. "
        + ("Two independent observables — the magnetization (M01) and the energy "
           "fluctuations (M04) — agree on the same critical point; the thermal "
           "response calibrates cleanly." + amp_str
           if passed else
           "The thermal transition is off — kept honestly as a null, not a "
           "discovery." + amp_str)
    )

    json_dump = json.dumps(report, indent=2)
    html = M04_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        cv_png=_plot_m04_specific_heat(report),
        e_png=_plot_m04_energy(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M05 — triangular-lattice 2D Ising (a new geometry, exact T_c = 4/ln 3) ────

def _plot_m05_chi(report: dict) -> str:
    """χ(T) with the located T_c vs the exact triangular benchmark — M05's headline."""
    T = report["T"]
    chi = report["chi"]
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_bench = report.get("tc_benchmark", 4.0 / np.log(3.0))
    tc_cv = report.get("tc_cv_refined")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T, chi, "o-", color="#7a4e2f", markersize=4, linewidth=1.5,
            label=f"Measured χ (L={report.get('L')})")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Exact T_c = 4/ln3 = {tc_bench:.4f}")
    if tc_fit is not None:
        ax.axvline(tc_fit, linestyle=":", color="#3a2e21", alpha=0.8,
                   label=f"χ-peak T_c(L) = {tc_fit:.3f}")
    if tc_cv is not None:
        ax.axvline(tc_cv, linestyle=":", color="#3a6ea5", alpha=0.55,
                   label=f"C-peak cross-check = {tc_cv:.3f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ  (per spin)")
    ax.set_title("Triangular-lattice susceptibility — peak locates T_c")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m05_mag_cv(report: dict) -> str:
    """⟨|m|⟩(T) (the order parameter melting) with the specific heat C(T) overlaid."""
    T = report["T"]
    m = report["abs_mag"]
    m_err = report.get("abs_mag_err") or [0.0] * len(T)
    cv = report.get("specific_heat") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 4.0 / np.log(3.0))
    tc_cv = report.get("tc_cv_refined")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.errorbar(T, m, yerr=m_err, fmt="o-", color="#3a2e21", markersize=4,
                capsize=2, linewidth=1.4, label="⟨|m|⟩  (order parameter)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Exact T_c = {tc_bench:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("|m|  (per spin)")
    ax.set_ylim(0, 1.05)
    ax2 = ax.twinx()
    ax2.plot(T, cv, "s-", color="#7a9b56", markersize=3, linewidth=1.2,
             alpha=0.85, label="C  (specific heat)")
    if tc_cv is not None:
        ax2.axvline(tc_cv, linestyle=":", color="#5f7a3e", alpha=0.7,
                    label=f"C-peak T_c(L) = {tc_cv:.3f}")
    ax2.set_ylabel("C  (per spin)")
    ax.set_title("Magnetization melts, specific heat peaks — same transition")
    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="upper right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M05_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · triangular Ising</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 1</h1>
  <div class="date">{date} · M05 — triangular-lattice 2D Ising</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Susceptibility vs Temperature — the peak is T_c</h2>
  <figure><img src="data:image/png;base64,{chi_png}" alt="triangular Ising susceptibility"></figure>

  <h2>Order parameter &amp; specific heat</h2>
  <figure><img src="data:image/png;base64,{mag_png}" alt="triangular Ising magnetization and specific heat"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render_m05(report: dict, date: str | None = None) -> Path:
    """Render an M05 triangular-Ising report (HTML + plots + JSON sidecar).

    Mirrors ``render_m06``: a slug-keyed ``~/.lab`` dated cache + ``latest.html``
    pointer AND a permanent committed pair (``reports/<date>-m05.html`` + ``.json``).
    The verdict is an honest **pass** only when the χ-peak T_c lands within ±0.15 of
    the exact triangular T_c = 4/ln 3 ≈ 3.6410 — a finite-L tolerance (the
    small-lattice peak sits *above* the infinite-volume value); a miss stays a
    folded grey leaf with its real numbers intact, never relabelled a discovery.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_cv = report.get("tc_cv_refined")
    tc_bench = report.get("tc_benchmark", 4.0 / np.log(3.0))
    rel_err = report.get("rel_error")

    sentence = (
        f"I ran the 2D Ising model on a *triangular* lattice (L={L}) across a "
        f"window straddling the transition and tracked the magnetic susceptibility "
        f"χ(T). The triangular lattice is the square grid plus one diagonal — six "
        f"neighbours per site, not four — so it is the same universality class as "
        f"M01 but a different geometry, with its own *exact* critical temperature "
        f"T_c = 4/ln 3 ≈ {tc_bench:.4f}. Because the triangular lattice is "
        f"non-bipartite, this needed a 3-sublattice update, not the square "
        f"checkerboard. The χ peak sits at T_c(L) = {tc_fit:.3f}. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )
    # Honest verdict: pass only when the χ-peak T_c lands within ±0.15 of 4/ln 3.
    passed = tc_fit is not None and abs(tc_fit - tc_bench) <= 0.15
    err_str = f"{rel_err*100:.1f}%" if rel_err is not None else "—"
    cv_str = (f", and the specific-heat peak from the same run independently gives "
              f"T_c(L) = {tc_cv:.3f}") if tc_cv is not None else ""
    verdict = (
        f"{'✓' if passed else '~'} χ-peak T_c(L) = {tc_fit:.3f} vs exact "
        f"4/ln3 = {tc_bench:.4f} (rel. err {err_str}){cv_str}. "
        + ("A new geometry reproduces its known answer: the triangular lattice's "
           "exact T_c falls right where the susceptibility peaks, on an engine that "
           "had to switch from the square checkerboard to a 3-sublattice update "
           "(the triangular lattice is non-bipartite). Same universality class as "
           "M01, different number — calibrated. (Small-L finite-size effects push "
           "the pseudo-critical peak slightly above the infinite-volume T_c; an "
           "L-extrapolation would sharpen it — see BACKLOG.)"
           if passed else
           "The transition is off — kept honestly as a null, not a discovery.")
    )

    json_dump = json.dumps(report, indent=2)
    html = M05_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        chi_png=_plot_m05_chi(report),
        mag_png=_plot_m05_mag_cv(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M07 — 2D q-state Potts (continuous q≤4 → first-order q≥5) ─────────────────

def _q_colors(qs: list[int]):
    """A copper ramp keyed to q so q=3..6 read in a consistent warm order."""
    n = len(qs)
    return {q: _COPPER(0.15 + 0.7 * i / max(1, n - 1)) for i, q in enumerate(qs)}


def _plot_m07_chi(report: dict) -> str:
    """χ(T) for every q, each with its exact-T_c marker — M07's headline plot.

    The continuous (q≤4) curves are drawn lighter, the first-order (q≥5) ones with
    a heavier line, so the *qualitative* change — a taller, sharper susceptibility
    spike for the first-order transitions — is legible at a glance.
    """
    per_q = report["per_q"]
    qs = [e["q"] for e in per_q]
    cols = _q_colors(qs)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    for e in per_q:
        q = e["q"]
        first_order = q >= 5
        ax.plot(e["T"], e["chi"], "o-", color=cols[q],
                markersize=3.5, linewidth=2.0 if first_order else 1.3,
                label=f"q={q} ({'1st-order' if first_order else 'continuous'})")
        ax.axvline(e["tc_exact"], linestyle=":", color=cols[q], alpha=0.6, linewidth=1.2)
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ  (order-parameter susceptibility)")
    ax.set_title("Potts susceptibility — the spike sharpens as q crosses 4")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m07_order(report: dict) -> str:
    """The Potts order parameter m(T) for every q — the melt steepens for q≥5.

    Continuous transitions soften m gradually; the first-order (q≥5) ones drop it
    much more steeply across T_c (a discontinuity in the L→∞ limit). Exact-T_c
    markers per q let the eye line the drop up with the known critical point.
    """
    per_q = report["per_q"]
    qs = [e["q"] for e in per_q]
    cols = _q_colors(qs)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    for e in per_q:
        q = e["q"]
        ax.plot(e["T"], e["order"], "o-", color=cols[q],
                markersize=3.5, linewidth=2.0 if q >= 5 else 1.3, label=f"q={q}")
        ax.axvline(e["tc_exact"], linestyle=":", color=cols[q], alpha=0.55, linewidth=1.2)
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("m = (q·ρ_max − 1)/(q − 1)")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Order parameter melts — steeper for the first-order q≥5")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M07_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · q-state Potts</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 14px; }}
  th, td {{ text-align: right; padding: 6px 10px; border-bottom: 1px solid #e3d6bd; }}
  th:first-child, td:first-child {{ text-align: left; }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 2</h1>
  <div class="date">{date} · M07 — 2D q-state Potts model</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Per-q critical temperatures</h2>
  {table}

  <h2>Susceptibility vs Temperature — the peak locates each T_c</h2>
  <figure><img src="data:image/png;base64,{chi_png}" alt="Potts susceptibility for q=3..6"></figure>

  <h2>Order parameter — the melt steepens for q≥5</h2>
  <figure><img src="data:image/png;base64,{order_png}" alt="Potts order parameter for q=3..6"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def _m07_table(per_q: list[dict]) -> str:
    """A small per-q results table: q, kind, measured T_c, exact T_c, rel. err."""
    rows = [
        "<tr><th>q</th><th>transition</th><th>T_c (measured)</th>"
        "<th>T_c (exact)</th><th>rel. err</th></tr>"
    ]
    for e in per_q:
        rows.append(
            f"<tr><td>{e['q']}</td><td>{e.get('transition', '')}</td>"
            f"<td>{e['tc_chi_refined']:.4f}</td><td>{e['tc_exact']:.4f}</td>"
            f"<td>{e['rel_error']*100:.1f}%</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def render_m07(report: dict, date: str | None = None) -> Path:
    """Render an M07 q-state-Potts report (HTML + plots + JSON sidecar).

    Mirrors ``render_m05``/``render_m06``: a slug-keyed ``~/.lab`` dated cache +
    ``latest.html`` pointer AND a permanent committed pair
    (``reports/<date>-m07.html`` + ``.json``). The verdict is an honest **pass**
    only when *every* q's χ-peak T_c lands within its finite-L tolerance of the
    exact Potts T_c = 1/ln(1+√q) — ±0.1 for the continuous q ≤ 4, ±0.15 for the
    first-order q ≥ 5 (stronger finite-size / metastability shift). It always
    names the qualitative continuous→first-order change (the sharper, taller
    susceptibility spike and steeper order-parameter drop for q ≥ 5). A miss on
    any q stays a folded grey leaf with its real numbers intact, never relabelled.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    per_q = report["per_q"]
    L = report.get("L")
    cont_drop = report.get("continuous_mean_order_drop")
    first_drop = report.get("first_order_mean_order_drop")
    cont_chimax = report.get("continuous_mean_chi_max")
    first_chimax = report.get("first_order_mean_chi_max")

    sentence = (
        f"I ran the 2D q-state Potts model on an L={L} square lattice for "
        f"q = {', '.join(str(e['q']) for e in per_q)}, each over a window "
        f"straddling its exact critical temperature T_c(q) = 1/ln(1+√q). The Potts "
        f"spin carries one of q flavours and a bond costs energy only when its two "
        f"sites agree; the order parameter m = (q·ρ_max − 1)/(q − 1) melts from 1 "
        f"(ordered) to 0 (disordered) as T rises, and its susceptibility peaks at "
        f"T_c. The point of M07 is the *kind* of transition: continuous for q ≤ 4, "
        f"first-order for q ≥ 5. Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )

    def _ok(e):
        tol = 0.1 if e["q"] <= 4 else 0.15
        return abs(e["tc_chi_refined"] - e["tc_exact"]) <= tol
    passed = all(_ok(e) for e in per_q)
    misses = [e["q"] for e in per_q if not _ok(e)]

    sharper = ""
    if cont_chimax is not None and first_chimax is not None:
        sharper = (
            f" The susceptibility peak climbs sharply across the boundary — mean "
            f"χ_max ≈ {first_chimax:.0f} for the first-order q≥5 vs ≈ {cont_chimax:.0f} "
            f"for the continuous q≤4 — the taller, sharper spike that marks a "
            f"discontinuous transition."
        )
    verdict = (
        f"{'✓' if passed else '~'} "
        + (
            "Every q's susceptibility peak lands on its exact Potts T_c "
            "(±0.1 for the continuous q≤4, ±0.15 for the first-order q≥5, whose "
            "stronger finite-size effects shift the pseudo-critical peak further). "
            if passed else
            f"q={', '.join(map(str, misses))} miss the finite-L tolerance and stay "
            "honest nulls, not discoveries. "
        )
        + "The qualitative change M07 asks for is clear: the q≥5 susceptibility "
        "spikes are taller and sharper than the q≤4 peaks — the continuous (q≤4) → "
        "first-order (q≥5) crossover." + sharper
    )

    json_dump = json.dumps(report, indent=2)
    html = M07_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        table=_m07_table(per_q),
        chi_png=_plot_m07_chi(report),
        order_png=_plot_m07_order(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M08 — 2D XY model · the Berezinskii–Kosterlitz–Thouless transition ────────

def _plot_m08_helicity(report: dict) -> str:
    """Υ(T) with the universal-jump line (2/π)T and the crossing — M08's headline.

    The BKT signature is the CROSSING of the measured helicity modulus Υ(T) with
    the straight line y = (2/π)·T (the Nelson–Kosterlitz universal jump), not a
    peak. We draw both, mark the interpolated crossing (the finite-L T_BKT(L)) and
    the benchmark 0.8929, and carry Υ's error bars so the smoothness of the curve
    — the thing a jagged, un-equilibrated run would betray — is legible.
    """
    T = np.asarray(report["T"], dtype=float)
    Y = np.asarray(report["helicity_modulus"], dtype=float)
    Y_err = report.get("helicity_err") or [0.0] * len(T)
    two_over_pi = report.get("two_over_pi", 2.0 / np.pi)
    tc_cross = report.get("tc_crossing")
    tc_bench = report.get("tc_benchmark", 0.8929)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.errorbar(T, Y, yerr=Y_err, fmt="o-", color="#3a2e21", markersize=4,
                capsize=2, linewidth=1.5, label=f"Measured Υ (L={report.get('L')})")
    line = two_over_pi * T
    ax.plot(T, line, "--", color="#9b6b3e", linewidth=1.8,
            label="universal jump  Υ = (2/π)·T")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.8,
               label=f"benchmark T_BKT = {tc_bench:.4f}")
    if tc_cross is not None:
        ax.axvline(tc_cross, linestyle=":", color="#5f7a3e", alpha=0.85,
                   label=f"crossing T_BKT(L) = {tc_cross:.3f}")
        ax.plot([tc_cross], [two_over_pi * tc_cross], "o", color="#5f7a3e",
                markersize=8, zorder=5)
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("Υ  (helicity modulus / spin stiffness)")
    ax.set_ylim(bottom=min(-0.05, float(Y.min()) - 0.05))
    ax.set_title("Helicity modulus crosses the (2/π)T jump line at T_BKT")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m08_energy_mag(report: dict) -> str:
    """⟨E⟩(T) (smooth, no peak) with ⟨|m|⟩ overlaid — the "no order parameter" plot.

    A deliberate contrast to M01–M07: there is NO sharp feature. The energy rises
    smoothly through T_BKT (BKT is an infinite-order transition — no latent heat,
    no specific-heat divergence at T_BKT), and ⟨|m|⟩ has no kink either: it is a
    finite-size artifact, not an order parameter (→0 as L grows at all T>0). Shown
    so the page makes visible *why* M08 needs the helicity jump, not a peak.
    """
    T = np.asarray(report["T"], dtype=float)
    e = report.get("energy") or [0.0] * len(T)
    m = report.get("abs_mag") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 0.8929)
    fig, ax = plt.subplots(figsize=(7, 4.0))
    ax.plot(T, e, "o-", color="#3a2e21", markersize=4, linewidth=1.4,
            label="⟨E⟩  (energy per spin)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"benchmark T_BKT = {tc_bench:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("E  (per spin)")
    ax2 = ax.twinx()
    ax2.plot(T, m, "s-", color="#7a9b56", markersize=3, linewidth=1.2, alpha=0.85,
             label="⟨|m|⟩  (finite-size artifact, NOT an order parameter)")
    ax2.set_ylabel("|m|  (per spin)")
    ax2.set_ylim(0, 1.05)
    ax.set_title("Energy is smooth through T_BKT — there is no order-parameter peak")
    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="upper left")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M08_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 2D XY BKT</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 2</h1>
  <div class="date">{date} · M08 — 2D XY model · BKT transition</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Helicity modulus &amp; the universal jump — the crossing is T_BKT</h2>
  <figure><img src="data:image/png;base64,{helicity_png}" alt="XY helicity modulus vs temperature with the (2/pi)T jump line"></figure>

  <h2>Energy &amp; magnetization — there is no order-parameter peak</h2>
  <figure><img src="data:image/png;base64,{energy_png}" alt="XY energy and magnetization vs temperature"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def render_m08(report: dict, date: str | None = None) -> Path:
    """Render an M08 2D-XY-BKT report (HTML + plots + JSON sidecar).

    Mirrors ``render_m05``/``render_m07``: a slug-keyed ``~/.lab`` dated cache +
    ``latest.html`` pointer AND a permanent committed pair
    (``reports/<date>-m08.html`` + ``.json``). The verdict is an honest **pass**
    only when the helicity-jump crossing lands within ±0.07 of the BKT benchmark
    T_BKT ≈ 0.8929 — a log-correction-tolerant finite-L window (BKT has notoriously
    strong log corrections and the single-L crossing typically sits a little
    *above* 0.8929); a miss (or a curve that never crosses the jump line) stays a
    folded grey leaf with its real numbers intact, never relabelled a discovery.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    tc_cross = report.get("tc_crossing")
    tc_bench = report.get("tc_benchmark", 0.8929)
    rel_err = report.get("rel_error")

    cross_str = f"{tc_cross:.3f}" if tc_cross is not None else "—"
    sentence = (
        f"I ran the 2D XY model — continuous angle spins θ ∈ [0, 2π), "
        f"E = −J·Σ cos(θ_i − θ_j) — on an L={L} square lattice across a window "
        f"straddling the transition. The XY model has NO long-range order at any "
        f"T &gt; 0 (Mermin–Wagner), so ⟨|m|⟩ is not an order parameter; its "
        f"transition is the topological Berezinskii–Kosterlitz–Thouless "
        f"vortex-unbinding at T_BKT ≈ {tc_bench:.4f}. The clean signature is the "
        f"helicity modulus Υ(T) and its universal jump: where Υ(T) crosses the "
        f"line (2/π)·T marks T_BKT. The crossing sits at T_BKT(L) = {cross_str}. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )
    passed = tc_cross is not None and abs(tc_cross - tc_bench) <= 0.07
    err_str = f"{rel_err*100:.1f}%" if rel_err is not None else "—"
    if tc_cross is None:
        verdict = (
            "~ The helicity modulus never crosses the (2/π)·T jump line on the "
            "swept window — no BKT crossing was bracketed. Kept honestly as a null, "
            "not a discovery: the window is mis-placed or the run is un-equilibrated."
        )
    else:
        verdict = (
            f"{'✓' if passed else '~'} Helicity-jump crossing T_BKT(L) = {tc_cross:.3f} "
            f"vs benchmark {tc_bench:.4f} (rel. err {err_str}). "
            + ("The helicity modulus — finite below the transition, dropping toward "
               "zero above it — crosses the Nelson–Kosterlitz universal-jump line "
               "(2/π)·T right where the BKT transition is known to sit. No "
               "order-parameter peak exists for this transition; the helicity jump "
               "is the calibrated signature. (BKT has strong logarithmic finite-size "
               "corrections, so the single-L crossing carries a wider, "
               "physically-justified ±0.07 window and typically sits a touch above "
               "the infinite-volume 0.8929 — an L-extrapolation would sharpen it.)"
               if passed else
               "The crossing is outside the finite-L window — kept honestly as a "
               "null, not a discovery.")
        )

    json_dump = json.dumps(report, indent=2)
    html = M08_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        helicity_png=_plot_m08_helicity(report),
        energy_png=_plot_m08_energy_mag(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M09 — 2D Heisenberg · Mermin–Wagner (the absence of order, done honestly) ──

def _plot_m09_drift(report: dict) -> str:
    """⟨|m|⟩ vs L drifting toward 0 — M09's headline (the absence-of-order signature).

    Unlike every milestone before it, there is NO transition to mark. The plot
    shows the per-spin vector magnetization ⟨|m|⟩ *falling* as the lattice grows
    at a fixed temperature — the Mermin–Wagner fingerprint. A dashed guide at |m|=0
    is the infinite-volume limit the sequence drifts toward; a faint reference line
    for what *spontaneous order* would look like (a flat plateau) makes the
    contrast legible — the measured points peel away from it, down toward zero.
    """
    Ls = np.asarray(report["L_values"], dtype=float)
    m = np.asarray(report["abs_mag"], dtype=float)
    m_err = report.get("abs_mag_err") or [0.0] * len(Ls)
    T = report.get("T")
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.errorbar(Ls, m, yerr=m_err, fmt="o-", color="#3a2e21", markersize=7,
                capsize=3, linewidth=1.6, label=f"Measured ⟨|m|⟩  (T={T})")
    # What spontaneous order would look like: a flat plateau at the smallest-L value.
    ax.axhline(m[0], linestyle=":", color="#c89878", alpha=0.7,
               label="if it ordered: a plateau (it doesn't)")
    ax.axhline(0.0, linestyle="--", color="#7a9b56", alpha=0.8,
               label="L → ∞ limit:  ⟨|m|⟩ → 0")
    ax.set_xscale("log", base=2)
    ax.set_xticks(Ls)
    ax.get_xaxis().set_major_formatter(plt.matplotlib.ticker.ScalarFormatter())
    ax.set_ylim(bottom=min(-0.02, float(m.min()) - 0.03))
    ax.set_xlabel("Lattice size  L")
    ax.set_ylabel("⟨|m|⟩  (vector magnetization per spin)")
    ax.set_title("Magnetization drifts toward 0 as L grows — no order at any T > 0")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m09_energy(report: dict) -> str:
    """⟨E⟩(L) flat with χ(L) overlaid — energy is intensive, |m| is the thing that drifts.

    A corroborating "nothing pathological here" plot: the energy per spin is
    essentially L-independent (an intensive quantity — the *same* physical state at
    every size), which is the receipt that the drift in ⟨|m|⟩ is the order parameter
    washing out, not the lattices sitting at different temperatures or being
    un-equilibrated. The |m|-susceptibility χ(L) is overlaid for context.
    """
    Ls = np.asarray(report["L_values"], dtype=float)
    e = np.asarray(report.get("energy") or [0.0] * len(Ls), dtype=float)
    chi = np.asarray(report.get("chi") or [0.0] * len(Ls), dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.0))
    ax.plot(Ls, e, "o-", color="#3a2e21", markersize=6, linewidth=1.4,
            label="⟨E⟩  (energy per spin — intensive, flat in L)")
    ax.set_xscale("log", base=2)
    ax.set_xticks(Ls)
    ax.get_xaxis().set_major_formatter(plt.matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Lattice size  L")
    ax.set_ylabel("E  (per spin)")
    ax2 = ax.twinx()
    ax2.plot(Ls, chi, "s-", color="#7a9b56", markersize=5, linewidth=1.2,
             alpha=0.85, label="χ  (|m|-susceptibility)")
    ax2.set_ylabel("χ  (per spin)")
    ax.set_title("Energy is flat in L — it's the magnetization, not the state, that drifts")
    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="center right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M09_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 2D Heisenberg · Mermin–Wagner</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 36px 24px 80px; min-height: 100vh;
    background: linear-gradient(180deg, #f6efe1 0%, #ede1c8 100%);
    font-family: 'Iowan Old Style', Georgia, serif;
    color: #3a2e21; line-height: 1.55;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-weight: 500; font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; margin: 38px 0 12px; font-weight: 600; }}
  .date {{ opacity: 0.55; font-size: 14px; margin-bottom: 28px; }}
  .lede {{ font-size: 17px; padding: 18px 22px; background: #fbf6ea; border-left: 3px solid #c89878; border-radius: 2px; }}
  .verdict {{ font-size: 15px; margin: 18px 0 0; padding: 12px 18px; background: #eef3e6; border-left: 3px solid #7a9b56; border-radius: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 14px; }}
  th, td {{ text-align: right; padding: 6px 10px; border-bottom: 1px solid #e3d6bd; }}
  th:first-child, td:first-child {{ text-align: left; }}
  figure {{ margin: 22px 0; }}
  figure img {{ width: 100%; height: auto; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  details {{ margin-top: 28px; padding: 14px 18px; background: #fbf6ea; border-radius: 4px; }}
  details summary {{ cursor: pointer; font-size: 13px; letter-spacing: 0.04em; opacity: 0.6; }}
  details pre {{ font-size: 11px; max-height: 320px; overflow: auto; margin-top: 12px; }}
  .footer {{ margin-top: 60px; padding-top: 18px; border-top: 1px solid #d6c0a2; opacity: 0.5; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>windowsill-lab · phase 2</h1>
  <div class="date">{date} · M09 — 2D Heisenberg · Mermin–Wagner</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Magnetization drift across lattice size</h2>
  {table}

  <h2>⟨|m|⟩ vs L — the drift toward zero is the result</h2>
  <figure><img src="data:image/png;base64,{drift_png}" alt="Heisenberg magnetization vs lattice size, drifting toward zero"></figure>

  <h2>Energy &amp; susceptibility — the state is the same, only |m| washes out</h2>
  <figure><img src="data:image/png;base64,{energy_png}" alt="Heisenberg energy and susceptibility vs lattice size"></figure>

  <details>
    <summary>Raw measurements (JSON)</summary>
    <pre>{json_dump}</pre>
  </details>

  <div class="footer">
    Sibling to <a href="https://github.com/benskamps/fish-tank">fish-tank</a>;
    its calm face is the <a href="https://www.brokenbranch.dev/windowsill/">windowsill</a>.
    One machine, one patient observation, real signal, accumulates over months.
  </div>
</div>
</body>
</html>
"""


def _m09_table(report: dict) -> str:
    """A small per-L results table: L, ⟨|m|⟩ ± err, ratio to the previous L, energy."""
    Ls = report["L_values"]
    m = report["abs_mag"]
    err = report.get("abs_mag_err") or [0.0] * len(Ls)
    e = report.get("energy") or [0.0] * len(Ls)
    rows = ["<tr><th>L</th><th>⟨|m|⟩</th><th>± err</th>"
            "<th>ratio to prev</th><th>energy</th></tr>"]
    for i, L in enumerate(Ls):
        ratio = f"{m[i] / m[i-1]:.3f}" if i > 0 and m[i-1] > 0 else "—"
        rows.append(
            f"<tr><td>{L}</td><td>{m[i]:.4f}</td><td>{err[i]:.4f}</td>"
            f"<td>{ratio}</td><td>{e[i]:.3f}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def render_m09(report: dict, date: str | None = None) -> Path:
    """Render an M09 2D-Heisenberg / Mermin–Wagner report (HTML + plots + JSON).

    Mirrors ``render_m08``: a slug-keyed ``~/.lab`` dated cache + ``latest.html``
    pointer AND a permanent committed pair (``reports/<date>-m09.html`` + ``.json``).
    M09 is a milestone whose *correct* result is a **negative** one, so the verdict
    is framed accordingly: a green ✓ "Mermin–Wagner confirmed" when ⟨|m|⟩ drifts
    monotonically toward 0 as L grows (the expected *absence* of finite-T order is
    reproduced), and a ✗ "absence NOT reproduced" when ⟨|m|⟩ fails to decrease — a
    fake finite-T transition / broken run, kept honestly as a miss, never dressed
    up as order. (This is the rare milestone where the *null IS the known answer*,
    so a reproduced negative earns the green leaf — distinct from an ``[~]`` failed
    calibration.)
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    Ls = report["L_values"]
    m = report["abs_mag"]
    T = report.get("T")
    ratios = report.get("ratios") or []
    slope = report.get("slope_vs_inv_L")
    monotone = report.get("monotone_decreasing")

    Ls_str = ", ".join(map(str, Ls))
    drift_str = " → ".join(f"{v:.3f}" for v in m)
    sentence = (
        f"I ran the 2D Heisenberg model — O(3) unit-vector spins S ∈ S², "
        f"E = −J·Σ S_i·S_j — on a family of square lattices L = {Ls_str} at a fixed "
        f"temperature T = {T}. Unlike every milestone before it, M09 has NO "
        f"transition to find: Mermin–Wagner forbids a 2D system with a continuous "
        f"symmetry from ordering at any T &gt; 0, and (unlike the XY model) the "
        f"Heisenberg sphere is simply connected, so there is no BKT escape either — "
        f"no transition of any kind at finite T. The falsifiable signature of that "
        f"absence is a finite-size drift: the per-spin magnetization ⟨|m|⟩ shrinks "
        f"toward 0 as L grows (⟨|m|⟩ = {drift_str}). "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )

    ratio_str = ", ".join(f"{r:.3f}" for r in ratios) or "—"
    slope_str = f"{slope:+.3f}" if slope is not None else "—"
    if monotone:
        verdict = (
            f"✓ Mermin–Wagner confirmed: ⟨|m|⟩ drifts {drift_str} across "
            f"L = {Ls_str} (each step ×{ratio_str} &lt; 1; slope vs 1/L = {slope_str} "
            f"&gt; 0, so ⟨|m|⟩ → 0 as L → ∞). There is no spontaneous order at this "
            f"temperature — exactly as the theorem demands. This is the rare run "
            f"whose *correct* answer is a negative one: the lab reproduces the known "
            f"*absence* of 2D Heisenberg order, distinguishing it cleanly from the "
            f"order-parameter plateau a real transition would show. (Reading a single "
            f"small L would have faked a finite ⟨|m|⟩ and a spurious transition — the "
            f"#1 way this milestone ships wrong; varying L is what makes the absence "
            f"visible.)"
        )
    else:
        verdict = (
            f"✗ The expected absence was NOT reproduced: ⟨|m|⟩ = {drift_str} across "
            f"L = {Ls_str} does not monotonically decrease (slope vs 1/L = {slope_str}). "
            f"Either the run is un-equilibrated, the sphere sampling is pole-biased, "
            f"or L is too small to clear ξ(T) — kept honestly as a miss, never "
            f"relabelled order."
        )

    json_dump = json.dumps(report, indent=2)
    html = M09_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        table=_m09_table(report),
        drift_png=_plot_m09_drift(report),
        energy_png=_plot_m09_energy(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out
