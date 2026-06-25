import argparse
import os
import sys
import webbrowser
from pathlib import Path

# Lightweight commands (open / publish / help) must work without torch or
# matplotlib, so ising/render are imported lazily inside `run`. LAB_HOME is a
# trivial constant we keep here to avoid importing render just for the path.
LAB_HOME = Path.home() / ".lab"


HELP = """lab — a windowsill physics lab.

Usage:
  lab                 run today's experiment and open the report
  lab run             run only — don't open the browser
  lab m02             run M02: finite-size scaling across lattice sizes
  lab m03             run M03: critical-exponent β via magnetization data-collapse
  lab m04             run M04: 2D Ising specific heat — the thermal cross-check of T_c
  lab m05             run M05: triangular-lattice 2D Ising — verify T_c = 4/ln3 ≈ 3.641
  lab m06             run M06: 3D simple-cubic Ising — verify T_c ≈ 4.5115 (Phase 2)
  lab m07             run M07: q-state Potts (q=3..6) — continuous→first-order transition
  lab m08             run M08: 2D XY model — BKT transition via the helicity-modulus jump
  lab open            open the latest report (no run)
  lab web             open your seed-in-the-pot page (web/index.html) locally
  lab publish         write the committed pot.json — feeds the windowsill
  lab backfill        copy ~/.lab history into reports/ under permanent names
  lab verify [IDs]    re-derive verified milestones from their reports (CI gate)
  lab setup           install the nightly job (run → publish → push)
  lab help            show this message

Backfill options (only with `backfill`):
  --dry-run           list what would be written, write nothing

Setup options (only with `setup`):
  --check             pre-flight health check only — install nothing
  --cron              install a cron line instead of a systemd user timer
  --dry-run           show what would happen, write nothing

Publish options (only with `publish`):
  --gist ID           push the snapshot to this public gist (or set POT_GIST_ID)

Knobs (only with `run`):
  --L INT             lattice side length (default 128)
  --t-min FLOAT       lower temperature (default 1.5)
  --t-max FLOAT       upper temperature (default 3.5)
  --n-temps INT       number of temperatures swept in parallel (default 21)
  --sweeps INT        measurement sweeps per lattice (default 40000)
  --burnin INT        burn-in sweeps (default 8000)
  --device STR        'cuda' or 'cpu' (default cuda)
  --seed INT          RNG seed (default 42)

Phase 1 reproduces Onsager's 2D Ising result. Later phases will sweep more
exotic systems. State accumulates under ~/.lab/.
"""


