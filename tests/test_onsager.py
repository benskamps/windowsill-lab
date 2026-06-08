import numpy as np
import pytest

from lab.onsager import onsager_magnetization, T_C


def test_critical_temperature_value():
    # Classic result: T_c = 2 / ln(1 + sqrt(2)) ≈ 2.269185
    assert abs(T_C - 2.269185) < 1e-5


def test_magnetization_zero_above_tc():
    T = np.linspace(T_C + 0.01, T_C + 1.0, 20)
    M = onsager_magnetization(T)
    assert np.all(M == 0.0)


def test_magnetization_one_at_zero_temp_limit():
    T = np.array([0.5, 1.0, 1.5])  # well below T_c
    M = onsager_magnetization(T)
    assert M[0] > 0.99  # essentially 1 at very low T
    assert np.all(np.diff(M) < 0)  # monotonically decreasing as T rises


def test_continuous_at_known_temperature():
    # M at T = 2.0 (below T_c) from the Onsager formula, computed by hand:
    # M = (1 - sinh(2/2)^-4)^(1/8) = (1 - sinh(1)^-4)^(1/8)
    import math
    expected = (1.0 - math.sinh(1.0) ** -4) ** (1.0 / 8.0)
    actual = onsager_magnetization(np.array([2.0]))[0]
    assert abs(actual - expected) < 1e-9
