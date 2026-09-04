"""Which three lattices the gallery shows — and the compatibility guarantee.

The page's triptych captions its middle frame "near the tipping point". Since the
repo's first commit (2026-06-08) that frame was the sweep's POSITIONAL midpoint,
``n_temps // 2``, which is the critical frame only if T_c happens to sit at the
centre of the temperature window. On the M01 heartbeat it does not: T runs
1.5 → 3.5 over 21 points, so the midpoint is T = 2.5, where the 2026-08-30 run
measures ⟨|m|⟩ ≈ 0.047 — a nearly-disordered lattice — while that same run's χ'
peak is index 8, T = 2.3, ⟨|m|⟩ ≈ 0.264, one grid step from Onsager's exact
T_c = 2.269. The page showed thermal noise under a caption claiming criticality.

Two things are pinned here, and the second matters as much as the first:

* with a peak observable, the middle frame is the run's OWN argmax;
* with ``peak_observable=None`` the result is byte-identical to the old literal
  ``[0, n_temps // 2, n_temps - 1]``, so every engine that abstains — ``xy``
  (θ angles, no symmetry-breaking order parameter), ``potts`` (q-state labels,
  no ⟨|m|⟩-based χ'), ``ising_afm`` (staggered order parameter), and
  ``ising_tri_afm`` (no finite-T transition at all) — is provably unchanged.

Snapshots are excluded from ``determinism.MEASUREMENT_KEYS``, so none of this
touches the golden hashes; ``test_snapshots_are_outside_the_graded_measurement``
below pins that rather than assuming it.
"""
from __future__ import annotations

import math

import pytest

from lab import determinism
from lab.ising import snapshot_indices


# ── The compatibility guarantee ─────────────────────────────────────────────


@pytest.mark.parametrize("n_temps", list(range(1, 40)))
def test_no_observable_reproduces_the_legacy_positional_midpoint_exactly(n_temps):
    """The literal every engine used before this helper existed, unchanged."""
    assert snapshot_indices(n_temps) == [0, n_temps // 2, n_temps - 1]
    assert snapshot_indices(n_temps, None) == [0, n_temps // 2, n_temps - 1]


@pytest.mark.parametrize("engine_name", [
    "xy", "potts", "ising_afm", "ising_tri_afm",
])
def test_abstaining_engines_pass_no_observable(engine_name):
    """The abstention is in the source, not just in a docstring.

    ``xy`` is the one that must NEVER gain an observable: it snapshots θ angles,
    not spins, and the BKT transition has no diverging χ' peak to point at. The
    other three abstain for reasons recorded at their call sites.
    """
    import inspect

    from lab import ising_afm, ising_tri_afm, potts, xy

    module = {"xy": xy, "potts": potts,
              "ising_afm": ising_afm, "ising_tri_afm": ising_tri_afm}[engine_name]
    source = inspect.getsource(module)
    calls = [
        line.strip() for line in source.splitlines()
        if "snapshot_indices(" in line and "pick_idx" in line
    ]
    assert len(calls) == 1, f"{engine_name}: expected exactly one snapshot pick"
    assert calls[0].endswith("n_temps)"), (
        f"{engine_name} passes a peak observable: {calls[0]!r}"
    )


@pytest.mark.parametrize("engine_name", [
    "ising", "ising_hex", "ising_tri", "wolff", "wolff3d",
])
def test_spin_lattice_engines_pass_their_own_chi_abs(engine_name):
    """Every engine whose snapshot is a ±1 spin lattice with a χ' curve uses it."""
    import inspect
    import importlib

    module = importlib.import_module(f"lab.{engine_name}")
    calls = [
        line.strip() for line in inspect.getsource(module).splitlines()
        if "snapshot_indices(" in line and "pick_idx" in line
    ]
    assert len(calls) == 1, f"{engine_name}: expected exactly one snapshot pick"
    assert calls[0].endswith("chi_abs)"), (
        f"{engine_name} does not use its own χ': {calls[0]!r}"
    )


# ── The fix: the middle frame follows the measurement ───────────────────────


def test_the_m01_heartbeat_shape_moves_off_the_midpoint_onto_the_chi_peak():
    """The exact geometry of the live M01 sweep, with a peak where it measures one.

    21 points from 1.5 to 3.5 → the positional midpoint is index 10 (T = 2.5).
    The measured χ' peak is index 8 (T = 2.3). Before this helper the gallery
    showed index 10 and captioned it critical.
    """
    n_temps = 21
    T = [1.5 + i * (3.5 - 1.5) / (n_temps - 1) for i in range(n_temps)]
    chi_abs = [1.0 / (1.0 + abs(t - 2.3) * 40) for t in T]

    assert snapshot_indices(n_temps) == [0, 10, 20]
    assert snapshot_indices(n_temps, chi_abs) == [0, 8, 20]
    assert abs(T[8] - 2.3) < 1e-9


def test_three_distinct_frames_are_always_returned_for_a_real_sweep():
    chosen = snapshot_indices(21, [0.0] * 8 + [9.0] + [0.0] * 12)
    assert len(set(chosen)) == 3
    assert chosen[0] == 0 and chosen[-1] == 20


def test_a_tie_resolves_to_the_lowest_index_so_a_run_is_reproducible():
    assert snapshot_indices(5, [0.0, 3.0, 3.0, 1.0, 0.0]) == [0, 1, 4]


# ── Degenerate observables never move the picture ───────────────────────────


@pytest.mark.parametrize("observable, why", [
    ([9.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "peak on the coldest index"),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 9.0], "peak on the hottest index"),
    ([1.0, 2.0], "wrong length"),
    ([0.0, 9.0, math.nan, 0.0, 0.0, 0.0, 0.0], "carries a NaN"),
    ([0.0, 9.0, math.inf, 0.0, 0.0, 0.0, 0.0], "carries an infinity"),
    (["a"] * 7, "not numeric"),
    (3.0, "not a sequence"),
    ([0.0] * 7, "flat — no peak anywhere"),
])
def test_a_degenerate_observable_falls_back_to_the_legacy_midpoint(observable, why):
    """A curve that cannot name a critical frame must not be allowed to move one.

    A peak on an endpoint is the interesting case: the triptych needs three
    DISTINCT frames, and an endpoint peak means the sweep never bracketed the
    transition — so there is no interior critical frame to show and the cold or
    hot panel is already showing it.
    """
    assert snapshot_indices(7, observable) == [0, 3, 6], why


# ── The golden gate is untouched, verified rather than assumed ──────────────


def test_snapshots_are_outside_the_graded_measurement():
    """Determinism grades six curves; the lattice gallery is not one of them.

    So moving which three lattices get saved cannot move a golden hash. Pinned
    here because "snapshots aren't graded" is exactly the kind of claim that is
    true until someone adds a key.
    """
    assert "snapshots" not in determinism.MEASUREMENT_KEYS
    assert "snapshot_peak_t" not in determinism.MEASUREMENT_KEYS
    assert set(determinism.MEASUREMENT_KEYS) == {
        "T", "abs_mag", "chi", "chi_abs", "energy", "specific_heat",
    }
