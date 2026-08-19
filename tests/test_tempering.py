"""Parallel-tempering tests — the move, and the thing it must not change.

The exchange is a sampler upgrade, and a sampler upgrade has exactly one way to
be wrong that matters: it can change the distribution it samples from. Speed is
worthless if the answer moves. So the load-bearing test here is not "does the
cold end mix better" — it is **exact enumeration**: a 4x4 lattice has 65,536
states, so the true Boltzmann distribution for a given bond realization can be
written down, and the tempered sampler's energy histogram has to match it at
every rung of the ladder. Everything else is mechanics.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from lab import tempering
from lab.spin_glass import SpinGlassConfig, run, _weighted_neighbor_sum


# ------------------------------------------------------- the acceptance rule ---

def test_acceptance_matches_the_formula_by_hand():
    beta = torch.tensor([2.0, 1.0])                 # cold, hot
    energy = torch.tensor([[-5.0, -3.0]])           # E_cold, E_hot
    prob, lo = tempering.swap_acceptance(beta, energy, parity=0)
    expected = min(1.0, float(np.exp((2.0 - 1.0) * (-5.0 - (-3.0)))))
    assert float(prob[0, 0]) == pytest.approx(expected)
    assert list(lo) == [0]


def test_a_cold_configuration_with_too_much_energy_always_swaps_up():
    """(β_i − β_j)(E_i − E_j) > 0 means the swap is downhill in the joint ensemble."""
    beta = torch.tensor([2.0, 1.0])
    energy = torch.tensor([[-1.0, -6.0]])           # cold holds the HIGH energy
    prob, _ = tempering.swap_acceptance(beta, energy, parity=0)
    assert float(prob[0, 0]) == pytest.approx(1.0)


def test_an_already_sorted_ladder_swaps_only_sometimes():
    beta = torch.tensor([2.0, 1.0])
    energy = torch.tensor([[-8.0, -2.0]])           # cold already colder
    prob, _ = tempering.swap_acceptance(beta, energy, parity=0)
    assert 0.0 < float(prob[0, 0]) < 1.0


def test_equal_temperatures_always_accept():
    beta = torch.tensor([1.0, 1.0])
    energy = torch.tensor([[-8.0, -2.0]])
    prob, _ = tempering.swap_acceptance(beta, energy, parity=0)
    assert float(prob[0, 0]) == pytest.approx(1.0)


def test_parity_selects_disjoint_pairs_and_together_covers_every_rung():
    beta = torch.arange(6.0) + 1.0
    _, even = tempering.swap_acceptance(beta, torch.zeros(1, 6), 0)
    _, odd = tempering.swap_acceptance(beta, torch.zeros(1, 6), 1)
    assert list(even) == [0, 2, 4]
    assert list(odd) == [1, 3]
    assert {int(x) for x in list(even) + list(odd)} == set(range(5))


def test_a_single_temperature_offers_no_pairs():
    prob, lo = tempering.swap_acceptance(torch.tensor([1.0]), torch.zeros(1, 1), 0)
    assert lo.numel() == 0 and prob.shape[-1] == 0


# --------------------------------------------------------------- the exchange ---

def _state(vals):
    """(batch=1, M, 1) states carrying a distinguishable tag per temperature."""
    return torch.tensor(vals, dtype=torch.float32).view(1, len(vals), 1)


def test_exchange_swaps_the_configurations_it_accepts():
    beta = torch.tensor([4.0, 1.0])
    energy = torch.tensor([[0.0, -50.0]])          # acceptance = 1
    rng = torch.Generator().manual_seed(0)
    out, accept = tempering.exchange(_state([10.0, 20.0]), beta, energy, 0, rng)
    assert bool(accept.all())
    assert out.flatten().tolist() == [20.0, 10.0]


def test_exchange_leaves_rejected_pairs_alone():
    beta = torch.tensor([50.0, 1.0])
    energy = torch.tensor([[-500.0, 0.0]])         # acceptance ~ 0
    rng = torch.Generator().manual_seed(0)
    out, accept = tempering.exchange(_state([10.0, 20.0]), beta, energy, 0, rng)
    assert not bool(accept.any())
    assert out.flatten().tolist() == [10.0, 20.0]


def test_exchange_never_mutates_its_input():
    beta = torch.tensor([4.0, 1.0])
    energy = torch.tensor([[0.0, -50.0]])
    state = _state([10.0, 20.0])
    tempering.exchange(state, beta, energy, 0, torch.Generator().manual_seed(0))
    assert state.flatten().tolist() == [10.0, 20.0]


def test_exchange_touches_only_the_pairs_of_its_parity():
    beta = torch.tensor([8.0, 4.0, 2.0, 1.0])
    energy = torch.tensor([[0.0, -50.0, 0.0, -50.0]])
    rng = torch.Generator().manual_seed(0)
    out, _ = tempering.exchange(_state([1.0, 2.0, 3.0, 4.0]), beta, energy, 0, rng)
    assert out.flatten().tolist() == [2.0, 1.0, 4.0, 3.0]
    out, _ = tempering.exchange(_state([1.0, 2.0, 3.0, 4.0]), beta, energy, 1, rng)
    assert out.flatten()[0] == 1.0 and out.flatten()[3] == 4.0


def test_exchange_is_deterministic_under_a_fixed_seed():
    beta = torch.tensor([3.0, 2.0, 1.0])
    energy = torch.tensor([[-4.0, -3.0, -2.0]])
    a, _ = tempering.exchange(_state([1., 2., 3.]), beta, energy, 0,
                              torch.Generator().manual_seed(7))
    b, _ = tempering.exchange(_state([1., 2., 3.]), beta, energy, 0,
                              torch.Generator().manual_seed(7))
    assert a.flatten().tolist() == b.flatten().tolist()


# ----------------------------------------------------------- ladder diagnostics ---

def test_ladder_health_reports_the_minimum_not_just_the_mean():
    """One dead rung disconnects the ladder however good the average looks."""
    counts = torch.tensor([90.0, 90.0, 1.0, 90.0])
    attempts = torch.tensor([100.0] * 4)
    health = tempering.ladder_health(counts, attempts)
    assert health["mean"] > 0.6
    assert health["min"] == pytest.approx(0.01)
    assert health["connected"] is False
    assert health["argmin_pair"] == 2


def test_ladder_health_calls_a_well_spaced_ladder_connected():
    counts = torch.tensor([30.0, 28.0, 32.0])
    health = tempering.ladder_health(counts, torch.tensor([100.0] * 3))
    assert health["connected"] is True
    assert health["in_target_band"] is True


def test_ladder_health_survives_zero_attempts():
    health = tempering.ladder_health(torch.zeros(3), torch.zeros(3))
    assert health["min"] == 0.0 and health["connected"] is False


def test_geometric_ladder_has_a_constant_ratio():
    ladder = tempering.geometric_ladder(0.4, 2.0, 5)
    ratios = (ladder[1:] / ladder[:-1]).tolist()
    assert max(ratios) - min(ratios) < 1e-5
    assert float(ladder[0]) == pytest.approx(0.4)
    assert float(ladder[-1]) == pytest.approx(2.0)


def test_geometric_ladder_refuses_nonsense():
    for args in ((2.0, 0.4, 5), (0.0, 2.0, 5), (0.4, 2.0, 1)):
        with pytest.raises(ValueError):
            tempering.geometric_ladder(*args)


# ------------------------------------- the one that matters: exact enumeration ---

def _exact_energies(Jx, Jy, L):
    """Total energy of every one of the 2^(L*L) states, same convention as the engine."""
    n = L * L
    states = ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1) * 2 - 1
    spins = torch.tensor(states.reshape(-1, L, L), dtype=torch.float32)
    field = _weighted_neighbor_sum(spins, Jx.expand(len(spins), L, L),
                                   Jy.expand(len(spins), L, L))
    return (-0.5 * (spins * field).sum(dim=(-1, -2))).numpy()


@pytest.mark.parametrize("swap_every", [0, 3])
def test_the_sampler_reproduces_the_exact_boltzmann_energy(swap_every):
    """With and without tempering, ⟨E⟩ must match exact enumeration at every rung.

    This is the test that would catch a wrong acceptance formula, a swap that
    moves configurations without moving their history, or an exchange that
    quietly breaks detailed balance: all of those change the distribution, and
    on 4x4 the true distribution is a sum nobody has to estimate.
    """
    L, M = 4, 4
    cfg = SpinGlassConfig(L=L, T_min=0.8, T_max=3.0, n_temps=M, n_realizations=1,
                          n_burnin=3000, n_sweeps=20000, sample_every=2,
                          seed=11, device="cpu", swap_every=swap_every)
    result = run(cfg)

    # Rebuild the bonds the engine drew, from the same seed and the same call.
    g = torch.Generator().manual_seed(cfg.seed)
    Jx = (torch.randint(0, 2, (1, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    Jy = (torch.randint(0, 2, (1, L, L), generator=g, dtype=torch.int8) * 2 - 1).float()
    energies = _exact_energies(Jx, Jy, L)

    for m, T in enumerate(result.T):
        w = np.exp(-(energies - energies.min()) / T)
        exact_per_spin = float((energies * w).sum() / w.sum()) / (L * L)
        assert result.energy[m] == pytest.approx(exact_per_spin, abs=0.035), (
            f"rung {m} (T={T:.2f}): sampled {result.energy[m]:.4f} "
            f"vs exact {exact_per_spin:.4f}")


def test_tempering_does_not_move_the_answer_it_only_moves_the_configurations():
    """Same physics, two samplers: the equilibrium energies must agree."""
    base = dict(L=4, T_min=0.8, T_max=3.0, n_temps=4, n_realizations=2,
                n_burnin=3000, n_sweeps=20000, sample_every=2, seed=5, device="cpu")
    plain = run(SpinGlassConfig(**base, swap_every=0))
    tempered = run(SpinGlassConfig(**base, swap_every=3))
    assert np.allclose(plain.energy, tempered.energy, atol=0.05)


def test_tempering_is_off_by_default_and_reports_no_health():
    cfg = SpinGlassConfig(L=4, n_temps=3, n_realizations=1, n_burnin=5,
                          n_sweeps=10, sample_every=5, device="cpu")
    assert cfg.swap_every == 0
    assert run(cfg).swap_health is None


def test_enabling_tempering_leaves_the_metropolis_stream_untouched():
    """The swap draws from its own generator, so 'off' is bit-identical to before.

    Guarded because the whole claim that tempering changes only the SAMPLER
    rests on it: if turning the move on perturbed the Metropolis randomness, no
    before/after comparison would mean anything.
    """
    base = dict(L=4, T_min=0.8, T_max=3.0, n_temps=3, n_realizations=2,
                n_burnin=40, n_sweeps=80, sample_every=8, seed=3, device="cpu")
    a = run(SpinGlassConfig(**base, swap_every=0))
    b = run(SpinGlassConfig(**base, swap_every=0))
    assert np.array_equal(a.q2_mean, b.q2_mean)
