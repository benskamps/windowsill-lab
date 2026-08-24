"""P01 — fold HP sequences blind and recover ground states proven in-house.

The graded claim is narrow on purpose: **for chains short enough that every
self-avoiding walk can be visited, a Monte-Carlo search told nothing about the
answer recovers the energy exhaustive enumeration proves.** That is a folding
result whose target this lab computed rather than cited, so nothing in the gate
depends on a number anybody remembered.

THREE CONTROLS, EACH ANSWERING A DIFFERENT DOUBT
    * **Enumeration** answers "is the target real?" — it is proven, not looked
      up, and the receipt carries how much of the tree was walked to prove it.
    * **Parity** answers "is the energy function even right?" A square lattice
      is bipartite, so beads at even sequence positions can only ever touch
      beads at odd ones. A sequence whose H beads all sit on one parity
      therefore has EXACTLY zero H-H contacts available, by geometry rather
      than by search — and both the enumerator and the sampler must return 0.
      No fit, no tolerance, an integer that cannot be argued with.
    * **Shuffle** answers "does the search work on a sequence nobody designed?"
      The same beads in a scrambled order are enumerated AND folded under an
      identical budget, and the search must recover that sequence's optimum too.

      The first draft of this control graded a shuffle that folded LOWER than
      the original as a failure, on the reasoning that composition should not
      beat arrangement. That is wrong, and the run caught it: HHHPPPHHHPP has
      optimum -2 while a permutation of it reaches -3. A permutation is simply a
      different sequence with its own ground state, and clustering hydrophobics
      genuinely lowers energy — that IS the model's physics. The comparison is
      kept as a reported diagnostic (arrangement matters, in both directions)
      and the gate asks the only question a control can honestly ask here:
      whether the search finds the proven optimum of whatever it is handed.

THE RECEIPT IS THE FOLD ITSELF
    Every reported conformation carries its coordinates, so ``check_p01``
    recomputes the energy from geometry and re-validates self-avoidance instead
    of trusting the number in the file.

BOUNDARY
    The HP model is a coarse-grained lattice abstraction of hydrophobic
    collapse. Recovering its ground states says nothing about real tertiary
    structure, and no claim about actual proteins is made or implied. This is
    an NP-hard combinatorial benchmark that folding methods are measured on,
    which is exactly why it is worth being able to solve.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import hp_lattice as hp

#: The graded set, declared before any of them was folded. Lengths chosen so
#: exhaustive enumeration is provable in seconds, with a mix of clustered and
#: interleaved hydrophobics so the answer is not one geometry repeated.
GRADED: tuple[str, ...] = (
    "HPHPPHHPHH",        # 10 — interleaved
    "HHPPHPPHPH",        # 10 — clustered head
    "HHHPPPHHHPP",       # 11 — two blocks
    "HPPHPHHPHPPH",      # 12 — symmetric-ish
    "HHPHPPHPPHPH",      # 12 — sparse tail
    "PHPHHPPHPHHPP",     # 13
    "HHPPHPHPHPPHH",     # 13 — palindromic hydrophobics
)

#: Parity controls: every H sits on an even sequence index, so on a bipartite
#: lattice no two of them can ever be neighbours. E* = 0 exactly, by geometry.
PARITY_CONTROLS: tuple[str, ...] = (
    "HPHPHPHPHP",
    "HPHPHPHPHPHP",
)

#: Longer chains, reported and never graded: enumeration is out of reach, so
#: "best found" is a search result and not a proven optimum. Saying which is
#: which is the whole point of keeping them in separate lists.
REPORTED: tuple[str, ...] = (
    "HPHPPHHPHPPHPHHPPHPH",              # 20
    "HHPPHPPHPPHPPHPPHPPHPPHH",          # 24
)

SWEEPS_GRADED = 20_000
SWEEPS_REPORTED = 60_000
N_REPLICAS = 8


@dataclass
class P01Result:
    graded: list = field(default_factory=list)
    parity: list = field(default_factory=list)
    reported: list = field(default_factory=list)
    wall_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return (bool(self.graded)
                and all(r["recovered"] for r in self.graded)
                and all(r["energy"] == 0 and r["enumerated"] == 0 for r in self.parity)
                and all(r["shuffle_recovered"] for r in self.graded))


def _fold_and_prove(seq: str, seed: int, sweeps: int) -> dict:
    """Prove the optimum by enumeration, then search for it blind."""
    proof = hp.enumerate_ground_state(seq)
    found = hp.fold(seq, n_sweeps=sweeps, n_replicas=N_REPLICAS, seed=seed)
    # Same beads, scrambled order, identical budget — the composition control.
    rng = np.random.default_rng(seed + 7919)
    shuffled = "".join(rng.permutation(list(seq)))
    shuffle_proof = hp.enumerate_ground_state(shuffled)
    shuffle = hp.fold(shuffled, n_sweeps=sweeps, n_replicas=N_REPLICAS, seed=seed)
    return {
        "sequence": seq,
        "length": len(seq),
        "enumerated": proof["energy"],
        "nodes_visited": proof["nodes_visited"],
        "energy": found["energy"],
        "coords": found["coords"],
        "recovered": bool(found["energy"] == proof["energy"]),
        "swap_health": found["swap_health"],
        "swap_rate_min": float(min(found["swap_rate"])),
        "shuffled_sequence": shuffled,
        "shuffle_energy": shuffle["energy"],
        "shuffle_enumerated": shuffle_proof["energy"],
        "shuffle_recovered": bool(shuffle["energy"] == shuffle_proof["energy"]),
        "sweeps": sweeps,
        "seed": seed,
    }


def run_p01(graded=GRADED, parity=PARITY_CONTROLS, reported=REPORTED,
            progress=None) -> P01Result:
    t0 = time.time()
    result = P01Result()
    for i, seq in enumerate(graded):
        row = _fold_and_prove(seq, seed=1000 + i, sweeps=SWEEPS_GRADED)
        result.graded.append(row)
        if progress:
            progress("graded", row)
    for i, seq in enumerate(parity):
        proof = hp.enumerate_ground_state(seq)
        found = hp.fold(seq, n_sweeps=SWEEPS_GRADED, n_replicas=N_REPLICAS,
                        seed=2000 + i)
        row = {"sequence": seq, "length": len(seq), "enumerated": proof["energy"],
               "energy": found["energy"], "coords": found["coords"],
               "reason": "all H beads on one sequence parity — bipartite lattice "
                         "forbids any H-H contact"}
        result.parity.append(row)
        if progress:
            progress("parity", row)
    for i, seq in enumerate(reported):
        found = hp.fold(seq, n_sweeps=SWEEPS_REPORTED, n_replicas=N_REPLICAS,
                        seed=3000 + i)
        row = {"sequence": seq, "length": len(seq), "energy": found["energy"],
               "coords": found["coords"], "swap_health": found["swap_health"],
               "sweeps": SWEEPS_REPORTED,
               "claim": "best found — not proven optimal (enumeration out of reach)"}
        result.reported.append(row)
        if progress:
            progress("reported", row)
    result.wall_seconds = time.time() - t0
    return result


def to_report(result: P01Result) -> dict:
    return {
        "milestone": "P01",
        "experiment": "P01-hp-lattice-folding",
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": "2D square-lattice HP (Dill); E = -(H-H contacts non-adjacent in chain)",
        "counts": {
            "graded": len(result.graded),
            "recovered": sum(1 for r in result.graded if r["recovered"]),
            "parity_controls": len(result.parity),
            "reported_only": len(result.reported),
        },
        "graded": result.graded,
        "parity_controls": result.parity,
        "reported": result.reported,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "Ground states of a coarse-grained lattice model, proven by exhaustive "
            "enumeration for the graded chains and searched blind. No claim about "
            "real protein structure is made or implied."
        ),
    }
