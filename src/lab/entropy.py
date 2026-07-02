"""Entropy by thermodynamic integration of C(T)/T — the lab's first *integrated* quantity.

Every prior milestone *locates* something: a peak (M01/M04/M05/M06/M07), a jump
(M08), a crossing (M12), or a monotone trend (M09/M11). M13 needs a genuinely new
analysis primitive — it has to **integrate** a measured curve. The entropy of a
spin system is fixed by the specific heat through the exact thermodynamic identity
``dS = (C/T) dT``, so integrating ``C(T')/T'`` from a temperature down to (or up
from) a reference pins the entropy there:

    S(T) = S(∞) − ∫_T^∞ (C(T')/T') dT'          with   S(∞) = N·ln 2   (free spins)

The **residual entropy** is the ``T → 0`` limit, ``S0 = S(0)`` — for an ordinary
system it is ``0`` (a unique, or sub-extensively degenerate, ground state), but for
a *frustrated* one (the triangular Ising antiferromagnet, M13) it is a macroscopic
constant: Wannier's exact ``S0/N = 0.3383 k_B``. Measuring it is the whole point of
M13, and this module is the instrument.

### What the numbers mean, and where the error lives

We only ever have C on a *finite* grid ``T_min … T_max``, so the measured residual

    S0_est = S(∞) − ∫_{T_min}^{T_max} (C/T) dT'  −  (high-T tail beyond T_max)

**omits** the unmeasured low-T piece ``∫_0^{T_min} (C/T) dT' ≥ 0``. That omission
*by itself* biases ``S0_est`` **high** (a dropped non-negative integral), which is
why ``T_min`` is pushed near 0. But it is not the only error: the trapezoidal
integration of the *measured* C over the window carries its own discretisation and
Monte-Carlo error, and in practice these can outweigh the low-T truncation — for the
triangular-AFM measurement M13 makes, the net residual lands a few percent *below*
0.3383 and converges there as the lattice grows (the ground-state energy anchor, an
exact −1, confirms the physics is right; the gap is the finite-window integration
method, not a broken model). So the honest caveat is: the integrated residual is a
**few-percent** number, and the tolerance that grades it is a physical band, not a
claim of exactness. The high-T tail beyond ``T_max`` is *added back* analytically
(the leading ``C ≈ a/T²`` form integrates to ``C(T_max)/2``), because it is small
and known; only the low-T end is left as an explicit truncation.

Stdlib-only (no numpy, no torch) so the check that grades M13 can **re-derive** the
residual entropy from a report's ``(T, C)`` arrays without importing the engine —
the same discipline M12's crossing reducers follow. The tolerance that decides
pass/null is owned by the *check*, never by this module or the report.
"""
from __future__ import annotations

import math

# S(∞) per spin for an Ising (two-state) degree of freedom: every spin is free at
# infinite temperature, so the high-T reference entropy is ln 2 per spin.
LN2 = math.log(2.0)


def _sorted_by_T(T, C) -> tuple[list[float], list[float]]:
    """Return ``(T, C)`` as parallel ascending-in-T float lists (a stable re-sort).

    Callers may hand grids in any order (a geometric grid, a stitched multi-window
    sweep); the trapezoid below assumes monotone T, so we sort once here.
    """
    order = sorted(range(len(T)), key=lambda i: T[i])
    return [float(T[i]) for i in order], [float(C[i]) for i in order]


