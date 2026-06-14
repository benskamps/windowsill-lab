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
    date = date or datetime.now(timezone.utc).date().isoformat()
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
