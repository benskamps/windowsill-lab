"""Post-Newtonian inspiral waveforms in the frequency domain.

TaylorF2: the stationary-phase approximation to a quasi-circular, non-spinning
inspiral. Amplitude goes as f^(-7/6); all the information about the masses is in
the phase, which is why matched filtering measures chirp mass so sharply.

The phase is written to 3.5PN. Order matters more than it looks: truncating at
2PN accumulates error over the hundreds-to-thousands of cycles a binary neutron
star spends in band, and the fit absorbs that error by shifting the chirp mass —
a percent-level bias on a quantity published to 0.1 %.

Constant terms and log normalisations inside the phase only shift the coalescence
phase phi_c, which the |z| matched-filter statistic is blind to, so ln(v) is used
directly rather than ln(v/v_lso).
"""
from __future__ import annotations

import numpy as np

C_LIGHT = 2.99792458e8
G_NEWTON = 6.67430e-11
M_SUN_KG = 1.98892e30
#: one solar mass in seconds — the geometric unit PN expansions are written in
TSUN = G_NEWTON * M_SUN_KG / C_LIGHT ** 3
EULER_GAMMA = 0.5772156649015329


def phase_35pn(v: np.ndarray, eta: float) -> np.ndarray:
    """The bracket of the TaylorF2 phase: Psi = 3/(128 eta v^5) * bracket."""
    e2 = eta * eta
    e3 = e2 * eta
    lv = np.log(v)
    return (
        1.0
        + (3715.0 / 756.0 + 55.0 * eta / 9.0) * v ** 2
        - 16.0 * np.pi * v ** 3
        + (15293365.0 / 508032.0 + 27145.0 * eta / 504.0 + 3085.0 * e2 / 72.0) * v ** 4
        + (38645.0 / 756.0 - 65.0 * eta / 9.0) * np.pi * (1.0 + 3.0 * lv) * v ** 5
        + (
            11583231236531.0 / 4694215680.0
            - 640.0 * np.pi ** 2 / 3.0
            - 6848.0 * EULER_GAMMA / 21.0
            - (6848.0 / 21.0) * np.log(4.0)
            - (6848.0 / 21.0) * lv
            + eta * (-15737765635.0 / 3048192.0 + 2255.0 * np.pi ** 2 / 12.0)
            + 76055.0 * e2 / 1728.0
            - 127825.0 * e3 / 1296.0
        ) * v ** 6
        + np.pi * (
            77096675.0 / 254016.0
            + 378515.0 * eta / 1512.0
            - 74045.0 * e2 / 756.0
        ) * v ** 7
    )


def isco_frequency(mc_msun: float, eta: float) -> float:
    """Innermost stable circular orbit — where an inspiral template stops being
    the right model. For a 66 Msun binary this is 67 Hz, which is the whole
    reason A03 does not target GW150914."""
    mtot = (mc_msun * TSUN) / eta ** 0.6
    return 1.0 / (6 ** 1.5 * np.pi * mtot)


def taylorf2_35(freqs: np.ndarray, mc_msun: float, eta: float,
                f_low: float, f_high: float) -> np.ndarray:
    """Unnormalised 3.5PN TaylorF2 template sampled on ``freqs``.

    Truncated at min(f_high, f_ISCO): past ISCO the stationary-phase inspiral is
    not a description of anything.
    """
    mc = mc_msun * TSUN
    mtot = mc / eta ** 0.6
    fmax = min(f_high, 1.0 / (6 ** 1.5 * np.pi * mtot))
    h = np.zeros(len(freqs), dtype=np.complex128)
    band = (freqs >= f_low) & (freqs <= fmax)
    if not band.any():
        return h
    f = freqs[band]
    v = (np.pi * mtot * f) ** (1.0 / 3.0)
    psi = (3.0 / (128.0 * eta * v ** 5)) * phase_35pn(v, eta)
    h[band] = f ** (-7.0 / 6.0) * np.exp(1j * psi)
    return h
