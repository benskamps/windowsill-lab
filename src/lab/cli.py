import argparse
import os
import sys
import webbrowser
from pathlib import Path

from .curriculum import RUNNERS

# Lightweight commands (open / publish / help) must work without torch or
# matplotlib, so ising/render are imported lazily inside `run`. LAB_HOME is a
# trivial constant we keep here to avoid importing render just for the path.
LAB_HOME = Path.home() / ".lab"

# Milestone → runnable ``lab`` subcommand lives in ``curriculum.py`` so the
# scheduler and the public feed expose the same operational truth. M01 is the
# un-prefixed heartbeat; milestones past M15 currently remain on the bench.


def _select_next(milestones):
    """Pick the lowest OPEN milestone and say whether we can run it.

    ``parse_milestones`` already flags exactly one milestone ``status=='open'``
    — the first pending in file order (M-track before the Citizen-Science
    tracks), unless one is explicitly marked ``[>]``. That is the lab's single
    bench: the experiment running now / next. We return its id and whether a
    runner is registered for it. Returns ``(None, False)`` when nothing is open
    (every milestone verified/null) — the caller then falls back to the
    heartbeat. This is pure selection: it reads state and decides, it never runs
    a simulation or edits ``MILESTONES.md``.
    """
    open_ms = next((m for m in milestones if m.get("status") == "open"), None)
    if open_ms is None:
        return None, False
    mid = open_ms["id"]
    return mid, mid in RUNNERS