def _parse_run(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=128)
    p.add_argument("--t-min", type=float, default=1.5)
    p.add_argument("--t-max", type=float, default=3.5)
    p.add_argument("--n-temps", type=int, default=21)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m02(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes, e.g. 32,64,128,256,512")
    p.add_argument("--quick", action="store_true",
                   help="cap at L=128 for a faster pass")
    p.add_argument("--t-min", type=float, default=2.27)
    p.add_argument("--t-max", type=float, default=2.40)
    p.add_argument("--n-temps", type=int, default=24)
    p.add_argument("--sweeps", type=int, default=80000)
    p.add_argument("--burnin", type=int, default=30000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m03(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes, e.g. 16,24,32,48")
    p.add_argument("--quick", action="store_true",
                   help="cap at L=32 for a faster pass")
    p.add_argument("--t-min", type=float, default=2.24)
    p.add_argument("--t-max", type=float, default=2.30)
    p.add_argument("--n-temps", type=int, default=24)
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=4000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, near-T_c) or 'metropolis'")
    return p.parse_args(args)


def _parse_m06(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=10,
                   help="lattice side (even; default 10)")
    p.add_argument("--quick", action="store_true",
                   help="L=6, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=4.1)
    p.add_argument("--t-max", type=float, default=4.9)
    p.add_argument("--n-temps", type=int, default=21)
    p.add_argument("--sweeps", type=int, default=8000)
    p.add_argument("--burnin", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m04(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=128,
                   help="lattice side (default 128)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=2.0)
    p.add_argument("--t-max", type=float, default=2.6)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m05(args):
    p = argparse.ArgumentParser(add_help=False)
    # L must be a multiple of 3 for the triangular 3-colour update; 129 is the
    # multiple of 3 nearest the square engine's 128 (ising_tri raises otherwise).
    p.add_argument("--L", type=int, default=129,
                   help="lattice side, must be a multiple of 3 (default 129)")
    p.add_argument("--quick", action="store_true",
                   help="L=48, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=3.3)
    p.add_argument("--t-max", type=float, default=4.0)
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m07(args):
    p = argparse.ArgumentParser(add_help=False)
    # M07 sweeps a per-q window straddling each exact T_c(q)=1/ln(1+√q), so the
    # temperature bounds are derived per q (T_c ± half-window) rather than fixed.
    # The default updater is Wolff (cluster) — single-spin Metropolis is
    # metastably trapped through the Potts transition — so --sweeps/--burnin are
    # counted in *cluster updates* (far fewer needed than Metropolis sweeps).
    # L defaults to 64 (not the 128 of the Ising engines): the Wolff cluster
    # flood costs O(L) BFS passes per update near T_c, so the 4-q sweep is only
    # tractable at L=64 — which already locates every T_c within tolerance (the
    # finite-L shift is absorbed by the per-q tolerances). Pass --L 128 for a
    # sharper single-q run.
    p.add_argument("--L", type=int, default=64,
                   help="lattice side (default 64; Wolff BFS cost scales with L)")
    p.add_argument("--quick", action="store_true",
                   help="L=32, short sweep for a fast sanity pass")
    p.add_argument("--q", type=str, default=None,
                   help="comma-separated q values (default 3,4,5,6)")
    p.add_argument("--half-window", type=float, default=0.12,
                   help="half-width of the per-q T window around T_c (default 0.12)")
    p.add_argument("--n-temps", type=int, default=25)
    p.add_argument("--sweeps", type=int, default=4000,
                   help="Wolff cluster updates per q (default 4000)")
    p.add_argument("--burnin", type=int, default=1500,
                   help="Wolff burn-in cluster updates (default 1500)")
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, default) or 'metropolis' (cross-check)")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m08(args):
    p = argparse.ArgumentParser(add_help=False)
    # M08 sweeps a window straddling the BKT benchmark T_BKT ≈ 0.8929 and locates
    # it from the helicity-modulus jump crossing Υ(T)=(2/π)T — there is NO χ/C peak
    # for this transition. L defaults to 64 (the XY engine is float-angle and uses
    # over-relaxation; L=64 already brackets the crossing within the documented
    # ±0.07 finite-L window). The default Metropolis-plus-over-relaxation updater
    # gives a smooth Υ(T); pass --updater wolff for the hardest near-T_BKT points.
    p.add_argument("--L", type=int, default=64,
                   help="lattice side (default 64)")
    p.add_argument("--quick", action="store_true",
                   help="L=32, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=0.6)
    p.add_argument("--t-max", type=float, default=1.1)
    p.add_argument("--n-temps", type=int, default=26)
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--over-relax", type=int, default=1,
                   help="microcanonical over-relaxation sweeps per Metropolis sweep")
    p.add_argument("--updater", default="metropolis",
                   help="'metropolis' (+ over-relaxation; default) or 'wolff'")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def main(argv=None):
    # Windows consoles default to the cp1252 codec, which can't encode the
    # unicode the CLI prints (→ ✓ · 🌱) or the reports carry — without this,
    # every `lab` invocation crashes with a UnicodeEncodeError. A no-op where
    # stdout is already UTF-8 (Linux/macOS) or isn't reconfigurable (a pipe).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "open"

    if cmd in ("help", "-h", "--help"):
        print(HELP); return 0

    if cmd == "open":
        path = LAB_HOME / "latest.html"
        if not path.exists():
            print("no report yet — run `lab run` first.", file=sys.stderr); return 1
        webbrowser.open(f"file://{path}")
        print(path); return 0

    if cmd == "web":
        from .publish import REPO_ROOT
        path = REPO_ROOT / "web" / "index.html"
        if not path.exists():
            print("web page missing — expected web/index.html", file=sys.stderr); return 1
        webbrowser.open(f"file://{path}")
        print(path); return 0

    if cmd == "publish":
        from . import publish as publish_mod
        gist = None
        if "--gist" in args:
            i = args.index("--gist")
            gist = args[i + 1] if i + 1 < len(args) else None
        path = publish_mod.publish(gist_id=gist)
        print(f"  ✓ snapshot: {path}")
        return 0

    if cmd == "backfill":
        from . import publish as publish_mod
        dry = "--dry-run" in args
        paths = publish_mod.backfill(dry_run=dry)
        verb = "would write" if dry else "wrote"
        for p in paths:
            print(f"  {verb}: {p}")
        print(f"\n{verb} {len(paths)} file(s) into reports/."
              + (" (dry run — nothing written)" if dry else ""))
        return 0

    if cmd == "verify":
        from . import checks
        ids = [a for a in args[1:] if not a.startswith("-")] or None
        results = checks.verify(ids)
        if not results:
            print("no verified milestones to check."); return 0
        mark = {"pass": "✓", "fail": "✗", "unchecked": "·", "no-report": "?"}
        for r in results:
            print(f"  {mark.get(r['status'], '?')} {r['id']} [{r['status']}] — {r['detail']}")
        failed = [r["id"] for r in results if r["status"] == "fail"]
        if failed:
            print(f"\nFAILED: {', '.join(failed)}", file=sys.stderr); return 1
        return 0

    if cmd == "setup":
        from . import setup as setup_mod
        flags = args[1:]
        print("windowsill-lab — pre-flight\n")
        checks = setup_mod.health_checks()
        for c in checks:
            print(f"  {'✓' if c['ok'] else '✗'} {c['name']}: {c['detail']}")
        if "--check" in flags:
            return 0 if all(c["ok"] for c in checks) else 1
        if not all(c["ok"] for c in checks):
            print("\nfix the ✗ above first, or re-run with --check to inspect.", file=sys.stderr)
            return 1
        plan = setup_mod.install(prefer_cron="--cron" in flags, dry_run="--dry-run" in flags)
        print(f"\nnightly job ({plan['method']}): {plan['nightly']}")
        for s in plan["steps"]:
            print(f"  · {s}")
        for n in plan["notes"]:
            print(n)
        print("\nthe windowsill will now grow on its own. 🌱")
        return 0

    if cmd == "m02":
        ns = _parse_m02(args[1:])
        from . import fss
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (32, 64, 128)
        else:
            L_values = fss.DEFAULT_L
        print(f"M02 finite-size scaling · L = {', '.join(map(str, L_values))} · "
              f"{ns.n_temps} temps in [{ns.t_min}, {ns.t_max}] · {ns.sweeps:,} sweeps")

        def _progress(L, curve):
            print(f"  ✓ L={L:<4} χ_max={curve.chi_max:8.1f} at T={curve.T_peak:.3f}"
                  f"  ({curve.wall_seconds:.1f}s)")

        result = fss.run_fss(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=ns.sweeps, n_burnin=ns.burnin, seed=ns.seed, device=ns.device,
            progress=_progress,
        )
        report = fss.to_report(result)
        print(f"  → χ_max ∝ L^{result.slope:.3f}  (theory γ/ν = 7/4 = 1.75, "
              f"R²={result.r2:.4f})  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_fss(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m03":
        ns = _parse_m03(args[1:])
        from . import m03
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (16, 24, 32)
        else:
            L_values = m03.DEFAULT_L
        print(f"M03 data collapse · L = {', '.join(map(str, L_values))} · "
              f"{ns.n_temps} temps in [{ns.t_min}, {ns.t_max}] · {ns.sweeps:,} sweeps "
              f"· {ns.updater}")

        def _progress(L, curve):
            print(f"  ✓ L={L:<4} {len(curve.T)} temps  ({curve.wall_seconds:.1f}s)")

        result = m03.run_m03(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=ns.sweeps, n_burnin=ns.burnin, seed=ns.seed, device=ns.device,
            updater=ns.updater, progress=_progress,
        )
        report = m03.to_report(result)
        print(f"  → β/ν = {result.beta_over_nu_fit:.3f}  (theory 1/8 = "
              f"{m03.BETA_OVER_NU:.3f}, residual={result.collapse_quality:.1e})"
              f"  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m03(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m04":
        ns = _parse_m04(args[1:])
        from . import m04
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M04 2D Ising specific heat · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m04(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m04.run_m04(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m04,
        )
        report = m04.to_report(result)
        print(f"  → C-peak T_c = {result.tc_cv_refined:.3f}  (Onsager exact "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  χ cross-check {result.tc_chi_refined:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m04(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m05":
        ns = _parse_m05(args[1:])
        from . import m05
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M05 triangular-lattice 2D Ising · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m05(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m05.run_m05(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m05,
        )
        report = m05.to_report(result)
        print(f"  → χ-peak T_c = {result.tc_chi_refined:.3f}  (exact 4/ln3 = "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  C cross-check {result.tc_cv_refined:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m05(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m06":
        ns = _parse_m06(args[1:])
        from . import m06
        from . import render as render_mod
        L = 6 if ns.quick else ns.L
        sweeps = 1500 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        print(f"M06 3D simple-cubic Ising · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps (CPU)")

        def _progress(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m06.run_m06(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, progress=_progress,
        )
        report = m06.to_report(result)
        print(f"  → χ-peak T_c = {result.tc_chi_refined:.3f}  (MC benchmark "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)"
              f"  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m06(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m07":
        ns = _parse_m07(args[1:])
        from . import m07
        from . import render as render_mod
        # Quick mode: small lattice + short Wolff burn — a fast sanity pass only.
        L = 32 if ns.quick else ns.L
        sweeps = 1000 if ns.quick else ns.sweeps
        burnin = 400 if ns.quick else ns.burnin
        q_values = (tuple(int(x) for x in ns.q.split(",")) if ns.q else m07.Q_VALUES)
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M07 q-state Potts · L={L} · q={', '.join(map(str, q_values))} · "
              f"{ns.n_temps} temps per q (T_c ± {ns.half_window}) · {sweeps:,} {unit} "
              f"· {ns.updater} on {ns.device}")

        def _progress_m07(qr):
            kind = "1st-order" if qr.q >= 5 else "continuous"
            print(f"  ✓ q={qr.q} ({kind:9}) χ-peak T_c={qr.tc_chi_refined:.3f} "
                  f"(exact {qr.tc_exact:.3f}, rel. err {qr.rel_error*100:.1f}%)  "
                  f"({qr.wall_seconds:.1f}s)")

        result = m07.run_m07(
            L=L, q_values=q_values, n_temps=ns.n_temps, n_sweeps=sweeps,
            n_burnin=burnin, seed=ns.seed, device=ns.device,
            half_window=ns.half_window, updater=ns.updater, progress=_progress_m07,
        )
        report = m07.to_report(result)
        print(f"  → continuous (q≤4) → first-order (q≥5): "
              f"mean χ_max {report['continuous_mean_chi_max']:.0f} (q≤4) "
              f"vs {report['first_order_mean_chi_max']:.0f} (q≥5) — the taller "
              f"first-order spike  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m07(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m08":
        ns = _parse_m08(args[1:])
        from . import m08
        from . import render as render_mod
        # Quick mode: small lattice + short sweep — a fast sanity pass only.
        L = 32 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M08 2D XY model (BKT) · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} {unit} · {ns.updater} on {ns.device}")

        def _progress_m08(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m08.run_m08(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, over_relax=ns.over_relax,
            seed=ns.seed, device=ns.device, updater=ns.updater,
            progress=_progress_m08,
        )
        report = m08.to_report(result)
        if result.tc_crossing is not None:
            print(f"  → Υ(T)=(2/π)T crossing T_BKT = {result.tc_crossing:.3f}  "
                  f"(benchmark {result.tc_benchmark:.4f}, rel. err "
                  f"{result.rel_error*100:.1f}%)  ·  {result.wall_seconds:.0f}s")
        else:
            print(f"  → no crossing of Υ(T) with the (2/π)T jump line on this window "
                  f"(un-equilibrated or window mis-placed)  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m08(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "run" or (cmd not in ("help", "open") and cmd.startswith("--")):
        rest = args if cmd != "run" else args[1:]
        ns = _parse_run(rest)
        from . import ising
        from . import render as render_mod
        cfg = ising.RunConfig(
            L=ns.L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_burnin=ns.burnin, n_sweeps=ns.sweeps, device=ns.device, seed=ns.seed,
        )
        print(f"running Ising on {cfg.device} · L={cfg.L} · {cfg.n_temps} temps · {cfg.n_sweeps:,} sweeps ...")
        result = ising.run(cfg)
        print(f"  ✓ {cfg.n_sweeps:,} sweeps in {result.wall_seconds:.1f}s")
        path = render_mod.render(result)
        print(f"  ✓ report: {path}")
        # A run also waters the seed: refresh the sanitized snapshot (and push
        # it if POT_GIST_ID is set). Best-effort — never let it break a run.
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(gist_id=os.environ.get("POT_GIST_ID"), quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        if cmd != "run":
            webbrowser.open(f"file://{path}")
        return 0

    print(f"unknown command: {cmd!r}\n", file=sys.stderr)
    print(HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
