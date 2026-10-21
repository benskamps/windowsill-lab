#!/usr/bin/env python3
"""First rung of the cross-sector single-event mode: positive control, placebo,
masked placebo, injection ladder. No survey.

Governed by ``docs/preregistrations/2026-10-20-a05-single-event-mode.md``.

    python scripts/a05_events_control.py            # full pre-registered run
    python scripts/a05_events_control.py --quick    # 20 rolls, 12 injections

Writes ``docs/investigations/2026-10-20-a05-single-event/toi1231-control.json``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab import a05_events as ev  # noqa: E402
from lab import a05_multisector as ms  # noqa: E402

PREREG = "docs/preregistrations/2026-10-20-a05-single-event-mode.md"
OUT = ROOT / "docs" / "investigations" / "2026-10-20-a05-single-event" / "toi1231-control.json"

CONTROL = {"name": "TOI-1231 b", "tic": "447061717", "period": 24.245586,
           "t0_btjd": 2458685.1163 - 2457000.0, "t14_days": 3.24 / 24,
           "depth": 0.00492, "source": "NASA Exoplanet Archive pscomppars, 2026-10-20"}

INJ_PERIODS = (17.3, 31.7, 58.9)
INJ_DEPTHS = (4000e-6, 2000e-6, 1000e-6, 500e-6)
INJ_PHASES = 5
INJ_DURATION = 3.0 / 24


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    return x


def _slim(res: dict, n: int = 10) -> dict:
    keep = ("n_events", "n_segments", "n_trials", "n_vetoed", "n_survivors", "s_max")
    out = {k: res[k] for k in keep}
    out["events"] = [{k: e[k] for k in ("t_centre", "segment", "snr", "depth", "duration_hours")}
                     for e in res["events"]]
    out["survivors"] = [{k: s[k] for k in ("period", "n", "pair", "t_ref", "duration_days",
                                           "depth", "score", "n_covered", "n_events")}
                        for s in res["survivors"][:n]]
    return out


def grade_control(res: dict, period: float) -> dict:
    surv = res["survivors"]
    if not surv:
        return {"verdict": "fail", "reason": "no surviving trial"}
    top = surv[0]
    if abs(top["period"] - period) / period <= 0.005:
        return {"verdict": "exact", "top_period": top["period"]}
    alias = any(abs(top["period"] * m - period) / period <= 0.005 for m in (2, 3, 1 / 2, 1 / 3))
    exact = [s for s in surv if abs(s["period"] - period) / period <= 0.005]
    if alias and exact and exact[0]["score"] >= 0.9 * top["score"]:
        return {"verdict": "alias-resolved", "top_period": top["period"],
                "exact_score_frac": exact[0]["score"] / top["score"]}
    return {"verdict": "fail", "top_period": top["period"],
            "exact_present": bool(exact)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    n_rolls = 20 if a.quick else ev.N_ROLLS
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    clock = time.time()
    C = CONTROL

    prods = ms.discover_products(C["tic"], provenances=("SPOC",))
    ts, fs, inputs = [], [], []
    for p in prods:
        c, row = ms.load_product(p)
        ts.append(c["t"])
        fs.append(c["f"])
        inputs.append(row)
    t = np.concatenate(ts)
    f = np.concatenate(fs)
    o = np.argsort(t, kind="stable")
    t, f = t[o], f[o]
    R: dict = {"control": C, "inputs": inputs, "preregistration": PREREG,
               "constants": {k: getattr(ev, k) for k in (
                   "EVENT_SNR", "P_MIN", "SEGMENT_GAP_DAYS", "DUR_FACTOR", "DEPTH_SIGMA",
                   "VETO_SIGMA", "SUPPORT_SNR", "N_ROLLS", "SEED")},
               "n_rolls_run": n_rolls, "quick": a.quick}

    # where the published ephemeris puts events inside the data (graded AFTER)
    seg = ev.segments(t)
    boxer = ev._Boxer(t, f)
    k0 = int(np.ceil((t[0] - C["t0_btjd"]) / C["period"]))
    k1 = int(np.floor((t[-1] - C["t0_btjd"]) / C["period"]))
    covered = []
    for k in range(k0, k1 + 1):
        tc = C["t0_btjd"] + k * C["period"]
        r = boxer.depth(tc, C["t14_days"])
        if r is not None:
            covered.append({"k": k, "t": tc, "depth": r[0], "sigma": r[1]})
    R["published_epochs_in_data"] = covered

    # 1. blind search
    blind = ev.search(t, f)
    R["blind"] = _slim(blind)
    R["positive_control"] = grade_control(blind, C["period"])

    # 2. placebo on the real series + inverted null
    pl = ev.placebo(t, f, n_rolls=n_rolls)
    R["placebo"] = {k: v for k, v in pl.items()}
    R["inverted_null"] = _slim(ev.search(t, ev.invert(f)), 3)
    R["positive_control"]["beats_all_rolls"] = bool(pl["k_exceed"] == 0)

    # 3. masked: known transits removed
    x = ((t - C["t0_btjd"] + 0.5 * C["period"]) % C["period"]) - 0.5 * C["period"]
    keep = np.abs(x) > 1.5 * C["t14_days"]
    tm, fm = t[keep], f[keep]
    R["masked"] = {"n_removed": int((~keep).sum())}
    plm = ev.placebo(tm, fm, n_rolls=n_rolls)
    R["masked"]["placebo"] = plm
    inside = (plm["null_q025"] <= plm["s_max_observed"] <= plm["null_q975"]) or \
             (plm["s_max_observed"] == 0.0 and plm["null_q975"] == 0.0)
    R["masked"]["observed_inside_central_95"] = bool(inside)
    R["masked"]["placebo_pass"] = bool(inside and plm["fap"] >= 0.05)
    R["masked"]["blind"] = _slim(ev.search(tm, fm), 5)

    # 4. injection ladder into the masked series
    rng = np.random.default_rng(ev.SEED)
    ladder = []
    n_ph = 1 if a.quick else INJ_PHASES
    for P in INJ_PERIODS:
        for _ in range(n_ph):
            t0 = float(tm[0] + rng.uniform(0, P))
            for d in INJ_DEPTHS:
                fi = ev.inject(tm, fm, P, t0, d, INJ_DURATION)
                kk = np.arange(int(np.ceil((tm[0] - t0) / P)), int(np.floor((tm[-1] - t0) / P)) + 1)
                b = ev._Boxer(tm, fi)
                n_in_data = sum(1 for k in kk if b.depth(t0 + k * P, INJ_DURATION) is not None)
                res = ev.search(tm, fi)
                ladder.append({"period": P, "t0": t0, "depth": d,
                               "n_events_in_data": n_in_data,
                               "detectable": n_in_data >= 2,
                               "recovered": ev.recovered(res, P),
                               "top_period": res["best"]["period"] if res["best"] else None,
                               "s_max": res["s_max"]})
    R["injections"] = ladder
    summ = {}
    for d in INJ_DEPTHS:
        rows = [r for r in ladder if r["depth"] == d and r["detectable"]]
        summ[f"{int(round(d * 1e6))}ppm"] = {
            "detectable": len(rows),
            "exact": sum(r["recovered"] == "exact" for r in rows),
            "alias": sum(r["recovered"] == "alias" for r in rows),
            "missed": sum(r["recovered"] is None for r in rows)}
    R["injection_summary"] = summ
    R.update({"code_commit": _git_head(), "generated_at": started,
              "wall_seconds": round(time.time() - clock, 1)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(_clean(R), indent=1) + "\n", encoding="utf-8", newline="\n")
    print(OUT)
    print(json.dumps(_clean({"positive_control": R["positive_control"],
                             "placebo_fap": pl["fap"], "masked": {k: R["masked"][k] for k in (
                                 "observed_inside_central_95", "placebo_pass")},
                             "injections": summ}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
