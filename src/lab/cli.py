import argparse
import sys
import webbrowser
from datetime import datetime

from . import ising
from . import render as render_mod
from .render import LAB_HOME


HELP = """lab — a windowsill physics lab.

Usage:
  lab                 run today's experiment and open the report
  lab run             run only — don't open the browser
  lab open            open the latest report (no run)
  lab help            show this message

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

    if cmd == "run" or (cmd not in ("help", "open") and cmd.startswith("--")):
        rest = args if cmd != "run" else args[1:]
        ns = _parse_run(rest)
        cfg = ising.RunConfig(
            L=ns.L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_burnin=ns.burnin, n_sweeps=ns.sweeps, device=ns.device, seed=ns.seed,
        )
        print(f"running Ising on {cfg.device} · L={cfg.L} · {cfg.n_temps} temps · {cfg.n_sweeps:,} sweeps ...")
        result = ising.run(cfg)
        print(f"  ✓ {cfg.n_sweeps:,} sweeps in {result.wall_seconds:.1f}s")
        path = render_mod.render(result)
        print(f"  ✓ report: {path}")
        if cmd != "run":
            webbrowser.open(f"file://{path}")
        return 0

    print(f"unknown command: {cmd!r}\n", file=sys.stderr)
    print(HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
