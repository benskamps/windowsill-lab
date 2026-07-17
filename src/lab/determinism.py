"""Golden-seed determinism gate — prove the instrument reproduces *itself*.

``lab verify`` regrades saved measurements; it never re-runs the engine, so
nothing on record proves the simulator is deterministic. This module closes that
gap with a tiny, pinned, **CPU-only** 2D Ising smoke run and a committed golden
artifact. It enforces two separate claims, and is honest about the boundary
between them:

1. **Self-determinism** (hard, platform-independent). Running the pinned config
   twice in one process must yield byte-identical canonical measurements
   (SHA-256 equal). One process on one build has no excuse to disagree with
   itself — if it does, the RNG seeding is broken or an accidentally
   nondeterministic op crept in. This is the load-bearing claim and it holds on
   every platform.

2. **Golden agreement** (regression anchor). The fresh measurements must match
   the committed golden (``tests/golden/determinism-l16-seed42.json``). On the
   platform that *blessed* the golden this is bit-exact (SHA-256 equal). Across
   platforms/torch builds, exact float bit-identity of a reduction is **not**
   guaranteed (last-ULP differences in ``exp``/summation, and the chaotic
   Metropolis trajectory amplifies them), so a SHA miss is graded **numerically**
   within a check-owned tolerance. A real regression — a broken RNG, a changed
   update rule, the wrong temperature grid — diverges by orders of magnitude or
   changes the *shape* of the output; last-ULP platform noise does not. The
   structural checks (keys, array lengths, config) are always exact.

Stdlib + torch only. Never touches CUDA: the config pins ``device="cpu"``.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

# The pinned smoke config: L=16 2D Ising, seed=42, six temperatures straddling
# Onsager's T_c=2.269 so the measurement carries a real susceptibility peak (a
# physically meaningful fingerprint, not noise). Small enough to run twice in
# ~a second on a CPU; large enough that a broken update rule is obvious.
SMOKE_CONFIG: dict = {
    "L": 16,
    "T_min": 1.6,
    "T_max": 3.0,
    "n_temps": 6,
    "n_burnin": 500,
    "n_sweeps": 1000,
    "sample_every": 20,
    "seed": 42,
    "device": "cpu",
}

# The canonical measurement fields — the physics numbers, in a fixed order. Timing
# (wall_seconds) and the heavy lattice snapshots are deliberately excluded: one is
# nondeterministic, the other is bulky and not a measurement.
MEASUREMENT_KEYS = ("T", "abs_mag", "chi", "chi_abs", "energy", "specific_heat")

# The committed golden lives beside the tests so a plain checkout carries it.
GOLDEN_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "golden" / "determinism-l16-seed42.json"
)

GOLDEN_SCHEMA = "windowsill.determinism-golden.v1"

# Cross-platform numeric tolerance for the golden regression anchor, OWNED HERE
# (never read from the golden, so a drifting run can't widen its own gate). The
# strong determinism claim is the byte-identical *self*-rerun; this band only has
# to absorb last-ULP / different-torch-build float drift (which the chaotic
# Metropolis trajectory can amplify off the shared seed) while still catching a
# genuine regression, which moves a value by ≫10% or changes the output's shape.
GOLDEN_RTOL = 0.10
GOLDEN_ATOL = 1e-3


def _lazy_ising():
    # Imported lazily so `lab verify` (stdlib milestone regrade) and `import
    # lab.determinism` stay torch-free until a smoke rerun is actually asked for.
    from . import ising
    return ising


def measure() -> dict:
    """Run the pinned smoke config on the CPU and return its canonical measurement.

    A plain dict of JSON-native types: the echoed ``config`` plus the six
    measurement arrays. Deterministic for a fixed seed on a fixed build.
    """
    ising = _lazy_ising()
    cfg = ising.RunConfig(**SMOKE_CONFIG)
    result = ising.run(cfg)
    payload = result.to_json()
    return {
        "config": {k: SMOKE_CONFIG[k] for k in sorted(SMOKE_CONFIG)},
        **{key: payload[key] for key in MEASUREMENT_KEYS},
    }


def canonical_json(measurement: dict) -> str:
    """Deterministic serialization of a canonical measurement (sorted, compact)."""
    return json.dumps(measurement, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha(measurement: dict) -> str:
    """SHA-256 of the canonical measurement bytes."""
    return hashlib.sha256(canonical_json(measurement).encode("utf-8")).hexdigest()


def provenance() -> dict:
    """A small fingerprint of the environment that blessed a golden."""
    try:
        import torch
        torch_v = torch.__version__
    except Exception:  # pragma: no cover - torch always present where this runs
        torch_v = "unavailable"
    try:
        import numpy
        numpy_v = numpy.__version__
    except Exception:  # pragma: no cover
        numpy_v = "unavailable"
    return {
        "torch": torch_v,
        "numpy": numpy_v,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


def build_golden() -> dict:
    """Assemble a fresh golden artifact from a smoke run (config + measurement + sha)."""
    measurement = measure()
    return {
        "schema": GOLDEN_SCHEMA,
        "config": measurement["config"],
        "measurement": measurement,
        "sha256": canonical_sha(measurement),
        "provenance": provenance(),
        "note": (
            "Golden-seed determinism anchor for the L=16 seed=42 CPU smoke run. "
            "Regenerate with `python -m lab.cli verify --rerun-smoke --bless`."
        ),
    }


def write_golden(path: Path | None = None) -> Path:
    """Bless (write) the golden artifact and return its path."""
    path = path or GOLDEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_golden(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_golden(path: Path | None = None) -> dict:
    path = path or GOLDEN_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _numeric_agreement(fresh: dict, golden_meas: dict) -> tuple[bool, str, float]:
    """Structural + tolerant numeric comparison of two canonical measurements.

    Returns ``(ok, detail, max_rel_dev)``. Structural mismatches (keys, config,
    array lengths) fail hard and platform-independently; numeric drift fails only
    when it exceeds the check-owned ``|a-b| <= ATOL + RTOL*|b|`` band.
    """
    if set(fresh) != set(golden_meas):
        return False, "canonical field set differs from the golden (structural regression)", float("inf")
    if fresh.get("config") != golden_meas.get("config"):
        return False, "smoke config no longer matches the golden's pinned config", float("inf")

    max_rel = 0.0
    worst = ""
    n = 0
    for key in MEASUREMENT_KEYS:
        a, b = fresh.get(key), golden_meas.get(key)
        if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
            return False, f"array '{key}' length/type differs from the golden (structural regression)", float("inf")
        for i, (x, y) in enumerate(zip(a, b)):
            n += 1
            dev = abs(float(x) - float(y))
            tol = GOLDEN_ATOL + GOLDEN_RTOL * abs(float(y))
            rel = dev / (abs(float(y)) + GOLDEN_ATOL)
            if rel > max_rel:
                max_rel, worst = rel, f"{key}[{i}]: {float(x):.6g} vs {float(y):.6g}"
            if dev > tol:
                return False, (
                    f"measurement diverged from the golden beyond tolerance at {key}[{i}]: "
                    f"{float(x):.6g} vs {float(y):.6g} (Δ={dev:.3g} > {tol:.3g}) — a regression, "
                    f"not last-ULP platform drift"
                ), max_rel
    return True, f"numerically reproduces the golden across {n} values (max Δrel={max_rel:.2%}, ≤{GOLDEN_RTOL:.0%})", max_rel


def run_gate(golden_path: Path | None = None) -> dict:
    """Run the determinism gate. Returns a result dict; ``ok`` folds into exit code.

    Result keys: ``ok`` (bool), ``self_deterministic`` (bool), ``golden`` (one of
    ``bit-exact`` / ``numeric`` / ``regression`` / ``missing``), ``detail`` (str),
    and ``sha``/``golden_sha`` for the record.
    """
    m1 = measure()
    m2 = measure()
    s1, s2 = canonical_sha(m1), canonical_sha(m2)
    if s1 != s2:
        return {
            "ok": False,
            "self_deterministic": False,
            "golden": "n/a",
            "detail": (
                "NON-DETERMINISTIC: two reruns of the pinned L=16 seed=42 CPU config "
                f"disagree ({s1[:12]}… vs {s2[:12]}…) — the RNG seeding or an op is not "
                "reproducible"
            ),
            "sha": s1,
            "golden_sha": None,
        }

    path = golden_path or GOLDEN_PATH
    if not path.exists():
        return {
            "ok": False,
            "self_deterministic": True,
            "golden": "missing",
            "detail": (
                f"self-deterministic (sha {s1[:12]}…) but no committed golden at {path} — "
                "bless one with `lab verify --rerun-smoke --bless`"
            ),
            "sha": s1,
            "golden_sha": None,
        }

    golden = load_golden(path)
    golden_sha = golden.get("sha256")
    if s1 == golden_sha:
        return {
            "ok": True,
            "self_deterministic": True,
            "golden": "bit-exact",
            "detail": f"reproduces the committed golden bit-for-bit (sha {s1[:12]}…)",
            "sha": s1,
            "golden_sha": golden_sha,
        }

    ok, detail, _max_rel = _numeric_agreement(m1, golden.get("measurement") or {})
    blessed_on = (golden.get("provenance") or {}).get("platform", "an unrecorded platform")
    if ok:
        return {
            "ok": True,
            "self_deterministic": True,
            "golden": "numeric",
            "detail": (
                f"self-deterministic; {detail} (bit-level drift vs the golden blessed on "
                f"{blessed_on} — expected across torch builds/platforms)"
            ),
            "sha": s1,
            "golden_sha": golden_sha,
        }
    return {
        "ok": False,
        "self_deterministic": True,
        "golden": "regression",
        "detail": f"self-deterministic but {detail}",
        "sha": s1,
        "golden_sha": golden_sha,
    }
