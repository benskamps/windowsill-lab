#!/usr/bin/env python3
"""U-K02 — run the clip control, then the attempt.

Order is not a preference. UNKNOWNS.md: "that is the argument for running the
clip control before anything expensive, not after." If the tail clip decides the
exponent then this engine's g(omega) is neither paper's and the expensive run
would measure the wrong distribution very precisely.

Usage:
  python3 scripts/u_k02_run.py control [--n N] [--steps S]
  python3 scripts/u_k02_run.py attempt [--n N]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from dataclasses import asdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from lab import u_k02  # noqa: E402

#: Subcritical grid. Spaced in log-eps so the fit has even leverage, and stopped
#: at 0.05 because measure_steps_for caps below that — a column the budget
#: cannot afford is a column that would be reported at its cap, quietly noisier
#: than its neighbours and pulling the slope.
ATTEMPT_EPS = [0.30, 0.21, 0.145, 0.10, 0.07, 0.05]
CONTROL_EPS = [0.30, 0.15, 0.08]
#: The clip LADDER. The control proved chi moves 162% between 40 and 400; the
#: question that decides whether the attempt is worth running is whether the
#: EXPONENT moves, and whether it converges as the clip widens. Daido's own
#: construction is the UNCLIPPED quantile rule, so wider is more faithful and
#: the production 40 is the deviation — convergence tells us where the answer
#: actually sits.
LADDER_EPS = [0.30, 0.19, 0.12, 0.08]
LADDER_CLIPS = [40.0, 100.0, 400.0]


def out_dir() -> pathlib.Path:
    d = pathlib.Path.home() / ".lab" / "u_k02"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["control", "ladder", "attempt"])
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    ns = ap.parse_args()

    t0 = time.time()
    if ns.mode == "control":
        n = ns.n or 20_000
        steps = ns.steps or 100_000
        print(f"U-K02 clip control · N={n:,} · {steps:,} steps/column · "
              f"eps={CONTROL_EPS}", flush=True)
        print("  narrow = production clip 40*gamma (32 of 2000 displaced)", flush=True)
        print("  wide   = 400*gamma, dt/10 so |omega|*dt is unchanged", flush=True)
        cc = u_k02.clip_control(CONTROL_EPS, n=n, steps=steps)
        for nar, wid in zip(cc.narrow, cc.wide):
            ratio = wid.chi / nar.chi if nar.chi else float("nan")
            print(f"  eps={nar.eps:<6} chi_narrow={nar.chi:.4f}+/-{nar.chi_err:.4f}  "
                  f"chi_wide={wid.chi:.4f}+/-{wid.chi_err:.4f}  ratio={ratio:.4f}",
                  flush=True)
        print(f"\n  VERDICT: {cc.verdict}\n  {cc.detail}", flush=True)
        payload = {"mode": "clip-control", "verdict": cc.verdict,
                   "detail": cc.detail, "n": n, "steps": steps,
                   "narrow": [asdict(c) for c in cc.narrow],
                   "wide": [asdict(c) for c in cc.wide],
                   "wall_seconds": round(time.time() - t0, 1)}
        (out_dir() / "clip-control.json").write_text(json.dumps(payload, indent=1))
        print(f"  -> {out_dir() / 'clip-control.json'}", flush=True)
        return 0

    if ns.mode == "ladder":
        import math
        n = ns.n or 20_000
        steps = ns.steps or 400_000
        print(f"U-K02 clip LADDER · N={n:,} · {steps:,} base steps · "
              f"eps={LADDER_EPS} · clips={LADDER_CLIPS}", flush=True)
        print("  dt scales with the clip so |omega|*dt is identical everywhere",
              flush=True)
        results = {}
        for clip in LADDER_CLIPS:
            cols = [u_k02.chi_column(e, n=n, clip_scale=clip, steps=steps)
                    for e in LADDER_EPS]
            fit = u_k02.fit_exponent(cols)
            verdict = u_k02.adjudicate(fit)
            results[str(clip)] = {"columns": [asdict(c) for c in cols],
                                  "fit": fit, "verdict": verdict}
            print(f"\n  clip {clip:>6}g  chi = "
                  + ", ".join(f"{c.chi:.4f}+/-{c.chi_err:.4f}" for c in cols),
                  flush=True)
            print(f"    gamma' = {fit['gamma_prime']:.4f} +/- {fit['stderr']:.4f}"
                  f"  local {[round(x,3) for x in fit['local_slopes']]}"
                  f"  -> {verdict['verdict']}", flush=True)
        gs = [results[str(c)]["fit"]["gamma_prime"] for c in LADDER_CLIPS]
        spread = max(gs) - min(gs)
        conv = abs(gs[-1] - gs[-2])
        print(f"\n  gamma' across the ladder: {[round(g,4) for g in gs]}", flush=True)
        print(f"  spread {spread:.4f} vs the {u_k02.RIVAL_GAP} rival gap; "
              f"last-step change {conv:.4f}", flush=True)
        if spread > u_k02.RIVAL_GAP:
            note = ("the exponent moves further across the CLIP than the two "
                    "papers differ from each other — this engine cannot pose the "
                    "question until the frequency set is fixed")
        elif conv < 0.1:
            note = ("the exponent is converging as the clip widens; the wide end "
                    "is the faithful one and the attempt can be posed there")
        else:
            note = "not converged; a wider clip or more statistics is needed"
        print(f"  READ: {note}", flush=True)
        (out_dir() / "clip-ladder.json").write_text(json.dumps(
            {"mode": "clip-ladder", "n": n, "steps": steps,
             "eps": LADDER_EPS, "clips": LADDER_CLIPS, "results": results,
             "gamma_prime_by_clip": gs, "spread": spread, "read": note,
             "wall_seconds": round(time.time() - t0, 1)}, indent=1))
        print(f"  -> {out_dir() / 'clip-ladder.json'}", flush=True)
        return 0

    n = ns.n or 200_000
    print(f"U-K02 ATTEMPT · N={n:,} · eps={ATTEMPT_EPS}", flush=True)
    print("  observable: chi = N*Var_t(r)  (FLUCTUATION, not the K03 response)",
          flush=True)
    print(f"  rivals in chi units: Daido {u_k02.DAIDO_GAMMA_PRIME}, "
          f"Hong {u_k02.HONG_GAMMA_PRIME}({u_k02.HONG_GAMMA_PRIME_ERR})", flush=True)
    cols = []
    for eps in ATTEMPT_EPS:
        c = u_k02.chi_column(eps, n=n)
        cols.append(c)
        print(f"  eps={c.eps:<6} chi={c.chi:.5f} +/- {c.chi_err:.5f} "
              f"({100*c.chi_err/c.chi:.1f}%)  steps={c.steps:,}  "
              f"{c.wall_seconds:.0f}s", flush=True)
    fit = u_k02.fit_exponent(cols)
    verdict = u_k02.adjudicate(fit)
    print(f"\n  gamma' = {fit['gamma_prime']:.4f} +/- {fit['stderr']:.4f}  "
          f"(R^2={fit['r_squared']:.4f}, chi2/dof={fit['chi2_per_dof']:.2f})",
          flush=True)
    print(f"  local slopes: {[round(s,3) for s in fit['local_slopes']]}", flush=True)
    print(f"  VERDICT: {verdict['verdict']} — {verdict['why']}", flush=True)
    payload = {"mode": "attempt", "n": n, "columns": [asdict(c) for c in cols],
               "fit": fit, "verdict": verdict,
               "wall_seconds": round(time.time() - t0, 1)}
    (out_dir() / "attempt.json").write_text(json.dumps(payload, indent=1))
    print(f"  -> {out_dir() / 'attempt.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
