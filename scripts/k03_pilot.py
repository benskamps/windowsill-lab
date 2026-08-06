"""K03 pilot — do the two branches of chi have different exponents?

The live disagreement:
  Daido (1986-90):  gamma = 1/4 above K_c,  gamma' = 1 below   (asymmetric)
  Hong et al. 2015: gamma ~ gamma' ~ 1/4                        (symmetric)
Both statements are about the REGULAR (deterministic-quantile) Lorentzian, which
is exactly this engine's frequency set (assay 2026-08-02 sec 2.2: identical term
for term to Hong Eq. 4.1).

chi ~ |K - K_c|^(-gamma) on each side. Fit each branch separately in log-log.

Rounding guard: finite-N smears the transition over eps ~ N^(-1/nubar) with
nubar ~ 5/4 for this class -> 0.0023 at N=2000. The grid starts at eps=0.02,
about 10x outside, so a scaling window exists.

Equilibration guard: K02 learned the hard way that a too-short window measures a
transient. Each point reports the drift between the halves of its own measurement
window; a point still settling is reported, not silently fitted.
"""
import sys, json, time
sys.path.insert(0, 'src')
import numpy as np
from lab import kuramoto as ku

GAMMA = 0.5
KC = ku.critical_coupling(GAMMA)          # exactly 1.0
EPS = np.array([0.02, 0.03, 0.045, 0.065, 0.10, 0.15, 0.22, 0.32])
DT = 0.02
T_BURN, T_MEAS = 500.0, 1000.0
SEEDS = [42, 7, 1234, 99]
LADDER = [1000, 2000]

K_BELOW = KC * (1.0 - EPS[::-1])
K_ABOVE = KC * (1.0 + EPS)
K_ALL = np.concatenate([K_BELOW, K_ABOVE])


def halves_drift(n, K, seed):
    """Run the window in two halves; return chi for each so drift is visible."""
    a = ku.run_sweep(K, n=n, gamma=GAMMA, dt=DT, t_burn=T_BURN,
                     t_measure=T_MEAS / 2, seed=seed)
    b = ku.run_sweep(K, n=n, gamma=GAMMA, dt=DT, t_burn=T_BURN + T_MEAS / 2,
                     t_measure=T_MEAS / 2, seed=seed)
    return a.chi, b.chi


def fit_loglog(eps, chi):
    """chi ~ eps^(-g). Return g (positive = diverging toward K_c) and R^2."""
    x, y = np.log(eps), np.log(chi)
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float('nan')
    return -float(coef[1]), r2


out = {"kc": KC, "gamma_lorentz": GAMMA, "eps": EPS.tolist(),
       "dt": DT, "t_burn": T_BURN, "t_measure": T_MEAS,
       "seeds": SEEDS, "ladder": LADDER, "rungs": []}

for n in LADDER:
    chis_a, chis_b = [], []
    t0 = time.time()
    for s in SEEDS:
        ca, cb = halves_drift(n, K_ALL, s)
        chis_a.append(ca); chis_b.append(cb)
    el = time.time() - t0
    ca = np.mean(chis_a, axis=0); cb = np.mean(chis_b, axis=0)
    chi = 0.5 * (ca + cb)
    drift = np.abs(cb - ca) / np.maximum(chi, 1e-12)

    n_e = len(EPS)
    chi_below = chi[:n_e][::-1]          # back to ascending eps
    chi_above = chi[n_e:]
    d_below = drift[:n_e][::-1]
    d_above = drift[n_e:]

    g_above, r2_above = fit_loglog(EPS, chi_above)
    g_below, r2_below = fit_loglog(EPS, chi_below)

    out["rungs"].append({
        "n": n, "wall_s": round(el, 1),
        "eps": EPS.tolist(),
        "chi_above": chi_above.tolist(), "chi_below": chi_below.tolist(),
        "drift_above": d_above.tolist(), "drift_below": d_below.tolist(),
        "gamma_above": g_above, "r2_above": r2_above,
        "gamma_below": g_below, "r2_below": r2_below,
    })
    print(f"N={n}  ({el:.0f}s)")
    print(f"   above K_c: gamma  = {g_above:+.3f}  (R2 {r2_above:.3f})   max drift {d_above.max():.1%}")
    print(f"   below K_c: gamma' = {g_below:+.3f}  (R2 {r2_below:.3f})   max drift {d_below.max():.1%}")
    print(f"   Daido predicts 0.25 / 1.00 ;  Hong predicts 0.25 / 0.25")
    sys.stdout.flush()

with open(sys.argv[1] if len(sys.argv) > 1 else 'k03_pilot.json', 'w') as f:
    json.dump(out, f, indent=2)
print("written")
