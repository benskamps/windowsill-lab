"""K04 — pulse-coupled fireflies: the Mirollo–Strogatz theorem, measured.

K01 and K02 ask how a crowd of *different* oscillators, each nudging all the
others continuously, drifts into partial agreement. K04 asks the older, sharper
question the field actually started with — Peskin's heart cells and the
riverbank fireflies of Southeast Asia: **identical** oscillators that interact
only in flashes. Each charges toward a threshold along a concave-down curve,
fires when it gets there, and its flash kicks every other oscillator up by a
fixed ε (capped at threshold). Nothing else couples them.

Mirollo & Strogatz (SIAM J. Appl. Math. 50, 1645 (1990)) proved the remarkable
thing: for all-to-all pulse coupling with any smooth, monotone, concave-down
charging curve and any ε > 0, the set of initial conditions that does NOT end
in perfect unison has **measure zero**. Not "usually synchronizes" — almost
every starting configuration, however scattered, ends with every oscillator
flashing as one. That is a theorem, which makes it the best possible check
target this lab has: the graded claim is an exact prediction with no tolerance
band to argue about.

### The model, exactly as the paper has it

Phase φ ∈ [0, 1] advances uniformly in time. The state ("charge") is
x = f(φ) with the concave-down charging curve

    f(φ) = (1 − e^{−bφ}) / (1 − e^{−b}),        b > 0

(Peskin's leaky integrate-and-fire form; ``B_DISSIPATION`` below is b). When an
oscillator reaches x = 1 it fires and resets to 0, and every other oscillator
jumps x → min(1, x + ε). A jump that reaches threshold fires *that* oscillator
too — absorption — and its own flash joins the cascade. Oscillators that fire
together are identical ever after (same dynamics, same resets), so the
implementation tracks **clusters** with multiplicities and the run ends when
one cluster holds the whole population. The integration is **event-driven**:
between flashes every phase advances by the same amount, so the simulation
jumps exactly from firing to firing and no time-stepping artifact can decide
the physics.

### What is graded, and what is deliberately not

1. **The theorem, measured.** ``CALIBRATION_TRIALS`` independent uniform-random
   initial conditions (deterministically seeded) must ALL reach full unison
   within ``CALIBRATION_MAX_EVENTS`` firing events. The bound is generous on
   purpose — the measured worst case over the shipped configuration is 228
   events and the bound is 5000 (~22×) — because the claim under test is
   *whether* almost-sure synchronization happens, not how fast.
2. **The null control, graded.** With ε = 0 the flashes carry no kick, clusters
   can never merge, and the population must still hold ``CALIBRATION_N``
   distinct clusters after ``NULL_EVENT_BUDGET`` events. A simulation that
   synchronized without coupling would be ordering through its own bookkeeping;
   this is the gate that proves the instrument can fail.
3. **Sync time vs N and vs ε: REPORTED, NEVER GRADED.** The events-to-unison
   ladders are carried in the receipt because they show the model's two
   characters — gradual pairwise merging at small ε, and an avalanche at
   ε ≳ the near-threshold charge spacing, where one flash absorbs the whole
   population in a single cascade (measured: median 167–169 events at ε = 0.001
   falling to ~1 at ε = 0.01, N = 100). Mirollo & Strogatz prove convergence
   but publish no closed-form rate for this configuration, and inventing a
   scaling law here to grade against would be exactly the defect the VET-F2
   history warns about. If a citable equation-level rate is ever adopted, the
   grading moves into ``checks.check_k04`` in its own change.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

# ── the fixed K04 calibration identity ───────────────────────────────────────
# One calibration, not a caller-chosen amount of easy work (the K01/C01 rule):
# ``checks.check_k04`` re-derives these and refuses to grade a run that changed
# any of them. Chosen in the GRADUAL regime — at this ε the population merges
# cluster by cluster over ~10² events, so the run actually exercises the
# absorption dynamics rather than avalanche-collapsing on the first flash.
CALIBRATION_N = 100          # oscillators
B_DISSIPATION = 3.0          # concavity of the charging curve (b > 0 required)
CALIBRATION_EPS = 0.001      # per-oscillator flash kick
CALIBRATION_TRIALS = 200     # independent initial conditions
# Generous by construction: measured events-to-unison over the shipped
# configuration is median 167 / max 228; a run needing more than ~22× the
# measured worst case is not exhibiting these dynamics.
CALIBRATION_MAX_EVENTS = 5000
# The ε = 0 control runs the same event loop with no coupling; 2000 events is
# ~10× the coupled max, and the cluster count must never drop below N.
NULL_EVENT_BUDGET = 2000
NULL_TRIALS = 20

# Reported-not-graded ladders (see the module docstring's point 3).
N_LADDER = (25, 50, 100, 200)
EPS_LADDER = (0.0005, 0.001, 0.002, 0.01)
LADDER_TRIALS = 50

#: Firing-detection tolerance: a phase within this of 1.0 is at threshold.
#: Purely numerical (accumulated float additions), far below any phase gap
#: the dynamics produces.
_FIRE_ATOL = 1e-12


def charging_curve(phi, b: float = B_DISSIPATION):
    """x = f(φ): monotone, concave down, f(0) = 0, f(1) = 1 — the paper's
    hypotheses, satisfied by the Peskin form for every b > 0."""
    import numpy as np

    return (1.0 - np.exp(-b * np.asarray(phi))) / (1.0 - math.exp(-b))


def charging_inverse(x, b: float = B_DISSIPATION):
    """φ = f⁻¹(x) — exact, so pulse kicks move charge and phases stay the
    single source of truth between events."""
    import numpy as np

    return -np.log(1.0 - np.asarray(x) * (1.0 - math.exp(-b))) / b


def run_trial(n: int, b: float, eps: float, rng, max_events: int,
              init_phi=None) -> dict:
    """One population from one random initial condition, event-driven.

    Returns the trial's whole story: ``events`` (firings until unison, or None
    if the budget ran out), the final cluster count, and the largest cascade
    (how many oscillators one flash chain-absorbed — the avalanche diagnostic).
    ``init_phi`` overrides the random draw with hand-placed phases — the test
    seam that lets the absorption cascade be pinned on configurations whose
    outcome is computable by hand.
    """
    import numpy as np

    if init_phi is not None:
        phi = np.sort(np.asarray(init_phi, dtype=float))[::-1].copy()
    else:
        phi = np.sort(rng.random(n))[::-1].copy()  # cluster phases
    size = np.ones(n, dtype=np.int64)              # cluster multiplicities
    largest_cascade = 1
    for event in range(1, max_events + 1):
        lead = int(np.argmax(phi))
        phi = phi + (1.0 - phi[lead])              # jump to the next firing
        firing = phi >= 1.0 - _FIRE_ATOL
        if eps > 0.0:
            # The cascade: every firing oscillator kicks every non-firing one
            # by ε; a kick that reaches threshold absorbs that cluster into
            # the firing group, whose own flashes then join the cascade.
            emitted = int(size[firing].sum())
            delivered = 0
            while True:
                rest = ~firing
                if not rest.any() or emitted == delivered:
                    break
                x = charging_curve(np.clip(phi[rest], 0.0, 1.0 - 1e-15), b)
                x = x + eps * (emitted - delivered)
                delivered = emitted
                absorbed = x >= 1.0
                idx = np.where(rest)[0]
                phi[idx[~absorbed]] = charging_inverse(x[~absorbed], b)
                if absorbed.any():
                    firing[idx[absorbed]] = True
                    emitted += int(size[idx[absorbed]].sum())
        fired = int(size[firing].sum())
        largest_cascade = max(largest_cascade, fired)
        if fired == n:
            return {"events": event, "clusters": 1,
                    "largest_cascade": largest_cascade}
        keep = ~firing
        phi = np.concatenate([phi[keep], [0.0]])
        size = np.concatenate([size[keep], [fired]])
    return {"events": None, "clusters": int(size.size),
            "largest_cascade": largest_cascade}


def _trial_rng(seed: int, *key: int):
    """Deterministic per-trial stream: the same house posture as A05's
    ``target_seed`` — every trial's initial condition is reproducible from the
    receipt's config alone."""
    import numpy as np

    return np.random.default_rng([seed, *key])