HELP = """lab — a windowsill physics lab.

Usage:
  lab                 run today's experiment and open the report
  lab run             run only — don't open the browser (the M01 heartbeat)
  lab next            run the lowest OPEN milestone's experiment (heartbeat if none)
  lab next --dry-run  print which milestone `lab next` would run — run nothing
  lab m02             run M02: finite-size scaling across lattice sizes
  lab m03             run M03: critical-exponent β via magnetization data-collapse
  lab m04             run M04: 2D Ising specific heat — the thermal cross-check of T_c
  lab m05             run M05: triangular-lattice 2D Ising — verify T_c = 4/ln3 ≈ 3.641
  lab m06             run M06: 3D simple-cubic Ising — verify T_c ≈ 4.5115 (Phase 2)
  lab m07             run M07: q-state Potts (q=3..6) — continuous→first-order transition
  lab m08             run M08: 2D XY model — BKT transition via the helicity-modulus jump
  lab m09             run M09: 2D Heisenberg — verify NO finite-T order (Mermin–Wagner)
  lab m10             run M10: antiferromagnetic Ising — T_N = Onsager 2.2692 on staggered m_s
  lab m11             run M11: 2D Edwards–Anderson spin glass — P(q) broadens toward T_c=0
  lab m12             run M12: 3D EA spin glass — Binder-cumulant crossing at T_SG≈0.95 (parallel tempering)
  lab m13             run M13: frustrated triangular AFM — residual entropy S0/N≈0.3383 via C/T integration
  lab m14             run M14: random-bond Ising — exact Nishimori-line energy, map toward the MNP p_c≈0.109
  lab m15             run M15: Glauber dynamics — domain growth L(t)∼t^(1/2) after a quench (Phase 4)
  lab m16             run M16: 3D spin-glass aging — compare t/t_w with t−t_w collapse
  lab m17             run M17: KPZ growth on a ring — β=1/3, α=1/2, z=3/2 + Tracy–Widom class
  lab c01             run C01: OEIS byte + Lucas–Lehmer arithmetic calibration
  lab a01             run A01: recover WASP-18 b from official TESS SPOC light curves
  lab i01             run I01: calibrate a real capped-CMOS dark-frame stack
  lab open            open the latest report (no run)
  lab web             open your seed-in-the-pot page (web/index.html) locally
  lab publish         write the committed pot.json — feeds the windowsill
  lab backfill        copy ~/.lab history into reports/ under permanent names
  lab verify [IDs]    re-derive verified milestones from their reports (CI gate)
  lab verify --rerun-smoke
                      also re-run the pinned L=16 CPU smoke config and prove it
                      reproduces itself + the committed golden (determinism gate)
  lab scoreboard      render the calibration scoreboard (measured vs theory) + archive
  lab controls        run published controls: cross-updater agreement + a J=0 null
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
    p.add_argument("--updater", default="wolff",
                   help="'wolff' (cluster, near-T_c; unlocks L≥512) or 'metropolis'")
    p.add_argument("--wolff-init", default="ordered",
                   help="wolff start: 'ordered' (fast burn-in at scale) or 'random'")
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


def _parse_m09(args):
    p = argparse.ArgumentParser(add_help=False)
    # M09 sweeps a *family* of L at a single fixed T and shows the Mermin–Wagner
    # drift ⟨|m|⟩(L) → 0 — there is NO transition and NO T-sweep. L defaults to the
    # {16,32,64} family (already resolves the monotone drift); T=0.7 is moderate
    # (cold enough that small L carries an appreciable, falsifiable ⟨|m|⟩, warm
    # enough that ξ(T) ≪ 64 so the drift is visible without needing L=128+). The
    # default Metropolis-plus-over-relaxation updater (over-relaxation cures the
    # spin-wave critical slowing at the low-T, large-ξ points); --updater wolff
    # uses the embedded-Ising single-cluster move.
    p.add_argument("--L", type=str, default=None,
                   help="comma-separated lattice sizes (default 16,32,64)")
    p.add_argument("--quick", action="store_true",
                   help="L=8,12,16, short sweep for a fast sanity pass")
    p.add_argument("--T", type=float, default=None,
                   help="fixed temperature for the L-family (default 0.7)")
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--over-relax", type=int, default=3,
                   help="microcanonical over-relaxation sweeps per Metropolis sweep")
    p.add_argument("--updater", default="metropolis",
                   help="'metropolis' (+ over-relaxation; default) or 'wolff'")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m10(args):
    p = argparse.ArgumentParser(add_help=False)
    # M10 reuses M01/M04's setup — J = −1 (antiferromagnetic) and the STAGGERED
    # order parameter — over a window straddling the Néel point T_N = Onsager's
    # exact 2.2692 (the bipartite gauge duality makes the AFM the FM in disguise).
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


def _parse_m11(args):
    p = argparse.ArgumentParser(add_help=False)
    # M11 sweeps a T-window down toward T = 0 (the 2D EA glass orders only at T = 0
    # — no finite-T transition) and shows the disorder-averaged P(q) broadening as T
    # falls. It batches realizations × temperatures × 2 replicas in one GPU pass; the
    # disorder average over MANY realizations is mandatory. L is modest (spin glasses
    # are expensive and the overlap needs two replicas each). The default cold edge is
    # T=0.6: below ≈0.5–0.6 single-spin Metropolis can't equilibrate the L=16 glass in
    # tractable time (the coldest points fall into an under-equilibration dip — the
    # reason parallel tempering exists), so the trustworthy window starts at the floor
    # and the broadening trend toward T=0 is the claim, the un-equilibrable tail is not.
    p.add_argument("--L", type=int, default=16,
                   help="lattice side (default 16; spin glasses are expensive)")
    p.add_argument("--quick", action="store_true",
                   help="L=8, few realizations, short sweep for a fast sanity pass")
    p.add_argument("--t-min", type=float, default=0.6,
                   help="cold edge (default 0.6 — the single-spin-Metropolis equilibration floor)")
    p.add_argument("--t-max", type=float, default=2.0)
    p.add_argument("--n-temps", type=int, default=16)
    p.add_argument("--realizations", type=int, default=64,
                   help="quenched ±J disorder realizations to average P(q) over")
    p.add_argument("--sweeps", type=int, default=60000)
    p.add_argument("--burnin", type=int, default=30000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m12(args):
    p = argparse.ArgumentParser(add_help=False)
    # M12 is the 3D EA glass: a genuine finite-T spin-glass transition at T_SG ≈ 0.95,
    # found by the disorder-averaged Binder-cumulant CROSSING across ≥3 lattice sizes on
    # a SHARED T ladder that straddles 0.95. Parallel tempering is mandatory — single-
    # spin Metropolis can't equilibrate the cold rungs and the crossing washes out (M11's
    # documented failure mode). --quick runs a small CPU pass that proves the code end to
    # end but does not generally resolve the crossing (that needs a GPU run with many
    # disorder realizations); it then ships an honest [~] null, per the lab's convention.
    p.add_argument("--L-values", default="4,6,8",
                   help="comma-separated even lattice sizes on the shared ladder (default 4,6,8)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (few realizations, short sweep) — proves the code, not the physics")
    p.add_argument("--t-min", type=float, default=0.4,
                   help="cold edge — must sit below T_SG≈0.95 (default 0.4)")
    p.add_argument("--t-max", type=float, default=1.6,
                   help="hot edge — the ergodic end parallel tempering decorrelates in (default 1.6)")
    p.add_argument("--n-temps", type=int, default=16)
    p.add_argument("--realizations", type=int, default=200,
                   help="quenched ±J disorder realizations to average the Binder cumulant over")
    p.add_argument("--sweeps", type=int, default=20000)
    p.add_argument("--burnin", type=int, default=10000)
    p.add_argument("--swap-every", type=int, default=10,
                   help="attempt a parallel-tempering even/odd swap round every N sweeps")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m13(args):
    p = argparse.ArgumentParser(add_help=False)
    # M13 is the frustrated triangular antiferromagnet (J=−1): NO ordering transition, a
    # macroscopically degenerate ground state, and the signature is the residual entropy
    # S0/N = 0.3383 k_B (Wannier), measured by integrating C(T)/T from S(∞)=ln2 down. So
    # the window is WIDE (near T=0 up to high T where S→ln2), not a tight peak straddle,
    # and the grid is geometric — packed into the low-T hump where C/T carries its weight.
    # L must be a multiple of 3 (the triangular 3-colour update's periodic seam).
    p.add_argument("--L", type=int, default=96,
                   help="lattice side, a multiple of 3 (default 96)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=24, short sweep) — proves the pipeline end to end")
    p.add_argument("--t-min", type=float, default=0.10,
                   help="cold edge — near T=0 to expose the residual (default 0.10)")
    p.add_argument("--t-max", type=float, default=14.0,
                   help="hot edge — high enough that S climbs back to ln2 (default 14.0)")
    p.add_argument("--n-temps", type=int, default=80,
                   help="geometric temperature-grid points (default 80)")
    p.add_argument("--sweeps", type=int, default=40000)
    p.add_argument("--burnin", type=int, default=8000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m14(args):
    p = argparse.ArgumentParser(add_help=False)
    # M14 is the random-bond Ising model swept along its Nishimori line (tanh(1/T)=1−2p).
    # The VERIFIED claim is the exact Nishimori-line energy E/N = −2 tanh(1/T); the sweep
    # also maps the ferro-order collapse toward the multicritical point p_c≈0.109 (only
    # approximately at this scale). L defaults to a two-size (12,24) map, the larger of
    # which grades the energy; the ±J disorder is averaged over many realizations. --quick
    # runs a small CPU pass that proves the pipeline end to end.
    p.add_argument("--L-values", default="12,24",
                   help="comma-separated map lattice sizes; the largest grades the energy (default 12,24)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=8,12, few realizations, short sweep) — proves the pipeline")
    p.add_argument("--p-values", default=None,
                   help="comma-separated AF-bond fractions along the Nishimori line "
                        "(default 0.04,0.06,0.08,0.10,0.1094,0.12,0.14,0.16)")
    p.add_argument("--realizations", type=int, default=64,
                   help="quenched ±J disorder realizations to average over")
    p.add_argument("--sweeps", type=int, default=10000)
    p.add_argument("--burnin", type=int, default=4000)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m15(args):
    p = argparse.ArgumentParser(add_help=False)
    # M15 is NON-equilibrium: a single lattice quenched from T=inf to T<T_c, evolved under
    # single-spin Glauber (heat-bath) dynamics — cluster updates are FORBIDDEN, they destroy
    # the coarsening. There is no temperature sweep; T is the fixed quench target (default
    # ~0.66·T_c). The x-axis is Monte-Carlo time (sweeps). L defaults to 512 (a large box so
    # domains grow over a wide window before finite-size saturation); n_seeds averages several
    # random starts. --quick runs a small CPU pass that proves the pipeline end to end.
    p.add_argument("--L", type=int, default=512,
                   help="lattice side (default 512; bigger box = wider scaling window)")
    p.add_argument("--quick", action="store_true",
                   help="small CPU pass (L=96, few seeds, short time) — proves the pipeline")
    p.add_argument("--T", type=float, default=None,
                   help="quench temperature < T_c (default ~0.66·T_c ≈ 1.498)")
    p.add_argument("--seeds", type=int, default=48,
                   help="independent random initial conditions, averaged (default 48)")
    p.add_argument("--t-max", type=int, default=8000,
                   help="final Monte-Carlo time in sweeps (default 8000)")
    p.add_argument("--n-times", type=int, default=52,
                   help="log-spaced measurement times (default 52)")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m16(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--L", type=int, default=12)
    p.add_argument("--quick", action="store_true",
                   help="small CPU aging pass for pipeline validation")
    p.add_argument("--T", type=float, default=0.60)
    p.add_argument("--realizations", type=int, default=64)
    p.add_argument("--waiting-times", default="16,32,64,128")
    p.add_argument("--delta-times", default="8,16,32,64,128,256")
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_m17(args):
    p = argparse.ArgumentParser(add_help=False)
    # M17 is NON-equilibrium and watches a SURFACE, not spins: a 1+1d interface grown on a
    # periodic ring. There is no temperature — the control parameter is the corner-flip
    # probability p, which must stay strictly inside (0,1) (at p=1 the sublattice-parallel
    # rule is deterministic and stops being stochastically rough, i.e. stops being KPZ).
    # The x-axis is Monte-Carlo time. L must be large enough that the ring never saturates
    # inside t_max (the runner asserts w(t_max) ≤ 0.20·√L). --quick proves the pipeline on CPU.
    p.add_argument("--L", type=int, default=4096,
                   help="KPZ ring size (default 4096; bigger ring = later saturation)")
    p.add_argument("--quick", action="store_true",
                   help="small fast pass — proves growth + controls + distributions end to end")
    p.add_argument("--batch", type=int, default=64,
                   help="independent rings averaged for the width (default 64)")
    p.add_argument("--t-max", type=int, default=8000,
                   help="final Monte-Carlo time in sweeps for the KPZ run (default 8000)")
    p.add_argument("--n-times", type=int, default=44,
                   help="log-spaced measurement sweeps (default 44)")
    p.add_argument("--dist-t", type=int, default=400,
                   help="sweeps for the Tracy-Widom distribution runs (default 400)")
    p.add_argument("--droplet-batch", type=int, default=6000,
                   help="independent droplets sampled for the GUE test (default 6000)")
    p.add_argument("--flat-batch", type=int, default=3000,
                   help="independent flat rings sampled for the GOE test (default 3000)")
    p.add_argument("--p-flip", type=float, default=0.5,
                   help="corner-flip probability, strictly in (0,1) (default 0.5)")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(args)


def _parse_c01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--terms", type=int, default=40)
    return p.parse_args(args)


def _parse_a01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--sectors", type=int, default=8,
                   help="maximum number of official SPOC sectors (default 8)")
    p.add_argument("--cache-dir", default=None,
                   help="optional FITS cache; defaults to ~/.lab/cache/a01")
    return p.parse_args(args)


def _parse_i01(args):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--frames", default=None,
                   help="real .npy/.npz dark stack or directory of 2-D .npy frames")
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
        rerun_smoke = "--rerun-smoke" in args
        bless = "--bless" in args
        ids = [a for a in args[1:] if not a.startswith("-")] or None
        results = checks.verify(ids)
        rc = 0
        if results:
            mark = {"pass": "✓", "fail": "✗", "unchecked": "·", "no-report": "?"}
            for r in results:
                print(f"  {mark.get(r['status'], '?')} {r['id']} [{r['status']}] — {r['detail']}")
            blocked = [r for r in results if r["status"] != "pass"]
            if blocked:
                summary = ", ".join(f"{r['id']} ({r['status']})" for r in blocked)
                print(f"\nVERIFICATION INCOMPLETE: {summary}", file=sys.stderr)
                print("Every promoted milestone must have a registered check and a readable passing report.",
                      file=sys.stderr)
                rc = 1
        elif not rerun_smoke:
            print("no verified milestones to check.", file=sys.stderr)
            return 1

        if bless and not rerun_smoke:
            print("--bless only applies with --rerun-smoke.", file=sys.stderr)
            return 2

        if rerun_smoke:
            from . import determinism
            if bless:
                path = determinism.write_golden()
                print(f"  ✓ blessed determinism golden → {path}")
                return 0
            gate = determinism.run_gate()
            glyph = "✓" if gate["ok"] else "✗"
            print(f"  {glyph} determinism (golden-seed L=16 smoke, {gate['golden']}) — {gate['detail']}")
            if not gate["ok"]:
                print("\nDETERMINISM GATE FAILED: the pinned CPU smoke run did not reproduce.",
                      file=sys.stderr)
                rc = 1
        return rc

    if cmd == "scoreboard":
        from . import scoreboard as scoreboard_mod
        from . import archive as archive_mod
        entries = scoreboard_mod.collect_entries()
        png = scoreboard_mod.write_scoreboard(entries=entries)
        n_pass = sum(1 for e in entries if e.passed)
        print(f"  ✓ scoreboard: {len(entries)} milestones, {n_pass} within tolerance → {png}")
        for e in entries:
            mark = "✓" if e.passed else "✗"
            print(f"    {mark} {e.milestone} {e.observable}: {e.value_label()}  (z={e.z:+.2f})")
        index = archive_mod.write_index()
        print(f"  ✓ embedded into {index}")
        if "--open" in args:
            webbrowser.open(index.as_uri())
        return 0 if n_pass == len(entries) else 1

    if cmd == "controls":
        import json as _json
        from . import controls as controls_mod
        from . import checks
        from .publish import today_local
        rep = controls_mod.build_controls_report()
        ok, detail = checks.check_controls(rep)
        # The receipt lands in ~/.lab (not the committed archive): a published control
        # that would ride into pot.json is a separate promotion step.
        LAB_HOME.mkdir(parents=True, exist_ok=True)
        out = LAB_HOME / f"{today_local()}-controls.json"
        out.write_text(_json.dumps(rep, indent=2), encoding="utf-8")
        print(f"  {'✓' if ok else '✗'} controls — {detail}")
        print(f"  receipt: {out}")
        return 0 if ok else 1

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
        if "--dry-run" in flags:
            print("\ndry run complete — nothing was written or scheduled.")
        else:
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
        unit = "cluster updates" if ns.updater == "wolff" else "sweeps"
        print(f"M02 finite-size scaling · L = {', '.join(map(str, L_values))} · "
              f"{ns.n_temps} temps in [{ns.t_min}, {ns.t_max}] · {ns.sweeps:,} {unit} "
              f"· {ns.updater} on {ns.device}")

        def _progress(L, curve):
            print(f"  ✓ L={L:<4} χ_max={curve.chi_max:8.1f} at T={curve.T_peak:.3f}"
                  f"  ({curve.wall_seconds:.1f}s)")

        result = fss.run_fss(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=ns.sweeps, n_burnin=ns.burnin, seed=ns.seed, device=ns.device,
            updater=ns.updater, wolff_init=ns.wolff_init, progress=_progress,
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

    if cmd == "m09":
        ns = _parse_m09(args[1:])
        from . import m09
        from . import render as render_mod
        if ns.L:
            L_values = tuple(int(x) for x in ns.L.split(","))
        elif ns.quick:
            L_values = (8, 12, 16)
        else:
            L_values = m09.DEFAULT_L
        T = ns.T if ns.T is not None else m09.DEFAULT_T
        sweeps = 2000 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        print(f"M09 2D Heisenberg (Mermin–Wagner) · L = {', '.join(map(str, L_values))} "
              f"at T={T} · {sweeps:,} sweeps · {ns.updater} on {ns.device}")

        def _progress_m09(L, r):
            print(f"  ✓ L={L:<4} ⟨|m|⟩={r.abs_mag[0]:.4f} ± {r.abs_mag_err[0]:.4f}  "
                  f"E={r.energy[0]:.3f}  accept={r.acceptance[0]:.3f}  ({r.wall_seconds:.1f}s)")

        result = m09.run_m09(
            L_values=L_values, T=T, n_sweeps=sweeps, n_burnin=burnin,
            over_relax=ns.over_relax, seed=ns.seed, device=ns.device,
            updater=ns.updater, progress=_progress_m09,
        )
        report = m09.to_report(result)
        ratio_str = " → ".join(f"{r:.3f}" for r in result.ratios) or "—"
        verdict = ("Mermin–Wagner confirmed (no finite-T order)"
                   if result.monotone_decreasing else "absence NOT reproduced")
        print(f"  → ⟨|m|⟩ drifts {', '.join(f'{m:.3f}' for m in result.abs_mag)} "
              f"(ratios {ratio_str}, slope vs 1/L = {result.slope_vs_inv_L:+.3f}) — "
              f"{verdict}  ·  {result.wall_seconds:.0f}s total")
        path = render_mod.render_m09(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m10":
        ns = _parse_m10(args[1:])
        from . import m10
        from . import render as render_mod
        L = 48 if ns.quick else ns.L
        sweeps = 4000 if ns.quick else ns.sweeps
        burnin = 1500 if ns.quick else ns.burnin
        print(f"M10 antiferromagnetic Ising (J=−1) · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {sweeps:,} sweeps on {ns.device}")

        def _progress_m10(result):
            print(f"  ✓ swept {len(result.T)} temps  ({result.wall_seconds:.1f}s)")

        result = m10.run_m10(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=ns.device,
            progress=_progress_m10,
        )
        report = m10.to_report(result)
        print(f"  → staggered χ_s-peak T_N = {result.tc_chi_refined:.3f}  (Onsager exact "
              f"{result.tc_benchmark:.4f}, rel. err {result.rel_error*100:.1f}%)  ·  "
              f"C cross-check {result.tc_cv_refined:.3f}  ·  uniform ⟨|m|⟩ ≤ "
              f"{result.max_abs_mag:.3f}  ·  {result.wall_seconds:.0f}s")
        path = render_mod.render_m10(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m11":
        ns = _parse_m11(args[1:])
        from . import m11
        from . import render as render_mod
        L = 8 if ns.quick else ns.L
        realizations = 8 if ns.quick else ns.realizations
        sweeps = 2000 if ns.quick else ns.sweeps
        burnin = 800 if ns.quick else ns.burnin
        print(f"M11 2D Edwards–Anderson spin glass · L={L} · {ns.n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] · {realizations} disorder realizations × 2 "
              f"replicas · {sweeps:,} sweeps on {ns.device}")

        def _progress_m11(result):
            print(f"  ✓ swept {len(result.T)} temps × {result.n_realizations} "
                  f"realizations  ({result.wall_seconds:.1f}s)")

        result = m11.run_m11(
            L=L, T_min=ns.t_min, T_max=ns.t_max, n_temps=ns.n_temps,
            n_realizations=realizations, n_sweeps=sweeps, n_burnin=burnin,
            seed=ns.seed, device=ns.device, progress=_progress_m11,
        )
        report = m11.to_report(result)
        verdict = ("P(q) broadens toward T=0" if result.monotone_broadening
                   else "broadening NOT clean — see report")
        print(f"  → ⟨q²⟩ grows {result.q2_hot:.3f} → {result.q2_cold:.3f} as T→0 "
              f"({result.broadening_fraction*100:.0f}% of steps) · max|⟨q⟩|="
              f"{result.max_abs_q_mean:.3f} · {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m11(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m12":
        ns = _parse_m12(args[1:])
        from . import m12
        from . import render as render_mod
        L_values = [int(x) for x in ns.L_values.split(",") if x.strip()]
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end-to-end and writes
            # HTML+JSON. It will not generally resolve the crossing — that is the GPU
            # full run's job — so an unresolved crossing here ships as an honest null.
            L_values = [4, 6, 8]
            realizations, n_temps = 8, 10
            sweeps, burnin, swap_every = 800, 400, 5
            device = "cpu"
        else:
            realizations, n_temps = ns.realizations, ns.n_temps
            sweeps, burnin, swap_every = ns.sweeps, ns.burnin, ns.swap_every
        print(f"M12 3D Edwards–Anderson spin glass · L={L_values} · {n_temps} temps in "
              f"[{ns.t_min}, {ns.t_max}] straddling T_SG≈0.95 · {realizations} disorder "
              f"realizations × 2 replicas · parallel tempering (swap every {swap_every}) "
              f"· {sweeps:,} sweeps on {device}")

        def _progress_m12(L, r):
            print(f"  ✓ L={L:<3} swept {len(r.T)} temps  (swap≈{r.swap_rate.mean():.2f}, "
                  f"{r.wall_seconds:.1f}s)")

        result = m12.run_m12(
            L_values=L_values, T_min=ns.t_min, T_max=ns.t_max, n_temps=n_temps,
            n_realizations=realizations, n_sweeps=sweeps, n_burnin=burnin,
            swap_every=swap_every, seed=ns.seed, device=device, progress=_progress_m12,
        )
        report = m12.to_report(result)
        ct = result.crossing_T
        ct_str = f"{ct:.3f}" if ct is not None else "none"
        verdict = ("Binder crossing at T_SG≈%s — the finite-T 3D glass transition" % ct_str
                   if result.crossing_resolved
                   else "no clean crossing near 0.95 — honest [~] null (needs the GPU full run)")
        print(f"  → Binder crossing T_SG = {ct_str} (benchmark {result.t_sg_benchmark:.2f} "
              f"± {result.tolerance:.2f}) · max|⟨q⟩|={result.max_abs_q_mean:.3f} · "
              f"{verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m12(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m13":
        ns = _parse_m13(args[1:])
        from . import m13
        from . import render as render_mod
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end-to-end and writes
            # HTML+JSON. The frustrated model equilibrates easily (single-spin flips walk
            # the degenerate ground manifold), so even this coarse grid usually lands the
            # integrated residual near 0.3383 — but a miss here still ships an honest null.
            L, n_temps = 24, 40
            t_min, t_max = 0.15, 12.0
            sweeps, burnin = 3000, 1000
            device = "cpu"
        else:
            L, n_temps = ns.L, ns.n_temps
            t_min, t_max = ns.t_min, ns.t_max
            sweeps, burnin = ns.sweeps, ns.burnin
            device = ns.device
        print(f"M13 frustrated triangular antiferromagnet · L={L} · {n_temps} geometric "
              f"temps in [{t_min}, {t_max}] · {sweeps:,} sweeps on {device} · integrating "
              f"C(T)/T → residual entropy vs Wannier 0.3383")

        def _progress_m13(result):
            print(f"  ✓ swept {len(result.T)} temps  (ground energy {result.e_ground:.4f}, "
                  f"{result.wall_seconds:.1f}s)")

        result = m13.run_m13(
            L=L, T_min=t_min, T_max=t_max, n_temps=n_temps,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=device,
            progress=_progress_m13,
        )
        report = m13.to_report(result)
        verdict = ("residual entropy reproduced — Wannier 0.3383" if result.resolved
                   else "integrated residual off 0.3383 — honest [~] null")
        print(f"  → residual S0/N = {result.s0_measured:.4f} (Wannier {result.s0_benchmark:.4f}, "
              f"Δ={result.s0_abs_error:.4f}) · ground energy {result.e_ground:.4f}/spin (exact −1) "
              f"· {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m13(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m14":
        ns = _parse_m14(args[1:])
        from . import m14
        from . import render as render_mod
        L_values = tuple(int(x) for x in ns.L_values.split(",") if x.strip())
        p_values = (tuple(float(x) for x in ns.p_values.split(",") if x.strip())
                    if ns.p_values else
                    (0.04, 0.06, 0.08, 0.10, 0.1094, 0.12, 0.14, 0.16))
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the multi-file recipe end to end and writes HTML+JSON.
            # The Nishimori-line energy is an exact identity, so even this coarse pass usually
            # reproduces it; a miss still ships an honest null.
            L_values = (8, 12)
            p_values = (0.05, 0.10, 0.1094, 0.15)
            realizations, sweeps, burnin = 16, 3000, 1200
            device = "cpu"
        else:
            realizations, sweeps, burnin = ns.realizations, ns.sweeps, ns.burnin
        print(f"M14 random-bond Ising (Nishimori line) · L={list(L_values)} · "
              f"p={', '.join(f'{p:.3f}' for p in p_values)} · {realizations} disorder "
              f"realizations · {sweeps:,} sweeps on {device} · verifying E/N = −2 tanh(1/T)")

        def _progress_m14(L, p, r):
            print(f"  ✓ L={L:<3} p={p:.4f} T_NL={r.T:.4f}  E={r.energy:.4f} "
                  f"(exact {r.energy_exact_nl:.4f}, Δ={abs(r.energy-r.energy_exact_nl):.4f}) "
                  f"|m|={r.abs_mag:.3f}  ({r.wall_seconds:.1f}s)")

        result = m14.run_m14(
            p_values=p_values, L_values=L_values, n_realizations=realizations,
            n_sweeps=sweeps, n_burnin=burnin, seed=ns.seed, device=device,
            progress=_progress_m14,
        )
        report = m14.to_report(result)
        ph = result.mnp_order_p_half
        ph_str = f"p≈{ph:.3f}" if ph is not None else "unresolved"
        verdict = ("exact Nishimori-line energy reproduced" if result.energy_resolved
                   else "Nishimori-line energy off — honest [~] null")
        print(f"  → max energy Δ = {result.max_energy_dev:.4f} vs exact −2 tanh(1/T) "
              f"(L={result.gate_L}) · ferro order collapses near {ph_str} "
              f"(MNP p_c≈{result.p_c_benchmark:.4f}) · {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m14(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m15":
        ns = _parse_m15(args[1:])
        from . import m15
        from . import render as render_mod
        device = ns.device
        if ns.quick:
            # A small CPU pass: proves the quench → measure → fit → report pipeline end to end
            # and writes HTML+JSON. The scaling window is short at this scale, so the exponent
            # is coarse — a miss still ships an honest null, per the lab's convention.
            L, seeds, t_max, n_times = 96, 8, 1500, 32
            device = "cpu"
        else:
            L, seeds, t_max, n_times = ns.L, ns.seeds, ns.t_max, ns.n_times
        from .onsager import T_C as _TC
        T = ns.T if ns.T is not None else 0.66 * float(_TC)
        print(f"M15 Glauber domain growth · L={L} · quench T={T:.3f} ({T/float(_TC):.2f}·T_c) · "
              f"{seeds} seeds · t_max={t_max:,} sweeps on {device} · fitting L(t)∼t^n vs "
              f"Allen–Cahn ½ (single-spin heat-bath — NO cluster updates)")

        def _progress_m15(result):
            print(f"  ✓ measured {len(result.times)} times  (n={result.exponent:.3f}, "
                  f"R²={result.r2:.4f}, {result.wall_seconds:.1f}s)")

        result = m15.run_m15(
            L=L, T=ns.T, n_seeds=seeds, t_max=t_max, n_times=n_times,
            seed=ns.seed, device=device, progress=_progress_m15,
        )
        report = m15.to_report(result)
        energy_n = result.energy_fit.exponent if result.energy_fit is not None else None
        en_str = f"{energy_n:.3f}" if energy_n is not None else "—"
        verdict = ("consistent with Allen–Cahn t^(1/2)" if result.supports_allen_cahn
                   else "off the Allen–Cahn ½ — honest [~] null")
        print(f"  → growth exponent n = {result.exponent:.3f} ± {result.exponent_stderr:.3f} "
              f"(stat) · energy-length cross-check {en_str} · systematic band "
              f"±{max(result.systematic_spread, 0.02):.2f} · {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_m15(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            snap = publish_mod.publish(quiet=True)
            print(f"  ✓ snapshot: {snap}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m16":
        ns = _parse_m16(args[1:])
        from . import m16
        from . import render as render_mod
        waiting = [int(x) for x in ns.waiting_times.split(",") if x.strip()]
        deltas = [int(x) for x in ns.delta_times.split(",") if x.strip()]
        L, realizations, device = ns.L, ns.realizations, ns.device
        if ns.quick:
            L, realizations, device = 6, 8, "cpu"
            waiting, deltas = [4, 8, 16], [2, 4, 8, 16, 32]
        print(f"M16 3D ±J spin-glass aging · L={L} · T={ns.T:.2f} · "
              f"{realizations} disorder realizations · t_w={waiting} · Δt={deltas} "
              f"on {device} (single-spin clock; no cluster/PT shortcuts)")

        def _progress_m16(sweep, last):
            print(f"  · clock {sweep:>4}/{last} sweeps")

        result = m16.run_m16(
            L=L, T=ns.T, n_realizations=realizations, waiting_times=waiting,
            delta_times=deltas, seed=ns.seed, device=device, progress=_progress_m16,
        )
        report = m16.to_report(result)
        print(f"  → ratio-collapse residual = {result.collapse_ratio:.2f}× fixed-lag "
              f"residual · ΔC={result.fixed_lag_separation:+.3f} at Δt={result.fixed_lag} · "
              f"{'aging resolved' if result.aging_resolved else 'honest null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "m17":
        ns = _parse_m17(args[1:])
        from . import m17
        from . import render as render_mod
        if ns.quick:
            # A small pass: proves growth → controls → saturation → both geometries → report
            # end to end and writes HTML+JSON. The scaling window and the sample sizes are
            # short at this scale, so the exponents are coarse and the third moments noisy —
            # a miss still ships an honest null, per the lab's convention.
            kw = dict(L=1024, batch=16, t_max=600, n_times=24,
                      ew_L=512, ew_t_max=300, rd_L=512, rd_t_max=300,
                      sat_L=(8, 16, 32), sat_batch=16,
                      dist_t=60, droplet_batch=400, flat_L=512, flat_batch=300, flat_sites=4)
        else:
            kw = dict(L=ns.L, batch=ns.batch, t_max=ns.t_max, n_times=ns.n_times,
                      dist_t=ns.dist_t, droplet_batch=ns.droplet_batch,
                      flat_batch=ns.flat_batch)
        print(f"M17 KPZ growth on a ring · L={kw['L']} · {kw['batch']} rings · "
              f"t_max={kw['t_max']:,} sweeps · p={ns.p_flip} · fitting β vs the exact KPZ 1/3, "
              f"with Edwards–Wilkinson (¼) and random deposition (½) as negative controls "
              f"on the same pipeline")

        result = m17.run_m17(p=ns.p_flip, seed=ns.seed, progress=lambda m: print(f"  · {m}"), **kw)
        report = m17.to_report(result)
        ew_b = (result.growth["ew"]["fit"] or {}).get("exponent")
        rd_b = (result.growth["rd"]["fit"] or {}).get("exponent")
        print(f"  → β = {result.beta:.4f} ± {result.beta_stderr:.4f} (stat) vs exact 1/3 · "
              f"α = {result.alpha:.4f} vs ½ · z = {result.z:.3f} vs 3/2 · "
              f"1/z = {result.inv_z:.3f} vs 2/3")
        print(f"  → controls: EW β={ew_b:.4f} (exact ¼) · RD β={rd_b:.4f} (exact ½), "
              f"w² within {100 * result.rd_exact['max_rel_dev']:.1f}% of the exact p(1−p)t · "
              f"{'separated' if result.controls_separate else 'CONTROL FAILED'}")
        for ic, a in result.assignments.items():
            print(f"  → {ic:>7}: skew {a['skewness']:+.4f} → nearer {a['nearer']} "
                  f"(expected {a['expected']}, {a['decisiveness']:.1f}×) "
                  f"{'✓' if a['correct'] else '✗'}")
        verdict = ("KPZ exponents + Tracy–Widom assignment reproduced"
                   if report["status"] == "pass" else "honest [~] null — see the report")
        print(f"  → {verdict} · {result.wall_seconds:.0f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001 — publishing must never fail a run
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "c01":
        ns = _parse_c01(args[1:])
        from . import c01
        from . import render as render_mod
        print(f"C01 arithmetic calibration · OEIS A000045 first {ns.terms} terms · "
              "Lucas–Lehmer for 2^31−1")
        result = c01.run_c01(n_terms=ns.terms)
        report = c01.to_report(result)
        print(f"  → OEIS bytes {'match' if result.bfile_exact_match else 'DO NOT match'} · "
              f"Lucas–Lehmer residue={result.lucas_lehmer_residue} · "
              f"{'calibrated' if result.calibration_passed else 'honest null'} · "
              f"{result.wall_seconds:.2f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "a01":
        ns = _parse_a01(args[1:])
        from . import a01
        from . import render as render_mod
        cache = Path(ns.cache_dir) if ns.cache_dir else a01.CACHE_DIR
        print(f"A01 archive photometry · {a01.TARGET_NAME} / TIC {a01.TIC_ID} · "
              f"up to {ns.sectors} official TESS SPOC sectors")

        def _progress_a01(done, total, product):
            source = "cache" if product["cached"] else "MAST"
            print(f"  ✓ sector {product['sector']:<3} {product['bytes']/1e6:.1f} MB from {source} "
                  f"({done}/{total})")

        result = a01.run_a01(max_sectors=ns.sectors, cache_dir=cache,
                             progress=_progress_a01)
        report = a01.to_report(result)
        print(f"  → P={result.period_days:.8f} d (Δ={result.period_error_days:.2g} d) · "
              f"depth={100*result.depth_fraction:.3f}% "
              f"(Δ={100*result.depth_error_fraction:.3f}%) · "
              f"{sum(result.kept_transits)} timed transits · "
              f"{'calibrated' if result.calibration_passed else 'honest null'} · "
              f"{result.wall_seconds:.1f}s")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "i01":
        ns = _parse_i01(args[1:])
        from . import i01
        from . import render as render_mod
        print("I01 CMOS particle-detector calibration · real capped-sensor dark frames only")
        result = i01.run_i01(frames_path=ns.frames)
        report = i01.to_report(result)
        if result.analysis:
            print(f"  → {result.analysis['shape'][0]} frames · "
                  f"{result.analysis['hot_pixel_count']} hot pixels · "
                  f"{result.analysis['track_candidate_count']} track-like components · "
                  f"{'calibrated' if result.calibration_passed else 'honest null'}")
        else:
            print(f"  → hardware-null: {result.reason}")
        path = render_mod.render_calibration(report)
        print(f"  ✓ report: {path}")
        try:
            from . import publish as publish_mod
            print(f"  ✓ snapshot: {publish_mod.publish(quiet=True)}")
        except Exception as e:  # noqa: BLE001
            print(f"  (snapshot skipped: {e})")
        return 0

    if cmd == "next":
        # Milestone-aware scheduler: run the LOWEST OPEN milestone's experiment,
        # falling back to the M01 heartbeat when the open milestone has no runner
        # yet (M14+) or nothing is open. Selection is read-only — it never edits
        # MILESTONES.md; a milestone is only marked done by the verify gate + a
        # human-reviewed PR (see docs/investigations/2026-06-26-heartbeat-vs-lab-next).
        # NOTE: the installed nightly still runs `lab run` (the heartbeat). Swapping
        # it to `lab next` is a deliberate, human-gated change (setup.py, one line) —
        # this command exists so that swap can be watched via --dry-run first.
        from . import publish as publish_mod
        dry = "--dry-run" in args
        passthrough = [a for a in args[1:] if a != "--dry-run"]
        text = (publish_mod.MILESTONES_MD.read_text(encoding="utf-8")
                if publish_mod.MILESTONES_MD.exists() else "")
        milestones = publish_mod.parse_milestones(text)
        mid, has_runner = _select_next(milestones)
        if mid is None:
            subcmd, reason = "run", "no open milestone — heartbeat"
        elif has_runner:
            subcmd, reason = RUNNERS[mid], f"open milestone {mid}"
        else:
            subcmd, reason = "run", f"no runner for {mid} yet — heartbeat instead"
        label = mid or "—"
        if dry:
            print(f"lab next → {label}: would run `lab {subcmd}` ({reason})")
            return 0
        print(f"lab next → {label}: running `lab {subcmd}` ({reason})")
        return main([subcmd, *passthrough])

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
