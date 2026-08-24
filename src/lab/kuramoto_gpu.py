"""The same Kuramoto dynamics on the GPU — because N is the lever, not T.

`kuramoto.py` concluded that collapsing the pair sum to a mean field "makes a
2000-oscillator sweep a NumPy job rather than a GPU one." That was correct when
2000 was the target. U-K02 changed the target.

The statistical error on a subcritical observable falls as ``1/sqrt(N · T/τ)``,
so N and T trade evenly in total work — and not at all evenly in wall-clock,
because time is strictly serial while N is embarrassingly parallel. Measured on
this box (RK4, float64, seconds per step):

| N | NumPy CPU | torch GPU |
|---|---|---|
| 2,000 | 203 µs | 306 µs |
| 20,000 | 1737 µs | 310 µs |
| 200,000 | 17680 µs | 527 µs |
| 2,000,000 | — | 3245 µs |

At N = 2,000 the GPU is *slower* — the kernels are launch-bound and the old
docstring's verdict still holds. By N = 200,000 it is 33× faster: **100× the
oscillators for 2.6× the wall-clock**, which buys a 10× noise reduction that
would otherwise cost 100× the measurement time. That is what moves U-K02 from
103 CPU-hours to 3.1 GPU-hours.

## The rule this module lives under

**A new engine must reproduce the old engine before it is allowed to produce new
science.** `test_kuramoto_gpu.py` steps both from identical state and requires
agreement to float64 round-off over a full trajectory, on both branches and with
a field applied. A faster instrument that quietly disagrees with the calibrated
one is not an upgrade; it is an unlabelled second lab.
"""
from __future__ import annotations

import numpy as np

_TORCH = None


def torch_or_none():
    """Import torch lazily. The lean CI job has no GPU stack and must not fail
    at import time — callers get `needs-deps`, which the verify path already
    understands, rather than a collection error."""
    global _TORCH
    if _TORCH is None:
        try:
            import torch
            _TORCH = torch
        except ModuleNotFoundError:
            _TORCH = False
    return _TORCH or None


def available() -> bool:
    t = torch_or_none()
    return bool(t and t.cuda.is_available())


def device_name() -> str:
    t = torch_or_none()
    if not t or not t.cuda.is_available():
        return "cpu"
    return t.cuda.get_device_name(0)


def _drift(theta, omega, coupling, field):
    """``dθ/dt = ω + K·r·sin(ψ − θ) + h·sin(Θ − θ)``, mirroring `kuramoto._drift`.

    Deliberately the same algebra in the same order — ``⟨sin θ⟩·cos θ −
    ⟨cos θ⟩·sin θ`` rather than a complex-exponential centroid — because the
    agreement test compares trajectories, and a mathematically equivalent but
    differently-associated expression would drift at the last bits and turn a
    real disagreement into noise nobody could interpret.
    """
    cos_t, sin_t = theta.cos(), theta.sin()
    c = cos_t.mean(dim=-1, keepdim=True)
    s = sin_t.mean(dim=-1, keepdim=True)
    out = omega + coupling * (s * cos_t - c * sin_t)
    if field is not None:
        out = out - field * sin_t
    return out


def rk4_step(theta, omega, coupling, dt, field=None):
    """One RK4 step. All four stages recompute the mean field, as on the CPU."""
    k1 = _drift(theta, omega, coupling, field)
    k2 = _drift(theta + 0.5 * dt * k1, omega, coupling, field)
    k3 = _drift(theta + 0.5 * dt * k2, omega, coupling, field)
    k4 = _drift(theta + dt * k3, omega, coupling, field)
    return theta + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def to_device(array, device="cuda", dtype=None):
    t = torch_or_none()
    if t is None:
        raise ModuleNotFoundError("torch is not installed")
    dtype = dtype or t.float64
    return t.as_tensor(np.asarray(array), dtype=dtype, device=device)


def evolve(theta, omega, coupling, dt, steps, field=None, observe_every=0,
           observable="both"):
    """Integrate ``steps`` steps, optionally accumulating running observables.

    Averages are accumulated on the device in float64 rather than by shipping a
    trajectory back — at N = 200,000 and 500,000 steps the trajectory would be
    hundreds of gigabytes, and the only quantities K03 needs are ⟨r⟩ and
    ⟨cos θ⟩, one scalar each per sample.
    """
    t = torch_or_none()
    if t is None:
        raise ModuleNotFoundError("torch is not installed")
    n_samples = 0
    acc_r = t.zeros((), dtype=theta.dtype, device=theta.device)
    acc_cos = t.zeros((), dtype=theta.dtype, device=theta.device)
    for i in range(steps):
        theta = rk4_step(theta, omega, coupling, dt, field)
        if observe_every and (i + 1) % observe_every == 0:
            cos_t, sin_t = theta.cos(), theta.sin()
            c = cos_t.mean(dim=-1)
            s = sin_t.mean(dim=-1)
            if observable in ("r", "both"):
                acc_r = acc_r + (c * c + s * s).sqrt().mean()
            if observable in ("cos", "both"):
                acc_cos = acc_cos + c.mean()
            n_samples += 1
    out = {"theta": theta, "n_samples": n_samples}
    if n_samples:
        out["mean_r"] = float(acc_r / n_samples)
        out["mean_cos"] = float(acc_cos / n_samples)
    return out