@dataclass
class K04Result:
    n: int
    b: float
    eps: float
    trials: int
    events: list                 # per-trial events-to-unison (all int if synced)
    largest_cascades: list
    synced: int                  # how many trials reached unison in budget
    max_events_bound: int
    events_median: float
    events_max: int
    null_trials: int
    null_event_budget: int
    null_clusters: list          # per-null-trial final cluster count
    ladder_n: dict               # {N: [events…]} at CALIBRATION_EPS
    ladder_eps: dict             # {eps: [events…]} at CALIBRATION_N
    seed: int
    is_calibration: bool
    wall_seconds: float
    config: dict


def run_k04(
    n: int = CALIBRATION_N,
    b: float = B_DISSIPATION,
    eps: float = CALIBRATION_EPS,
    trials: int = CALIBRATION_TRIALS,
    max_events: int = CALIBRATION_MAX_EVENTS,
    seed: int = 42,
    ladders: bool = True,
    progress=None,
) -> K04Result:
    """Measure the theorem: every trial must end in unison, and the uncoupled
    control must not."""
    t0 = time.time()

    events, cascades = [], []
    for trial in range(trials):
        out = run_trial(n, b, eps, _trial_rng(seed, 4, n, trial), max_events)
        events.append(out["events"])
        cascades.append(out["largest_cascade"])
        if progress is not None and (trial + 1) % 50 == 0:
            progress("trials", trial + 1, trials)

    null_clusters = []
    for trial in range(NULL_TRIALS):
        out = run_trial(n, b, 0.0, _trial_rng(seed, 4, n, trial),
                        NULL_EVENT_BUDGET)
        null_clusters.append(out["clusters"])
    if progress is not None:
        progress("null", NULL_TRIALS, NULL_TRIALS)

    ladder_n: dict = {}
    ladder_eps: dict = {}
    if ladders:
        for ln in N_LADDER:
            ladder_n[str(ln)] = [
                run_trial(ln, b, eps, _trial_rng(seed, 5, ln, t),
                          max_events)["events"]
                for t in range(LADDER_TRIALS)
            ]
        for le in EPS_LADDER:
            ladder_eps[repr(le)] = [
                run_trial(n, b, le, _trial_rng(seed, 6, int(le * 1e6), t),
                          max_events)["events"]
                for t in range(LADDER_TRIALS)
            ]
        if progress is not None:
            progress("ladders", 1, 1)

    finished = [e for e in events if e is not None]
    finished.sort()
    return K04Result(
        n=n, b=b, eps=eps, trials=trials,
        events=events,
        largest_cascades=cascades,
        synced=len(finished),
        max_events_bound=max_events,
        events_median=(float(finished[len(finished) // 2])
                       if finished else float("nan")),
        events_max=(max(finished) if finished else -1),
        null_trials=NULL_TRIALS,
        null_event_budget=NULL_EVENT_BUDGET,
        null_clusters=null_clusters,
        ladder_n=ladder_n,
        ladder_eps=ladder_eps,
        seed=seed,
        is_calibration=bool(
            n == CALIBRATION_N and b == B_DISSIPATION
            and eps == CALIBRATION_EPS and trials == CALIBRATION_TRIALS
            and max_events == CALIBRATION_MAX_EVENTS
        ),
        wall_seconds=time.time() - t0,
        config={"n": n, "b": b, "eps": eps, "trials": trials,
                "max_events": max_events, "seed": seed,
                "null_trials": NULL_TRIALS,
                "null_event_budget": NULL_EVENT_BUDGET},
    )


def to_report(result: K04Result) -> dict:
    """A JSON report shaped for the page and ``check_k04`` — per-trial arrays
    included, so every graded number is re-derivable from the raw receipt."""
    from .checks import check_k04

    report = {
        "experiment": "K04-firefly-synchronization",
        "n": result.n,
        "b": result.b,
        "eps": result.eps,
        "trials": result.trials,
        "events": result.events,
        "largest_cascades": result.largest_cascades,
        "synced": result.synced,
        "max_events_bound": result.max_events_bound,
        "events_median": result.events_median,
        "events_max": result.events_max,
        "null_trials": result.null_trials,
        "null_event_budget": result.null_event_budget,
        "null_clusters": result.null_clusters,
        "ladder_n": result.ladder_n,
        "ladder_eps": result.ladder_eps,
        "seed": result.seed,
        "is_calibration": result.is_calibration,
        "wall_seconds": result.wall_seconds,
        "config": result.config,
    }
    report["headline"] = (
        f"Mirollo–Strogatz fireflies (N={result.n}, b={result.b:g}, "
        f"ε={result.eps:g}): {result.synced}/{result.trials} random initial "
        f"conditions reached unison (median {result.events_median:.0f} / max "
        f"{result.events_max} events vs bound {result.max_events_bound}); "
        f"ε=0 control held {min(result.null_clusters) if result.null_clusters else 0} "
        f"clusters of {result.n} · {result.wall_seconds:.0f}s"
    )
    passed, _ = check_k04(report)
    report["status"] = "pass" if passed else "null"
    report["claim_boundary"] = (
        "The graded claim is the Mirollo–Strogatz almost-sure synchronization "
        "theorem, measured over 200 random initial conditions of one fixed "
        "configuration (N=100, b=3, ε=0.001, all-to-all): every trial must "
        "reach unison within a generous event bound, and the uncoupled "
        "control must not. Sync-TIME behaviour vs N and ε is reported, never "
        "graded — the theorem guarantees convergence, not a rate, and no "
        "equation-level published rate for this configuration is adopted "
        "here. Nothing is claimed about non-identical oscillators, delayed or "
        "local coupling, or the inhibitory case."
    )
    return report
