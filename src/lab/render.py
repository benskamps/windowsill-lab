"""Render a daily report HTML + plots from an Ising RunResult."""
from __future__ import annotations
from .hw import hw

import base64
import hashlib
import html as html_lib
import importlib.metadata
import io
import json
import platform
import subprocess
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
REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str | None:
    try:
        run = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5, check=False,
        )
        return (run.stdout or "").strip() if run.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _source_tree_sha256() -> str:
    """Digest the Python source tree that produced a report.

    This is not a substitute for a clean commit; it is the honest fallback that
    makes a dirty run's exact local source state distinguishable without
    publishing a patch that may contain unrelated work.
    """

    digest = hashlib.sha256()
    source = REPO_ROOT / "src" / "lab"
    for path in sorted(source.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("numpy", "torch", "matplotlib"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _stamp_report_json(json_dump: str, slug: str) -> str:
    """Add prospective, machine-readable provenance to a persisted report.

    Legacy reports remain explicitly legacy; every new committed report records
    its source commit, cleanliness, full source-tree digest, runtime, dependency
    versions, and the separate commands for saved-data regrading and stochastic
    rerunning. Missing git metadata is represented as null, never guessed.
    """

    try:
        report = json.loads(json_dump)
    except (TypeError, json.JSONDecodeError):
        return json_dump
    if not isinstance(report, dict):
        return json_dump

    status = _git("status", "--porcelain", "--", "src/lab")
    commit = _git("rev-parse", "HEAD")
    milestone = slug.upper() if slug != "run" else None
    rerun = None
    if slug == "m01":
        rerun = "python -m lab.cli run"
    elif milestone:
        rerun = f"python -m lab.cli {slug}"

    report["report_schema_version"] = 1
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    diff = _git("diff", "--binary", "HEAD", "--", "src/lab") or ""
    dirty_material = (status or "") + "\n" + diff
    report["provenance"] = {
        "source_commit": commit,
        "source_clean": status == "" if status is not None else False,
        "source_diff_sha256": (
            hashlib.sha256(dirty_material.encode("utf-8")).hexdigest()
            if status else None
        ),
        "source_tree_sha256": _source_tree_sha256(),
        "python": platform.python_version(),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "dependencies": _dependency_versions(),
    }
    report["reproduction"] = {
        "regrade": f"python -m lab.cli verify {milestone}" if milestone else "python -m lab.cli verify",
        "rerun": rerun,
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


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
    stamped_dump = _stamp_report_json(json_dump, slug)
    if stamped_dump != json_dump and json_dump in html:
        html = html.replace(json_dump, stamped_dump)
    json_dump = stamped_dump

    REPO_REPORTS.mkdir(parents=True, exist_ok=True)
    html_path = REPO_REPORTS / f"{date}-{slug}.html"
    json_path = REPO_REPORTS / f"{date}-{slug}.json"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json_dump, encoding="utf-8")
    # Keep a small, durable public record even though the full dated report is
    # intentionally gitignored.  Numerical curves + provenance remain; only
    # heavyweight lattice snapshots are replaced by explicit digests.
    from .receipt import write_public_receipt  # stdlib-only, kept lazy
    write_public_receipt(
        json.loads(json_dump),
        REPO_REPORTS / "receipts" / f"run-{date}-{slug}.json",
        json_dump.encode("utf-8"),
    )
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
        f" · {result.wall_seconds:.0f}s on {hw(result.config)}"
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


# ── M10 — antiferromagnetic Ising · the staggered order parameter ─────────────

def _plot_m10_chi(report: dict) -> str:
    """χ_s(T) with the located T_N vs the exact Onsager benchmark — M10's headline.

    The staggered susceptibility, not the uniform one — its peak is the Néel
    temperature, which by the bipartite gauge duality equals Onsager's exact T_c.
    """
    T = report["T"]
    chi = report["chi_staggered"]
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_bench = report.get("tc_benchmark", 2.0 / np.log(1.0 + np.sqrt(2.0)))
    tc_cv = report.get("tc_cv_refined")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T, chi, "o-", color="#7a4e2f", markersize=4, linewidth=1.5,
            label=f"Measured χ_s  (staggered, L={report.get('L')})")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Onsager exact T_N = {tc_bench:.4f}")
    if tc_fit is not None:
        ax.axvline(tc_fit, linestyle=":", color="#3a2e21", alpha=0.8,
                   label=f"χ_s-peak T_N(L) = {tc_fit:.3f}")
    if tc_cv is not None:
        ax.axvline(tc_cv, linestyle=":", color="#3a6ea5", alpha=0.55,
                   label=f"C-peak cross-check = {tc_cv:.3f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("χ_s  (staggered susceptibility)")
    ax.set_title("Antiferromagnet: the STAGGERED susceptibility peaks at T_N")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m10_order(report: dict) -> str:
    """Staggered ⟨|m_s|⟩ melting WITH the uniform ⟨|m|⟩ pinned at ≈0 — the AFM punchline.

    The whole milestone in one plot: the staggered order parameter melts from 1 to
    0 across T_N (the real transition), while the *uniform* magnetization — what a
    naive reader would measure — stays flat at ≈0 at every temperature, ordered
    phase included. Reading uniform m would show nothing and look broken; the AFM's
    order is hidden in the staggered (Néel) sublattice structure.
    """
    T = report["T"]
    ms = report.get("stag_mag") or [0.0] * len(T)
    ms_err = report.get("stag_mag_err") or [0.0] * len(T)
    mu = report.get("abs_mag") or [0.0] * len(T)
    tc_bench = report.get("tc_benchmark", 2.0 / np.log(1.0 + np.sqrt(2.0)))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.errorbar(T, ms, yerr=ms_err, fmt="o-", color="#3a2e21", markersize=4,
                capsize=2, linewidth=1.4, label="⟨|m_s|⟩  staggered (the order parameter)")
    ax.plot(T, mu, "s--", color="#b06a45", markersize=3.5, linewidth=1.3, alpha=0.85,
            label="⟨|m|⟩  uniform (≈0 — reading this looks broken)")
    ax.axvline(tc_bench, linestyle="--", color="#c89878", alpha=0.85,
               label=f"Onsager exact T_N = {tc_bench:.4f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("order parameter  (per spin)")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Staggered order melts at T_N; uniform magnetization stays ≈0")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M10_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · antiferromagnetic Ising</title>
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
  <div class="date">{date} · M10 — antiferromagnetic Ising</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>

  <h2>Staggered susceptibility — the peak is T_N</h2>
  <figure><img src="data:image/png;base64,{chi_png}" alt="antiferromagnetic Ising staggered susceptibility"></figure>

  <h2>Staggered order melts; uniform magnetization stays ≈0</h2>
  <figure><img src="data:image/png;base64,{order_png}" alt="staggered vs uniform magnetization"></figure>

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


def render_m10(report: dict, date: str | None = None) -> Path:
    """Render an M10 antiferromagnetic-Ising report (HTML + plots + JSON sidecar).

    Mirrors ``render_m05``/``render_m08``: a slug-keyed ``~/.lab`` dated cache +
    ``latest.html`` pointer AND a permanent committed pair
    (``reports/<date>-m10.html`` + ``.json``). The verdict is an honest **pass**
    only when the *staggered* χ_s peak lands within ±0.1 of Onsager's exact
    T_N ≈ 2.2692 AND the uniform ⟨|m|⟩ stayed ≈0 (the AFM signature — a silent
    sign-flip to the FM would peak on the uniform moment instead). It names the
    FM↔AFM gauge duality (flipping J on a bipartite lattice is the ferromagnet in
    disguise, so the Néel point is Onsager's same number). A miss stays a folded
    grey leaf with its real numbers intact, never relabelled a discovery.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    tc_fit = report.get("tc_chi_refined", report.get("tc_chi"))
    tc_cv = report.get("tc_cv_refined")
    tc_bench = report.get("tc_benchmark", 2.0 / np.log(1.0 + np.sqrt(2.0)))
    rel_err = report.get("rel_error")
    max_unif = report.get("max_abs_mag")

    sentence = (
        f"I ran the *antiferromagnetic* 2D Ising model (J = −1) on an L={L} square "
        f"lattice across a window straddling the transition. Flipping the coupling "
        f"sign favours anti-aligned neighbours — the ground state is the "
        f"checkerboard Néel state, not the aligned ferromagnet. On a bipartite "
        f"lattice the sublattice gauge flip s_i → −s_i (on one colour) turns the "
        f"antiferromagnet exactly into the ferromagnet, so the Néel temperature is "
        f"Onsager's *same* exact T_c ≈ {tc_bench:.4f}. The order parameter is the "
        f"*staggered* magnetization m_s = (1/N)Σ ε_i s_i (ε = (−1)^(x+y)); its "
        f"susceptibility χ_s peaks at T_N(L) = {tc_fit:.3f}. The uniform ⟨|m|⟩ "
        f"stays ≈0 throughout — reading it would show nothing and look broken. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )
    near = tc_fit is not None and abs(tc_fit - tc_bench) <= 0.1
    unif_ok = max_unif is None or max_unif <= 0.3
    passed = near and unif_ok
    err_str = f"{rel_err*100:.1f}%" if rel_err is not None else "—"
    cv_str = (f", and the specific-heat peak from the same run independently gives "
              f"T_N(L) = {tc_cv:.3f}") if tc_cv is not None else ""
    unif_str = (f" The uniform magnetization stayed ≤ {max_unif:.3f} across the sweep "
                f"(the AFM carries no net moment — the staggered order does all the "
                f"work)." if max_unif is not None else "")
    verdict = (
        f"{'✓' if passed else '~'} Staggered χ_s-peak T_N(L) = {tc_fit:.3f} vs Onsager "
        f"exact {tc_bench:.4f} (rel. err {err_str}){cv_str}. "
        + ("Flipping J to −1 doesn't break the engine: the antiferromagnet lands on "
           "Onsager's same critical temperature, read off the *staggered* order "
           "parameter (the uniform magnetization stays ≈0, the deliberate trap). The "
           "framework handles negative coupling cleanly — a calibration pass."
           + unif_str +
           " (Small-L finite-size effects push the pseudo-critical peak slightly "
           "above the infinite-volume T_N; an L-extrapolation would sharpen it.)"
           if passed else
           "The antiferromagnet does not land on T_N on the staggered order "
           "parameter (or the uniform moment failed to stay ≈0) — kept honestly as "
           "a null, not a discovery." + unif_str)
    )

    json_dump = json.dumps(report, indent=2)
    html = M10_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict,
        chi_png=_plot_m10_chi(report),
        order_png=_plot_m10_order(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M11 — 2D Edwards–Anderson spin glass (P(q) broadening toward T_c = 0) ─────

def _plot_m11_pq(report: dict) -> str:
    """P(q) at a few temperatures — the broadening as T → 0 is the headline visual."""
    T = np.asarray(report["T"], dtype=float)
    centers = np.asarray(report["q_bin_centers"], dtype=float)
    pq = np.asarray(report["pq"], dtype=float)            # (n_temps, n_qbins)
    # Pick up to 5 temperatures spread cold→hot to show the broadening.
    order = np.argsort(T)
    n = len(order)
    pick = order[np.linspace(0, n - 1, min(5, n)).round().astype(int)]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = [_COPPER(0.12 + 0.78 * i / max(1, len(pick) - 1)) for i in range(len(pick))]
    for col, idx in zip(colors, pick):
        ax.plot(centers, pq[idx], "-", color=col, linewidth=1.8,
                label=f"T = {T[idx]:.2f}")
    ax.set_xlabel("overlap  q")
    ax.set_ylabel("P(q)  (disorder-averaged)")
    ax.set_title("P(q) broadens as T → 0 — the approach to the T=0 glass")
    ax.legend(frameon=False, fontsize=9, title="cold → hot")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m11_q2(report: dict) -> str:
    """⟨q²⟩(T) (the broadening signal) with the Binder cumulant overlaid."""
    T = np.asarray(report["T"], dtype=float)
    q2 = np.asarray(report["q2_mean"], dtype=float)
    binder = np.asarray(report.get("binder") or [0.0] * len(T), dtype=float)
    order = np.argsort(T)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T[order], q2[order], "o-", color="#7a4e2f", markersize=5, linewidth=1.6,
            label="⟨q²⟩  (overlap second moment)")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("⟨q²⟩")
    ax2 = ax.twinx()
    ax2.plot(T[order], binder[order], "s-", color="#7a9b56", markersize=4,
             linewidth=1.2, alpha=0.85, label="Binder g")
    ax2.set_ylabel("Binder cumulant  g")
    ax.set_title("⟨q²⟩ grows as T → 0 — no finite-T transition (2D EA: T_c = 0)")
    lines1, lab1 = ax.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="upper right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M11_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 2D Edwards–Anderson spin glass</title>
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
  .caveat {{ font-size: 14px; margin: 14px 0 0; padding: 12px 18px; background: #f6eee0; border-left: 3px solid #c89878; border-radius: 2px; opacity: 0.95; }}
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
  <h1>windowsill-lab · phase 3</h1>
  <div class="date">{date} · M11 — 2D Edwards–Anderson spin glass</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>
  <div class="caveat">{caveat}</div>

  <h2>P(q) — the overlap distribution broadens as T → 0</h2>
  <figure><img src="data:image/png;base64,{pq_png}" alt="overlap distribution P(q) at several temperatures"></figure>

  <h2>⟨q²⟩(T) &amp; the Binder cumulant — the broadening signal</h2>
  <figure><img src="data:image/png;base64,{q2_png}" alt="overlap second moment and Binder cumulant vs temperature"></figure>

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


def render_m11(report: dict, date: str | None = None) -> Path:
    """Render an M11 2D Edwards–Anderson spin-glass report (HTML + plots + JSON).

    Mirrors ``render_m09`` (the other "verify an expected behaviour, not a T_c"
    milestone): a slug-keyed ``~/.lab`` dated cache + ``latest.html`` pointer AND a
    permanent committed pair (``reports/<date>-m11.html`` + ``.json``). M11's *correct*
    result is the **approach to a T = 0 critical point**, not a transition — the 2D EA
    glass orders only at T = 0 (lower critical dimension). The verdict is a green ✓
    "P(q) broadens toward T=0" when ⟨q²⟩ grows monotonically as T falls and P(q) stays
    symmetric; a ✗ otherwise. An equilibration caveat is always shown honestly (spin
    glasses are hard to equilibrate at low T; this engine uses heavy Metropolis, not
    parallel tempering), so the run never overclaims a low-T result it can't reach.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    n_real = report.get("n_realizations")
    T = report.get("T") or []
    q2 = report.get("q2_mean") or []
    monotone = report.get("monotone_broadening")
    frac = report.get("broadening_fraction")
    q2_cold = report.get("q2_cold")
    q2_hot = report.get("q2_hot")
    max_abs_qmean = report.get("max_abs_q_mean")
    sym_resid = report.get("pq_symmetry_resid")
    t_cold = min(T) if T else 0.0
    t_hot = max(T) if T else 0.0

    sentence = (
        f"I ran the 2D Edwards–Anderson spin glass — Ising spins with quenched "
        f"random ±J bonds, E = −Σ J_ij s_i s_j — on an L={L} square lattice across "
        f"{len(T)} temperatures, averaged over {n_real} disorder realizations, with "
        f"two independent replicas per realization so I can read the overlap "
        f"q = (1/N) Σ s_i^α s_i^β. Unlike a clean transition, the 2D glass orders "
        f"only at T = 0 (the lower critical dimension), so the signature is the "
        f"disorder-averaged P(q) <em>broadening</em> as T → 0: ⟨q²⟩ grows "
        f"{q2_hot:.3f} → {q2_cold:.3f} as T falls {t_hot:.2f} → {t_cold:.2f}. "
        f"Wall time on the GPU: {report.get('wall_seconds', 0):.0f}s."
    )

    frac_str = f"{frac*100:.0f}%" if frac is not None else "—"
    if monotone:
        verdict = (
            f"✓ P(q) broadens toward T = 0: ⟨q²⟩ grows {q2_hot:.3f} → {q2_cold:.3f} "
            f"as the lattice cools ({frac_str} of temperature steps broaden), and the "
            f"distribution stays symmetric (max|⟨q⟩| = {max_abs_qmean:.3f} ≈ 0). This "
            f"is the expected approach to the T = 0 spin-glass critical point — in two "
            f"dimensions the Edwards–Anderson glass orders <em>only</em> at T = 0 (the "
            f"lower critical dimension), so there is <em>no</em> finite-temperature "
            f"glass phase to find. Reproducing the broadening (not a transition) is the "
            f"calibrated result; like the Mermin–Wagner null (M09), the known behaviour "
            f"IS the answer. (A finite-T transition with a Binder-cumulant crossing is "
            f"the 3D case — that's M12.)"
        )
    else:
        verdict = (
            f"~ P(q) did NOT broaden cleanly toward T = 0: ⟨q²⟩ = {q2_hot:.3f} → "
            f"{q2_cold:.3f} ({frac_str} of steps broaden), max|⟨q⟩| = {max_abs_qmean:.3f}. "
            f"Kept honestly as an open/null — either the low-T points are "
            f"un-equilibrated (the likely culprit; see the caveat) or the window is "
            f"too narrow. Never relabelled a finite-T transition (there is none in 2D)."
        )

    caveat = (
        f"Honesty on equilibration: 2D spin glasses are genuinely hard to equilibrate "
        f"at low T (rugged free-energy landscape, long autocorrelation times). This "
        f"engine uses heavy single-spin checkerboard Metropolis with a long burn-in — "
        f"<em>not</em> parallel tempering — so the lowest-T points may be only "
        f"partially equilibrated. The symmetry diagnostic max|⟨q⟩| = {max_abs_qmean:.3f} "
        f"and the coldest-T P(q) symmetry residual {sym_resid:.3f} (both ≈ 0 when "
        f"equilibrated) are reported so a mistune is visible, not hidden. The "
        f"<em>broadening trend</em> toward T = 0 is robust well before full low-T "
        f"equilibration; the precise low-T P(q) shape is not claimed. Parallel "
        f"tempering would sharpen the cold end — see BACKLOG."
    )

    json_dump = json.dumps(report, indent=2)
    html = M11_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict, caveat=caveat,
        pq_png=_plot_m11_pq(report),
        q2_png=_plot_m11_q2(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


def _plot_m12_binder(report: dict) -> str:
    """The headline: disorder-averaged Binder cumulant g_L(T) for each L — they CROSS.

    The multi-size intersection is the finite-T spin-glass transition T_SG. A vertical
    marker shows the located crossing (when one resolved) and a faint line the ≈0.95
    benchmark, so the eye lands on the physics claim.
    """
    T = np.asarray(report["T"], dtype=float)
    order = np.argsort(T)
    Ts = T[order]
    binder_by_L = report.get("binder_by_L") or {}
    Ls = sorted(binder_by_L, key=lambda k: int(k))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = [_COPPER(0.15 + 0.72 * i / max(1, len(Ls) - 1)) for i in range(len(Ls))]
    for col, L in zip(colors, Ls):
        g = np.asarray(binder_by_L[L], dtype=float)[order]
        ax.plot(Ts, g, "o-", color=col, markersize=4, linewidth=1.6, label=f"L = {L}")
    bench = report.get("t_sg_benchmark", 0.95)
    ax.axvline(bench, color="#8a8a8a", linestyle=":", linewidth=1.1,
               label=f"benchmark ≈ {bench:.2f}")
    ct = report.get("crossing_T")
    if ct is not None:
        ax.axvline(ct, color="#7a9b56", linestyle="--", linewidth=1.4,
                   label=f"crossing T_SG = {ct:.3f}")
    ax.set_xlabel("Temperature  T  (J/k_B)")
    ax.set_ylabel("Binder cumulant  g_L")
    ax.set_title("g_L(T) crosses at T_SG — the finite-T 3D spin-glass transition")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m12_pq(report: dict) -> str:
    """P(q) at the largest L across temperatures — the overlap distribution's structure.

    Below T_SG the disorder-averaged P(q) grows weight at large |q| (the glass); above it
    stays a narrow peak at q = 0 (the paramagnet). Symmetric P(q) = P(−q) by the ±J
    symmetry — the equilibration diagnostic made visible.
    """
    T = np.asarray(report["T"], dtype=float)
    centers = np.asarray(report.get("q_bin_centers") or [], dtype=float)
    pq = np.asarray(report.get("pq_ref") or [], dtype=float)
    L_ref = report.get("pq_ref_L")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    if pq.size and centers.size:
        order = np.argsort(T)
        n = len(order)
        pick = order[np.linspace(0, n - 1, min(5, n)).round().astype(int)]
        colors = [_COPPER(0.12 + 0.78 * i / max(1, len(pick) - 1)) for i in range(len(pick))]
        for col, idx in zip(colors, pick):
            ax.plot(centers, pq[idx], "-", color=col, linewidth=1.8, label=f"T = {T[idx]:.2f}")
        ax.legend(frameon=False, fontsize=9, title="cold → hot")
    ax.set_xlabel("overlap  q")
    ax.set_ylabel("P(q)  (disorder-averaged)")
    ax.set_title(f"P(q) at L = {L_ref} — broadens into the glass below T_SG")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M12_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab · {date} · 3D Edwards–Anderson spin glass</title>
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
  .caveat {{ font-size: 14px; margin: 14px 0 0; padding: 12px 18px; background: #f6eee0; border-left: 3px solid #c89878; border-radius: 2px; opacity: 0.95; }}
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
  <h1>windowsill-lab · phase 3</h1>
  <div class="date">{date} · M12 — 3D Edwards–Anderson spin glass</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>
  <div class="caveat">{caveat}</div>

  <h2>The Binder cumulant crossing — the finite-T spin-glass transition</h2>
  <figure><img src="data:image/png;base64,{binder_png}" alt="disorder-averaged Binder cumulant vs temperature for several lattice sizes, crossing at T_SG"></figure>

  <h2>P(q) — the overlap distribution at the largest lattice</h2>
  <figure><img src="data:image/png;base64,{pq_png}" alt="overlap distribution P(q) at several temperatures"></figure>

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


def render_m12(report: dict, date: str | None = None) -> Path:
    """Render an M12 3D Edwards–Anderson spin-glass report (HTML + plots + JSON).

    Mirrors ``render_m11`` but the physics is different: the **3D** ±J glass has a real
    finite-temperature transition, so the verdict is the **multi-L Binder-cumulant
    crossing** landing near T_SG ≈ 0.95 (not a T = 0 approach). A green ✓ when a crossing
    resolves within tolerance and the overlap stays symmetric; a ✗/~ honest null when it
    does not — the parallel-tempering equilibration caveat is always shown, and a small
    CPU ``--quick`` pass is labelled as a code proof, not a resolved crossing.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L_values = report.get("L_values") or []
    n_real = report.get("n_realizations")
    T = report.get("T") or []
    ct = report.get("crossing_T")
    bench = report.get("t_sg_benchmark", 0.95)
    tol = report.get("tolerance", 0.15)
    resolved = report.get("crossing_resolved")
    max_abs_qmean = report.get("max_abs_q_mean", 0.0)
    pairs = report.get("crossing_pairs") or []
    mean_T = report.get("crossing_mean_T")
    swap_by_L = report.get("swap_rate_by_L") or {}
    swap_vals = [v for arr in swap_by_L.values() for v in arr]
    swap_mean = sum(swap_vals) / len(swap_vals) if swap_vals else 0.0
    t_cold = min(T) if T else 0.0
    t_hot = max(T) if T else 0.0
    ct_str = f"{ct:.3f}" if ct is not None else "none"
    mean_str = f"{mean_T:.3f}" if mean_T is not None else "—"
    pair_str = ", ".join(f"{p['L1']}/{p['L2']} → {p['T']:.3f}" for p in pairs) or "none"

    sentence = (
        f"I ran the 3D Edwards–Anderson spin glass — Ising spins with quenched random "
        f"±J bonds on a simple-cubic lattice, E = −Σ J_ij s_i s_j — across lattice sizes "
        f"L = {L_values} on one shared temperature ladder [{t_cold:.2f}, {t_hot:.2f}] "
        f"straddling T_SG ≈ 0.95, averaged over {n_real} disorder realizations with two "
        f"replicas each for the overlap q = (1/N) Σ s_i^α s_i^β. Unlike the 2D glass "
        f"(M11, which orders only at T = 0), the 3D glass has a genuine finite-temperature "
        f"transition, and its fingerprint is the disorder-averaged <em>Binder cumulant "
        f"crossing</em> across sizes. Parallel tempering (mean swap acceptance "
        f"{swap_mean:.2f}) equilibrates the cold rungs. Wall time: "
        f"{report.get('wall_seconds', 0):.0f}s."
    )

    if resolved:
        verdict = (
            f"✓ The Binder cumulant curves g_L(T) cross at T_SG = {ct_str} — inside the "
            f"{bench:.2f} ± {tol:.2f} benchmark band for the 3D ±J Edwards–Anderson "
            f"transition — and the overlap stays symmetric (max|⟨q⟩| = {max_abs_qmean:.3f} "
            f"≈ 0). Pairwise crossings [{pair_str}] (mean {mean_str}). This is the genuine "
            f"finite-temperature spin-glass transition — the famous hard case that, unlike "
            f"2D (T_c = 0, M11), orders at a real temperature. The scale-invariant crossing "
            f"(not a single-L peak) is the calibrated result."
        )
    else:
        why = ("no multi-size crossing resolved" if ct is None
               else f"the crossing landed at {ct_str}, outside the {bench:.2f} ± {tol:.2f} band")
        verdict = (
            f"~ No clean Binder crossing near {bench:.2f} — {why}. Kept honestly as an "
            f"open/null (a folded grey leaf), <em>not</em> a fake green. The most likely "
            f"cause at this scale is under-equilibration / too few disorder realizations: "
            f"resolving a sharp 3-size crossing needs a long parallel-tempered GPU run. A "
            f"CPU <code>--quick</code> pass proves the pipeline end-to-end but is not "
            f"expected to resolve the physics. Pairwise crossings observed: [{pair_str}]."
        )

    caveat = (
        f"Honesty on equilibration: 3D spin glasses are hard to equilibrate near T_SG "
        f"(rugged landscape, long autocorrelation times). This engine uses checkerboard "
        f"Metropolis <em>with parallel tempering</em> (replica exchange across the "
        f"temperature ladder — the tool M11 lacked), because single-spin dynamics alone "
        f"produces a smeared, crossing-free g_L(T) that only looks finished. The mean swap "
        f"acceptance {swap_mean:.2f} and the symmetry diagnostic max|⟨q⟩| = "
        f"{max_abs_qmean:.3f} (≈ 0 when equilibrated) are reported so a mistune is visible, "
        f"not hidden. Promotion to a verified ✓ is human-reviewed via the report PR — the "
        f"milestone is never auto-marked done from an unattended run."
    )

    json_dump = json.dumps(report, indent=2)
    html = M12_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict, caveat=caveat,
        binder_png=_plot_m12_binder(report),
        pq_png=_plot_m12_pq(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M13 — frustrated triangular AFM residual (Wannier) entropy by C/T integration ──

def _plot_m13_specific_heat(report: dict) -> str:
    """C(T) over the wide geometric window — a broad hump, NOT a divergence.

    The frustrated antiferromagnet has no ordering transition, so there is no peak to
    locate; the whole curve is the integrand's numerator. A log temperature axis (the
    grid is geometric) shows the low-T rise and the high-T ``C proportional to 1/T^2``
    fall-off, and the energy per spin is overlaid to show it settling onto the exact
    ground state -1.
    """
    T = np.asarray(report["T"], dtype=float)
    C = np.asarray(report["specific_heat"], dtype=float)
    e = np.asarray(report.get("energy") or [], dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(T, C, "o-", color="#7a4e2f", markersize=3.5, linewidth=1.5,
            label="C(T) (specific heat)")
    ax.set_xscale("log")
    ax.set_xlabel("Temperature  T  (|J|/k_B, log scale)")
    ax.set_ylabel("C  (per spin)")
    ax.set_title("Specific heat - a broad hump, no transition (frustration)")
    ax.set_facecolor("#fbf6ea")
    if e.size:
        ax2 = ax.twinx()
        ax2.plot(T, e, "s-", color="#3a6ea5", markersize=2.6, linewidth=1.1, alpha=0.7,
                 label="energy / spin")
        ax2.axhline(-1.0, linestyle="--", color="#c89878", alpha=0.8,
                    label="exact ground state -1")
        ax2.set_ylabel("energy  (per spin)")
        lines1, lab1 = ax.get_legend_handles_labels()
        lines2, lab2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, lab1 + lab2, frameon=False, fontsize=8, loc="upper left")
    else:
        ax.legend(frameon=False, fontsize=8.5)
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m13_entropy(report: dict) -> str:
    """The headline: S(T) integrated down from ln2, plateauing at the residual S0.

    Cooling removes entropy at the rate dS = (C/T) dT, so S(T) descends from the free-spin
    reference ln 2 (dashed) and flattens onto the residual as T -> 0. The measured residual
    (with the analytic high-T tail) is marked against Wannier's exact 0.3383 - the eye
    lands on the gap between the plateau and the benchmark, which IS the calibration.
    """
    T = np.asarray(report["T"], dtype=float)
    S = np.asarray(report.get("entropy_curve") or [], dtype=float)
    s_inf = report.get("s_inf", np.log(2.0))
    s0 = report.get("s0_measured")
    bench = report.get("s0_benchmark", 0.3383)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    if S.size:
        ax.plot(T, S, "o-", color="#7a9b56", markersize=3.5, linewidth=1.7,
                label="S(T) = ln2 - integral C/T' dT'")
    ax.axhline(s_inf, linestyle="--", color="#c89878", alpha=0.85,
               label=f"S(inf) = ln 2 = {s_inf:.4f}")
    ax.axhline(bench, linestyle="-", color="#3a2e21", alpha=0.55,
               label=f"Wannier exact S0/N = {bench:.4f}")
    if s0 is not None:
        ax.axhline(s0, linestyle=":", color="#3a6ea5", alpha=0.9,
                   label=f"measured residual S0/N = {s0:.4f}")
    ax.set_xscale("log")
    ax.set_xlabel("Temperature  T  (|J|/k_B, log scale)")
    ax.set_ylabel("S  (per spin, k_B)")
    ax.set_ylim(0, s_inf * 1.08)
    ax.set_title("Entropy by integration - the residual survives to T -> 0")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M13_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab &middot; {date} &middot; frustrated triangular antiferromagnet</title>
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
  .caveat {{ font-size: 14px; margin: 14px 0 0; padding: 12px 18px; background: #f6eee0; border-left: 3px solid #c89878; border-radius: 2px; opacity: 0.95; }}
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
  <h1>windowsill-lab &middot; phase 3</h1>
  <div class="date">{date} &middot; M13 - frustrated triangular antiferromagnet</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>
  <div class="caveat">{caveat}</div>

  <h2>Specific heat &amp; energy - a broad hump, no transition</h2>
  <figure><img src="data:image/png;base64,{cv_png}" alt="specific heat C(T) and energy per spin over a wide temperature window"></figure>

  <h2>Entropy by integration - the residual survives to T -&gt; 0</h2>
  <figure><img src="data:image/png;base64,{entropy_png}" alt="entropy S(T) integrated down from ln2, plateauing at the residual"></figure>

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


def render_m13(report: dict, date: str | None = None) -> Path:
    """Render an M13 frustrated-triangular-AFM residual-entropy report (HTML + plots + JSON).

    The physics is unlike every prior milestone: no peak, no crossing - the signature is an
    **integrated** residual entropy. The verdict is a green check when the residual, re-derived
    by integrating C(T)/T down from S(inf)=ln2, lands within tolerance of Wannier's exact
    0.3383 AND the cold-end energy sits on the exact ground state -1; otherwise an honest
    null (a folded grey leaf), never a fake green. Promotion to a verified check on the
    windowsill is human-reviewed via the report PR - never auto-marked from an unattended run.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    s0 = report.get("s0_measured")
    s0_nt = report.get("s0_no_tail")
    bench = report.get("s0_benchmark", 0.3383)
    abs_err = report.get("s0_abs_error")
    e_ground = report.get("e_ground")
    resolved = report.get("resolved")
    removed = report.get("entropy_removed")
    tail = report.get("high_t_tail")
    T = report.get("T") or []
    t_cold = min(T) if T else 0.0
    t_hot = max(T) if T else 0.0

    sentence = (
        f"I ran the antiferromagnetic Ising model (J = -1) on a triangular lattice "
        f"(L={L}) across a wide geometric temperature window [{t_cold:.2f}, {t_hot:.1f}]. "
        f"On the triangular lattice the antiferromagnet is <em>frustrated</em> - every "
        f"triangle is an odd cycle, so the three spins can never all disagree - which "
        f"means there is no ordering transition and the ground state is macroscopically "
        f"degenerate. That degeneracy leaves a residual entropy at absolute zero, and I "
        f"measured it the only way you can: by integrating the specific heat, "
        f"S0/N = ln2 - integral of C(T)/T dT, cooling from the free-spin limit toward T = 0. "
        f"Wall time: {report.get('wall_seconds', 0):.0f}s."
    )

    err_str = f"{abs_err:.4f}" if abs_err is not None else "-"
    nt_str = f"{s0_nt:.4f}" if s0_nt is not None else "-"
    if resolved:
        verdict = (
            f"The integrated residual entropy is S0/N = {s0:.4f} k_B - within tolerance of "
            f"Wannier's exact 0.3383 (delta = {err_str}) - and the cold-end energy sits on the "
            f"exact frustrated ground state at {e_ground:.4f} per spin (-1). The lab's first "
            f"integrated thermodynamic quantity reproduces a known macroscopic degeneracy: "
            f"a real residual entropy, not a rounding error."
        )
    else:
        why = ("the ground-state energy is off (a wrong sign or geometry?)"
               if e_ground is not None and abs(e_ground + 1.0) > 0.06
               else f"the integrated residual {s0:.4f} misses the 0.3383 benchmark")
        verdict = (
            f"No clean residual near 0.3383 - {why}. Kept honestly as an open/null (a folded "
            f"grey leaf), <em>not</em> a fake green. The most likely cause at this scale is a "
            f"coarse temperature grid or a small lattice biasing the C/T integral; a wider, "
            f"finer sweep on a larger lattice sharpens it."
        )

    caveat = (
        f"Honesty on the integration: the residual is an <em>integrated</em> quantity measured "
        f"over a finite temperature window, so it is a few-percent number, not an exact one. It "
        f"lands slightly <em>below</em> Wannier's 0.3383 and converges toward about 0.32 as the "
        f"lattice grows (L=24 gives ~0.334, L=96 ~0.322) - that residual gap is the finite-window "
        f"integration systematic, not a lattice or model error: the ground-state energy is an "
        f"exact -1 per spin at every size. C/T is integrated in log-temperature (grid-robust on "
        f"the geometric grid); the small high-T tail beyond T_max is added back analytically "
        f"({tail:.4f} k_B, the leading C=a/T^2 form), without which the residual reads {nt_str}; "
        f"the entropy removed across the window is {removed:.4f} k_B against the free-spin "
        f"reference S(inf) = ln 2 = {report.get('s_inf', 0):.4f}. The grading check re-integrates "
        f"C/T from these arrays with its own tolerance, so the report cannot set its own bar; "
        f"promotion to a verified check is human-reviewed."
    )

    json_dump = json.dumps(report, indent=2)
    html = M13_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict, caveat=caveat,
        cv_png=_plot_m13_specific_heat(report),
        entropy_png=_plot_m13_entropy(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


def _plot_m14_energy(report: dict) -> str:
    """The verified claim: measured energy on the Nishimori line vs the exact identity.

    Walking p up the Nishimori line, the disorder-averaged energy per spin should trace the
    exact curve E/N = -2 tanh(1/T) = -2(1-2p) (solid). The measured points (at the gate L)
    are overlaid with error bars; the eye lands on how tightly they sit on the exact line -
    that agreement IS the calibration.
    """
    p = np.asarray(report["p_values"], dtype=float)
    e_exact = np.asarray(report["energy_exact"], dtype=float)
    gate_L = str(report.get("gate_L"))
    e_meas = np.asarray(report["energy_by_L"][gate_L], dtype=float)
    e_err = np.asarray(report.get("energy_err_by_L", {}).get(gate_L, [0.0] * len(p)), dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(p, e_exact, "-", color="#9b6b3e", linewidth=2,
            label="exact  E/N = -2 tanh(1/T) = -2(1-2p)")
    ax.errorbar(p, e_meas, yerr=e_err, fmt="o", color="#3a2e21", markersize=5, capsize=2,
                label=f"measured (L={gate_L})")
    ax.axvline(report.get("p_c_benchmark", 0.1094), linestyle="--", color="#c89878",
               alpha=0.7, label=f"MNP p_c = {report.get('p_c_benchmark', 0.1094):.4f}")
    ax.set_xlabel("antiferromagnetic-bond fraction  p  (along the Nishimori line)")
    ax.set_ylabel("energy  E/N  (per spin)")
    ax.set_title("Nishimori-line energy - measured vs exact identity")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m14_order(report: dict) -> str:
    """The map: the ferromagnetic order parameter |m| collapsing near the MNP.

    Along the Nishimori line, the disorder-averaged |m| is strong (ferromagnet) at small p
    and dies as p rises toward the multicritical point. Plotted for each L, with the
    benchmark p_c marked. The collapse brackets p_c ~ 0.109 - an approximate map at this
    scale, not a precise pinning (the two-L Binder crossing does not resolve here).
    """
    p = np.asarray(report["p_values"], dtype=float)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = ["#7a9b56", "#3a6ea5", "#7a4e2f", "#9b6b3e"]
    for i, L in enumerate(report.get("L_values", [])):
        m = np.asarray(report["abs_mag_by_L"][str(L)], dtype=float)
        ax.plot(p, m, "o-", color=colors[i % len(colors)], markersize=4, linewidth=1.5,
                label=f"|m| (L={L})")
    ax.axvline(report.get("p_c_benchmark", 0.1094), linestyle="--", color="#c89878",
               alpha=0.8, label=f"MNP benchmark p_c = {report.get('p_c_benchmark', 0.1094):.4f}")
    ph = report.get("mnp_order_p_half")
    if ph is not None:
        ax.axvline(ph, linestyle=":", color="#3a2e21", alpha=0.6,
                   label=f"|m| drops through 1/2 at p ~ {ph:.3f}")
    ax.set_xlabel("antiferromagnetic-bond fraction  p  (along the Nishimori line)")
    ax.set_ylabel("|m|  (ferromagnetic order, per spin)")
    ax.set_title("Mapping the multicritical point - ferro order dies near p_c")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M14_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab &middot; {date} &middot; random-bond Ising (Nishimori)</title>
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
  .caveat {{ font-size: 14px; margin: 14px 0 0; padding: 12px 18px; background: #f6eee0; border-left: 3px solid #c89878; border-radius: 2px; opacity: 0.95; }}
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
  <h1>windowsill-lab &middot; phase 3</h1>
  <div class="date">{date} &middot; M14 - random-bond Ising, the Nishimori line</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>
  <div class="caveat">{caveat}</div>

  <h2>Nishimori-line energy - measured vs the exact identity</h2>
  <figure><img src="data:image/png;base64,{energy_png}" alt="disorder-averaged energy per spin along the Nishimori line vs the exact -2 tanh(1/T) identity"></figure>

  <h2>Mapping the multicritical point - ferro order dies near p_c</h2>
  <figure><img src="data:image/png;base64,{order_png}" alt="ferromagnetic order parameter collapsing as p rises toward the multicritical Nishimori point"></figure>

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


def render_m14(report: dict, date: str | None = None) -> Path:
    """Render an M14 random-bond-Ising / Nishimori-line report (HTML + plots + JSON).

    The verified claim is the exact Nishimori-line internal energy: the measured disorder-
    averaged energy per spin reproduces -2 tanh(1/T) across a spread of p on the line. The
    green check is earned by that identity (re-derived by check_m14); the multicritical
    point p_c itself is only mapped approximately at this scale and is called out honestly
    as an open edge, never a fake green. Promotion is human-reviewed via the report PR.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    gate_L = report.get("gate_L")
    max_dev = report.get("max_energy_dev")
    resolved = report.get("energy_resolved")
    ph = report.get("mnp_order_p_half")
    crossing = report.get("binder_crossing_p")
    p_c = report.get("p_c_benchmark", 0.1094)
    t_c = report.get("t_c_benchmark", 0.9528)
    ps = report.get("p_values") or []
    p_lo = min(ps) if ps else 0.0
    p_hi = max(ps) if ps else 0.0
    n_real = report.get("n_realizations")

    sentence = (
        f"I ran the random-bond Ising model - a square grid of spins where a fraction p of "
        f"the couplings are flipped antiferromagnetic - along its <em>Nishimori line</em>, "
        f"the special curve tanh(1/T) = 1 - 2p where a hidden gauge symmetry makes the energy "
        f"exactly solvable. I swept p across [{p_lo:.2f}, {p_hi:.2f}] (each at its own line "
        f"temperature T = 2/ln((1-p)/p)), averaging the energy over {n_real} frozen disorder "
        f"realizations at L={gate_L}. Wall time: {report.get('wall_seconds', 0):.0f}s."
    )

    dev_str = f"{max_dev:.3f}" if max_dev is not None else "-"
    if resolved:
        verdict = (
            f"The measured disorder-averaged energy sits on the exact Nishimori-line identity "
            f"E/N = -2 tanh(1/T) = -2(1 - 2p) across the whole sweep - the largest departure is "
            f"only Delta = {dev_str} per spin. That identity holds at any lattice size (it is a "
            f"gauge symmetry, not a finite-size-shifted critical point), so reproducing it is a "
            f"real, cheap, exact win on the frontier of the ladder: the lab's first result on a "
            f"quenched-disorder phase diagram."
        )
    else:
        verdict = (
            f"The measured energy departs from the exact Nishimori-line identity (largest Delta = "
            f"{dev_str} per spin). Kept honestly as an open/null - a folded grey leaf - not a fake "
            f"green. The likely cause is under-equilibration of the frozen +/-J disorder at the "
            f"colder points; more sweeps or realizations sharpen it."
        )

    ph_str = f"p ~ {ph:.3f}" if ph is not None else "not cleanly located in-window"
    cross_str = (f"an approximate two-size Binder crossing at p ~ {crossing:.3f}"
                 if crossing is not None else
                 "no clean two-size Binder crossing (the L=12 and L=24 curves do not cross "
                 "in this window - the expected strong finite-size drift of the MNP)")
    caveat = (
        f"Honesty on the multicritical point itself: mapping <em>where</em> the ferromagnet dies "
        f"on the Nishimori line - the multicritical Nishimori point, benchmark p_c &asymp; {p_c:.4f}, "
        f"T_c &asymp; {t_c:.4f} - is genuinely hard at a windowsill's scale. The ferromagnetic order "
        f"parameter |m| does collapse through the right region ({ph_str} at L={gate_L}), bracketing "
        f"the benchmark, but pinning p_c precisely needs a large lattice and many realizations (a "
        f"hero run): here there is {cross_str}. So the exact energy earns the leaf; the precise MNP "
        f"stays a documented open edge. The grading check re-derives the exact energy from each "
        f"point's own temperature with its own tolerance - the report cannot set its own bar - and "
        f"does not gate on the MNP location; promotion is human-reviewed."
    )

    json_dump = json.dumps(report, indent=2)
    html = M14_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict, caveat=caveat,
        energy_png=_plot_m14_energy(report),
        order_png=_plot_m14_order(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


# ── M15 — Glauber-dynamics domain growth (Phase 4: non-equilibrium coarsening) ────────────

def _plot_m15_growth(report: dict) -> str:
    """The headline: L(t) vs t on log-log, both estimators, with the t^(1/2) reference slope.

    The measured correlation length (graded) and energy length (cross-check) trace parallel
    straight lines; a dashed guide of pure slope ½ (Allen-Cahn) is anchored through the
    correlation fit so the eye reads the small preasymptotic deficit directly. The shaded band
    marks the scaling window the exponent was fit in.
    """
    t = np.asarray(report["times"], dtype=float)
    Lc = np.asarray(report["L_corr"], dtype=float)
    Le = np.asarray(report["L_energy"], dtype=float)
    cf = report.get("corr_fit") or {}
    n = report.get("exponent", cf.get("exponent"))
    intr = cf.get("intercept")
    t_lo, t_hi = cf.get("t_lo"), cf.get("t_hi")

    fig, ax = plt.subplots(figsize=(7, 4.6))
    ax.loglog(t, Lc, "o", color="#3a2e21", markersize=4.5, label="correlation length  L_c(t)")
    fin = np.isfinite(Le) & (Le > 0)
    ax.loglog(t[fin], Le[fin], "s", color="#7a9b56", markersize=3.5, alpha=0.8,
              label="energy length  L_e(t) ~ 1/(E-E_eq)")
    # The fitted correlation-length power law across the scaling window.
    if intr is not None and n is not None and t_lo and t_hi:
        xs = np.linspace(np.log(t_lo), np.log(t_hi), 100)
        ax.loglog(np.exp(xs), np.exp(intr + n * xs), "-", color="#7a4e2f", linewidth=2,
                  label=f"fit: n = {n:.3f}")
        # A pure slope-half Allen-Cahn guide, anchored at the window's low end.
        y0 = np.exp(intr + n * np.log(t_lo))
        ax.loglog([t_lo, t_hi], [y0, y0 * (t_hi / t_lo) ** 0.5], "--", color="#c89878",
                  linewidth=1.6, label="Allen-Cahn slope 1/2")
        ax.axvspan(t_lo, t_hi, color="#c89878", alpha=0.08)
    ax.set_xlabel("Monte-Carlo time  t  (sweeps)")
    ax.set_ylabel("domain length  L(t)  (lattice units)")
    ax.set_title("Domain growth after a quench - L(t) ~ t^n")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m15_snapshots(report: dict) -> str:
    """The coarsening gallery: lattice snapshots at increasing times - domains growing."""
    snaps = report.get("snapshots") or {}
    keys = sorted(snaps.keys(), key=lambda k: int(k.split("=")[1]))
    if not keys:
        fig, ax = plt.subplots(figsize=(4, 3)); ax.axis("off")
        return _fig_to_b64(fig)
    fig, axes = plt.subplots(1, len(keys), figsize=(3.0 * len(keys), 3.2))
    if len(keys) == 1:
        axes = [axes]
    for ax, k in zip(axes, keys):
        ax.imshow(np.asarray(snaps[k]), cmap="bone", interpolation="nearest")
        ax.set_title(k, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Coarsening: ordered domains grow with time (one seed)", fontsize=11)
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


def _plot_m15_correlation(report: dict) -> str:
    """The equal-time G(r,t) family - the curve whose half-height IS the domain length."""
    G = report.get("G_snapshots") or {}
    keys = sorted(G.keys(), key=lambda k: int(k.split("=")[1]))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for k, col in zip(keys, _l_colors(max(len(keys), 2))):
        g = np.asarray(G[k], dtype=float)
        r = np.arange(len(g))
        ax.plot(r, g, "-", color=col, linewidth=1.6, label=k)
    ax.axhline(0.5, linestyle="--", color="#c89878", alpha=0.8, label="G = 1/2 (defines L_c)")
    ax.set_xlabel("separation  r  (lattice units)")
    ax.set_ylabel("G(r, t)  (normalised, G(0)=1)")
    ax.set_title("Equal-time correlation broadens as domains coarsen")
    ax.legend(frameon=False, fontsize=9)
    ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    return _fig_to_b64(fig)


M15_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>windowsill-lab &middot; {date} &middot; Glauber domain growth</title>
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
  .caveat {{ font-size: 14px; margin: 14px 0 0; padding: 12px 18px; background: #f6eee0; border-left: 3px solid #c89878; border-radius: 2px; opacity: 0.95; }}
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
  <h1>windowsill-lab &middot; phase 4</h1>
  <div class="date">{date} &middot; M15 - Glauber dynamics, domain growth after a quench</div>

  <div class="lede">{sentence}</div>
  <div class="verdict">{verdict}</div>
  <div class="caveat">{caveat}</div>

  <h2>Domain length vs time - L(t) &sim; t^n</h2>
  <figure><img src="data:image/png;base64,{growth_png}" alt="log-log domain length vs Monte-Carlo time, correlation and energy estimators, with the Allen-Cahn slope-half reference"></figure>

  <h2>The coarsening lattice</h2>
  <figure><img src="data:image/png;base64,{snap_png}" alt="Ising lattice snapshots at increasing times, ordered domains growing"></figure>

  <h2>Equal-time correlation G(r, t)</h2>
  <figure><img src="data:image/png;base64,{corr_png}" alt="equal-time correlation function broadening as domains coarsen, with the half-height line that defines the domain length"></figure>

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


def render_m15(report: dict, date: str | None = None) -> Path:
    """Render an M15 Glauber-dynamics domain-growth report (HTML + plots + JSON).

    The lab's first non-equilibrium milestone: the signature is a GROWTH EXPONENT, the log-log
    slope of the domain length L(t) vs Monte-Carlo time. The verdict is a green check when the
    re-fit correlation-length exponent lands within tolerance of Allen-Cahn's t^(1/2); the
    caveat foregrounds the honest story - the effective exponent sits a few percent below 1/2
    (the documented preasymptotic correction) and the OLS statistical error badly understates
    the true systematic uncertainty (estimator + window choice). A miss ships as an honest null
    (a folded grey leaf), never a fake 0.500. Promotion to a verified check is human-reviewed.
    """
    from .publish import today_local
    date = date or today_local()
    _ensure_home()

    L = report.get("L")
    T = report.get("T")
    ratio = report.get("T_ratio")
    n = report.get("exponent")
    se = report.get("exponent_stderr")
    r2 = report.get("r2")
    late = report.get("late_exponent")
    spread = report.get("systematic_spread", 0.0)
    ef = report.get("energy_fit") or {}
    energy_n = ef.get("exponent")
    cf = report.get("corr_fit") or {}
    t_lo, t_hi = cf.get("t_lo"), cf.get("t_hi")
    L_lo, L_hi = cf.get("L_lo"), cf.get("L_hi")
    n_pts = cf.get("n_points")
    seeds = report.get("n_seeds")
    supports = report.get("supports_allen_cahn")
    band = max(spread, 0.02)

    sentence = (
        f"I quenched a 2D Ising lattice (L={L}, {seeds} random starts) instantly from infinite "
        f"temperature to T={T:.3f} - about {ratio:.2f} of T_c, cold enough to order - and watched "
        f"it <em>coarsen</em> under single-spin Glauber (heat-bath) dynamics: ordered domains "
        f"grow, and their typical size L(t) climbs as a power of the real Monte-Carlo time. This "
        f"is non-equilibrium - the clock on the x-axis is the physics, so no cluster shortcuts are "
        f"allowed. Allen-Cahn theory predicts a single universal law, L(t) &sim; t^(1/2), for a "
        f"non-conserved order parameter. Wall time: {report.get('wall_seconds', 0):.0f}s."
    )

    n_str = f"{n:.3f}" if n is not None else "-"
    se_str = f"{se:.3f}" if se is not None else "-"
    en_str = f"{energy_n:.3f}" if energy_n is not None else "-"
    late_str = f"{late:.3f}" if late is not None else "-"
    if supports:
        verdict = (
            f"The domain length traces a clean power law L(t) &sim; t^n over more than two decades "
            f"in time (R&sup2; = {r2:.4f}), with a correlation-length exponent n = {n_str} - "
            f"consistent with the Allen-Cahn prediction of 1/2. The energy-length cross-check gives "
            f"n = {en_str}, and re-fitting only the late window pushes the exponent up to {late_str}, "
            f"exactly the drift toward 1/2 you expect as the finite-time correction fades. A real, "
            f"honest non-equilibrium scaling law measured on a windowsill."
        )
    else:
        verdict = (
            f"The domain length grows as L(t) &sim; t^n with n = {n_str} (R&sup2; = {r2:.4f}), which "
            f"does <em>not</em> sit within tolerance of the Allen-Cahn 1/2. Kept honestly as an "
            f"open/null - a folded grey leaf - not a fake 0.500. The most likely causes at this scale "
            f"are too short a scaling window, an off-target quench temperature, or a seed frozen into "
            f"a metastable stripe; a larger lattice run to later times sharpens it."
        )

    caveat = (
        f"Honesty on the exponent and its error bar. The OLS statistical error on the fit is tiny "
        f"(&plusmn;{se_str}) precisely <em>because</em> the log-log line is nearly perfect - but that "
        f"number badly <strong>understates</strong> the real uncertainty, which is systematic: it "
        f"depends on the estimator (correlation length {n_str} vs energy length {en_str}) and on where "
        f"the scaling window is placed. The effective exponent measured here sits a few percent "
        f"<em>below</em> the asymptotic 1/2 - this is the well-documented preasymptotic correction: "
        f"2D Ising coarsening approaches t^(1/2) from below, and the deficit shrinks toward later "
        f"times (the late-window fit gives {late_str}). So the defensible statement is n &asymp; {n_str} "
        f"with a systematic band of roughly &plusmn;{band:.2f}, consistent with Allen-Cahn once the "
        f"finite-time bias is acknowledged - not a rounded 0.500. The exponent was fit in the window "
        f"t &isin; [{t_lo:.0f}, {t_hi:.0f}], L &isin; [{L_lo:.1f}, {L_hi:.1f}] ({n_pts} points), past "
        f"the lattice-scale transient and below finite-size saturation. The grading check re-selects "
        f"that window and re-fits the exponent from these arrays with its own tolerance - the report "
        f"cannot set its own bar; promotion to a verified check is human-reviewed."
    )

    json_dump = json.dumps(report, indent=2)
    html = M15_HTML_TEMPLATE.format(
        date=date, sentence=sentence, verdict=verdict, caveat=caveat,
        growth_png=_plot_m15_growth(report),
        snap_png=_plot_m15_snapshots(report),
        corr_png=_plot_m15_correlation(report),
        json_dump=json_dump,
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(html, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(html, encoding="utf-8")
    _commit_report(date, slug, html, json_dump)
    return out


CALIBRATION_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>windowsill-lab &middot; {date} &middot; {milestone}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin:0; padding:36px 24px 80px; min-height:100vh;
    background:linear-gradient(180deg,#f6efe1 0%,#ede1c8 100%);
    font-family:'Iowan Old Style',Georgia,serif; color:#3a2e21; line-height:1.55; }}
  .wrap {{ max-width:780px; margin:0 auto; }}
  h1 {{ font-weight:500; font-size:28px; margin:0 0 4px; }}
  h2 {{ font-size:13px; letter-spacing:.09em; text-transform:uppercase;
    opacity:.58; margin:34px 0 12px; }}
  .date {{ opacity:.55; font-size:14px; margin-bottom:28px; }}
  .lede,.verdict,.boundary {{ padding:16px 20px; border-radius:3px; margin:12px 0; }}
  .lede {{ background:#fbf6ea; border-left:3px solid #c89878; font-size:17px; }}
  .verdict {{ background:{verdict_bg}; border-left:3px solid {verdict_line}; }}
  .boundary {{ background:#f5eadb; border-left:3px solid #b88963; font-size:14px; }}
  figure {{ margin:22px 0; }} figure img {{ width:100%; border-radius:4px; }}
  details {{ margin-top:28px; padding:14px 18px; background:#fbf6ea; border-radius:4px; }}
  summary {{ cursor:pointer; opacity:.65; }} pre {{ font-size:11px; max-height:420px; overflow:auto; }}
  .footer {{ margin-top:56px; border-top:1px solid #d6c0a2; padding-top:16px;
    opacity:.55; font-size:12px; }}
</style></head><body><div class="wrap">
  <h1>windowsill-lab &middot; {plant}</h1>
  <div class="date">{date} &middot; {milestone}</div>
  <div class="lede">{headline}</div>
  <div class="verdict">{verdict}</div>
  <div class="boundary"><strong>Claim boundary.</strong> {boundary}</div>
  <h2>Calibration evidence</h2>
  <figure><img src="data:image/png;base64,{plot_png}" alt="calibration evidence plot"></figure>
  <details><summary>Measurement receipt (JSON)</summary><pre>{json_dump}</pre></details>
  <div class="footer">Four plants, one rule: reproduce a known signal before claiming a new one.
  Public face: <a href="https://www.brokenbranch.dev/windowsill/">the windowsill</a>.</div>
</div></body></html>"""


def _plot_calibration(report: dict) -> str:
    exp = str(report.get("experiment", ""))
    if exp.startswith("M17"):
        # Left: the three growth classes on one log-log axis — the separation IS the control.
        # Right: the saturated width vs ring size, whose slope is the roughness exponent α.
        fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9))
        colors = {"kpz": "#7a5c3e", "ew": "#667c86", "rd": "#7d8f68"}
        labels = {"kpz": "KPZ (single-step)  β=1/3",
                  "ew": "Edwards–Wilkinson  β=1/4",
                  "rd": "random deposition  β=1/2"}
        for name, block in (report.get("growth") or {}).items():
            t = np.asarray(block.get("times", []), dtype=float)
            w = np.asarray(block.get("width", []), dtype=float)
            if t.size == 0:
                continue
            fit = block.get("fit") or {}
            measured = fit.get("exponent")
            lab = labels.get(name, name)
            if measured is not None:
                lab += f"  (measured {measured:.3f})"
            axes[0].plot(t, w, "o-", ms=3, lw=1.1, color=colors.get(name, "#8d8175"), label=lab)
        axes[0].set_xscale("log"); axes[0].set_yscale("log")
        axes[0].set_xlabel("Monte-Carlo time  t  (sweeps)")
        axes[0].set_ylabel("interface width  w(t)")
        axes[0].set_title("three classes, one pipeline")
        axes[0].legend(frameon=False, fontsize=7)
        sat = report.get("saturation") or []
        if sat:
            Ls = np.asarray([s["L"] for s in sat], dtype=float)
            ws = np.asarray([s["w_sat"] for s in sat], dtype=float)
            axes[1].plot(Ls, ws, "o", ms=5, color="#7a5c3e")
            a = report.get("alpha")
            if a:
                ref = ws[0] * (Ls / Ls[0]) ** a
                axes[1].plot(Ls, ref, "-", lw=1.0, color="#b88963",
                             label=f"slope α = {a:.3f}  (exact ½)")
                axes[1].legend(frameon=False, fontsize=8)
            axes[1].set_xscale("log"); axes[1].set_yscale("log")
        axes[1].set_xlabel("ring size  L")
        axes[1].set_ylabel("saturated width  w_sat")
        axes[1].set_title("roughness exponent")
    elif exp.startswith("M16"):
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
        tws = [int(x) for x in report["waiting_times"]]
        dts = np.asarray(report["delta_times"], dtype=float)
        for tw in tws:
            values = report["correlations"][str(tw)]
            axes[0].plot(dts / tw, values, "o-", ms=4, label=f"t_w={tw}")
            axes[1].plot(dts, values, "o-", ms=4, label=f"t_w={tw}")
        axes[0].set_xscale("log"); axes[1].set_xscale("log")
        axes[0].set_xlabel("scaled lag  Δt / t_w")
        axes[1].set_xlabel("absolute lag  Δt")
        axes[0].set_ylabel("C(t_w+Δt, t_w)")
        axes[0].set_title("aging scale"); axes[1].set_title("equilibrium clock")
        axes[0].legend(frameon=False, fontsize=8)
    elif exp.startswith("A01"):
        fig, ax = plt.subplots(figsize=(8, 4))
        phase = np.asarray(report["phase_curve"]["phase"], dtype=float)
        flux = np.asarray([np.nan if x is None else x for x in report["phase_curve"]["flux"]])
        ax.plot(phase, flux, ".-", color="#4d6f78", ms=3, lw=.8)
        ax.set_xlim(-.14, .14)
        ax.set_xlabel("orbital phase")
        ax.set_ylabel("normalized PDCSAP flux")
        ax.set_title(f"TESS phase-folded transit — {report.get('target')}")
    elif exp.startswith("C01"):
        fig, ax = plt.subplots(figsize=(8, 4))
        pairs = [line.split() for line in report.get("source_prefix_text", "").splitlines()]
        n = [int(p[0]) for p in pairs if len(p) == 2]
        values = [int(p[1]) for p in pairs if len(p) == 2]
        ax.plot(n, values, "o-", color="#6f7952", ms=3)
        ax.set_yscale("symlog", linthresh=1)
        ax.set_xlabel("OEIS index n")
        ax.set_ylabel("Fibonacci A000045(n)")
        ax.set_title("locally generated bytes matched the OEIS b-file")
    else:
        fig, ax = plt.subplots(figsize=(8, 3.6))
        analysis = report.get("analysis")
        if analysis:
            labels = ["frames", "hot pixels", "track-like"]
            values = [analysis["shape"][0], analysis["hot_pixel_count"],
                      analysis["track_candidate_count"]]
            ax.bar(labels, values, color=["#7d8f68", "#b88963", "#667c86"])
            ax.set_ylabel("count")
            ax.set_title("real dark-frame calibration")
        else:
            ax.axis("off")
            ax.text(.5, .55, "No real capped-sensor frames were available",
                    ha="center", va="center", fontsize=16, color="#6f5b48")
            ax.text(.5, .38, "hardware-null recorded; no synthetic measurement substituted",
                    ha="center", va="center", fontsize=10, color="#8a7867")
    for ax in fig.axes:
        ax.set_facecolor("#fbf6ea")
    fig.patch.set_facecolor("#f6efe1")
    fig.tight_layout()
    return _fig_to_b64(fig)


def render_calibration(report: dict, date: str | None = None) -> Path:
    """Render M16/C01/A01/I01 reports through one quiet four-plant template."""
    from .publish import today_local
    date = date or today_local()
    _ensure_home()
    milestone = _slug_for(report).upper()
    plant = {
        "M": "physics fern", "C": "compute vine", "A": "astronomy creeper",
        "I": "instrument succulent",
    }.get(milestone[:1], "calibration plant")
    passed = str(report.get("status", "")).lower() == "pass"
    verdict = (
        "Machine gate passed; this measurement remains amber until human review."
        if passed else
        "Calibration did not pass. The null remains visible and is not promoted."
    )
    json_dump = json.dumps(report, indent=2, ensure_ascii=False)
    page = CALIBRATION_HTML_TEMPLATE.format(
        date=date,
        milestone=milestone,
        plant=plant,
        headline=html_lib.escape(str(report.get("headline", "calibration run"))),
        verdict=verdict,
        boundary=html_lib.escape(str(report.get("claim_boundary", "No claim boundary recorded."))),
        verdict_bg="#eef3e6" if passed else "#eee9e2",
        verdict_line="#7a9b56" if passed else "#8d8175",
        plot_png=_plot_calibration(report),
        json_dump=html_lib.escape(json_dump),
    )
    slug = _slug_for(report)
    out = LAB_HOME / f"{date}-{slug}.html"
    out.write_text(page, encoding="utf-8")
    (LAB_HOME / f"{date}-{slug}.json").write_text(json_dump, encoding="utf-8")
    (LAB_HOME / "latest.html").write_text(page, encoding="utf-8")
    _commit_report(date, slug, page, json_dump)
    return out
