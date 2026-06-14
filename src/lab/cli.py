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
  lab open            open the latest report (no run)
  lab publish         write the committed pot.json — feeds the windowsill
  lab verify [IDs]    re-derive verified milestones from their reports (CI gate)
  lab setup           install the nightly job (run → publish → push)
  lab help            show this message

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


def main(argv=None):
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

    if cmd == "publish":
        from . import publish as publish_mod
        gist = None
        if "--gist" in args:
            i = args.index("--gist")
            gist = args[i + 1] if i + 1 < len(args) else None
        path = publish_mod.publish(gist_id=gist)
        print(f"  ✓ snapshot: {path}")
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
