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
# The newest full report is also committed here so the windowsill page can
# deep-link it; the nightly commits reports/ on every run.
REPO_REPORTS = Path(__file__).resolve().parents[2] / "reports"


def _ensure_home() -> Path:
    LAB_HOME.mkdir(parents=True, exist_ok=True)
    return LAB_HOME


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
    out = LAB_HOME / f"{date}.html"

    T_peak, sentence = _tc_estimate(result)
    report = result.to_json()
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
    out.write_text(html, encoding="utf-8")

    # Also drop the raw JSON next to the HTML so it's easy to grep
    (LAB_HOME / f"{date}.json").write_text(json_dump, encoding="utf-8")
    # And update the latest pointer
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")

    # Publish the newest full report into the repo so the windowsill page can
    # deep-link it (the nightly commits reports/). One overwritten file — the
    # dated archive stays local in ~/.lab.
    REPO_REPORTS.mkdir(parents=True, exist_ok=True)
    (REPO_REPORTS / "latest.html").write_text(html, encoding="utf-8")
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


def render_fss(report: dict, date: str | None = None) -> Path:
    """Render an M02 finite-size-scaling report (HTML + plots + JSON sidecar).

    Mirrors ``render()``'s persistence: dated HTML/JSON in ``~/.lab``, a
    ``latest.html`` pointer, and the overwritten copy in the repo's ``reports/``.
    """
    from .publish import today_local
    from .fss import fit_gamma_over_nu, GAMMA_OVER_NU
    date = date or today_local()
    _ensure_home()
    out = LAB_HOME / f"{date}.html"

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
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    REPO_REPORTS.mkdir(parents=True, exist_ok=True)
    (REPO_REPORTS / "latest.html").write_text(html, encoding="utf-8")
    return out
