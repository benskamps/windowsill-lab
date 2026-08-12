"""Exact analytical results for the 2D Ising model (Onsager 1944)."""
import numpy as np


T_C = 2.0 / np.log(1.0 + np.sqrt(2.0))  # ≈ 2.269185...


def onsager_magnetization(T: np.ndarray, J: float = 1.0) -> np.ndarray:
    """Spontaneous magnetization per spin for an infinite 2D square Ising lattice.

    The exact result is Yang 1952 (Phys. Rev. 85, 808); Onsager's 1944 paper
    solved the free energy and gave T_C, and he announced this curve in 1948
    without publishing a derivation.

        M(T) = (1 - sinh(2J/T)^(-4))^(1/8)   for T < T_c
        M(T) = 0                              for T >= T_c
    """
    T = np.asarray(T, dtype=np.float64)
    beta = 1.0 / T
    s4 = np.sinh(2.0 * J * beta) ** 4
    out = np.zeros_like(T)
    mask = s4 > 1.0  # below T_c
    out[mask] = (1.0 - 1.0 / s4[mask]) ** (1.0 / 8.0)
    return out