def cooling_integral(T, C) -> list[float]:
    """Cumulative entropy removed ``∫_{T_i}^{T_max} (C/T') dT'`` at every grid point.

    ``T`` ascending, ``C`` parallel. Returns ``I`` with ``I[-1] = 0`` (nothing lies
    above the hottest sample) and ``I[0]`` the full-grid integral, accumulated from
    the top down so each ``I[i]`` is the entropy *removed* between ``T_i`` and the top
    of the window.

    The integral is taken in **log-temperature**: since ``C/T' dT' = C d(ln T')``, the
    trapezoid integrates ``C`` against ``ln T`` rather than ``C/T`` against ``T``. On the
    geometric grid M13 uses this is the well-conditioned choice — the grid is *uniform*
    in ``ln T`` and ``C`` is a smooth bump there, so a coarse grid already converges;
    integrating ``C/T`` against ``T`` instead samples the hot end (large ΔT steps)
    coarsely and biases the residual low until the grid is very fine (verified against
    the analytic Schottky curve: log-T is grid-independent by ~20 points, C/T-in-T needs
    ~100). The two are the same continuum integral — this is purely the accurate
    discretisation. Stdlib only.
    """
    n = len(T)
    u = [math.log(t) for t in T]
    I = [0.0] * n
    for i in range(n - 2, -1, -1):
        du = u[i + 1] - u[i]
        I[i] = I[i + 1] + 0.5 * (C[i] + C[i + 1]) * du
    return I


def high_t_tail(T_max: float, C_max: float) -> float:
    """Analytic ``∫_{T_max}^∞ (C/T') dT'`` under the leading high-T form ``C ≈ a/T²``.

    At high temperature the specific heat of a lattice spin model falls off as
    ``C ≈ a/T²`` (the leading term of the high-T expansion), so ``C/T ≈ a/T³`` and
    the tail integrates in closed form to ``a/(2 T_max²) = C(T_max)/2`` (using
    ``a = C_max · T_max²``). It is a small, *known* correction we add back so the
    hot-end truncation is not silently charged to the residual; the load-bearing
    truncation M13 reports is the low-T end, which is left explicit.
    """
    return 0.5 * C_max


def entropy_curve(T, C, s_inf: float = LN2, add_high_t_tail: bool = True):
    """``(T_sorted, S)`` with ``S[i] = s_inf − tail − ∫_{T_i}^{T_max} C/T'`` per spin.

    The entropy at each temperature, descending from ``≈ s_inf`` at the hot end
    toward the residual at the cold end. ``s_inf`` defaults to ``ln 2`` (one Ising
    spin's worth of high-T disorder); pass a different reference for a toy with a
    different multiplicity (e.g. ``ln 3`` for a three-state high-T limit). When
    ``add_high_t_tail`` is set the small analytic ``C(T_max)/2`` beyond the grid is
    folded in so ``S`` sits at ``≈ s_inf`` at the top instead of a hair below it.
    """
    Ts, Cs = _sorted_by_T(T, C)
    I = cooling_integral(Ts, Cs)
    tail = high_t_tail(Ts[-1], Cs[-1]) if add_high_t_tail else 0.0
    return Ts, [s_inf - tail - Ii for Ii in I]


def residual_entropy(T, C, s_inf: float = LN2, add_high_t_tail: bool = True) -> float:
    """The ``T → 0`` residual entropy per spin: ``S`` at the coldest measured point.

    ``S0 = s_inf − tail − ∫_{T_min}^{T_max} (C/T') dT'``. Dropping the unmeasured
    ``∫_0^{T_min}`` (non-negative) biases this *up*, but the trapezoidal integration
    of the measured C carries its own error, so the net is a few-percent number (for
    M13's triangular AFM it lands slightly *below* Wannier's exact ``0.3383 k_B`` and
    converges there with lattice size). For a frustrated system it sits near that
    macroscopic constant; for an unfrustrated one it lands near ``0``.
    """
    _, S = entropy_curve(T, C, s_inf, add_high_t_tail)
    return S[0]


def total_entropy_removed(T, C, add_high_t_tail: bool = True) -> float:
    """``∫_{T_min}^{T_max} (C/T') dT'`` (+ optional analytic high-T tail) per spin.

    The entropy carried away by cooling across the measured window — the companion
    of :func:`residual_entropy` (``S0 = s_inf − total_removed``). Reported so the
    windowed integral and the reference ``s_inf`` are both visible, not just their
    difference.
    """
    Ts, Cs = _sorted_by_T(T, C)
    I = cooling_integral(Ts, Cs)
    tail = high_t_tail(Ts[-1], Cs[-1]) if add_high_t_tail else 0.0
    return I[0] + tail
