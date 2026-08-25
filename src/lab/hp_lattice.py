"""The HP lattice model — the lab's first biology engine.

Dill's hydrophobic-polar model: a protein is a string of H and P beads folded
onto a square lattice as a self-avoiding walk, and its energy is minus the
number of H-H contacts that are neighbours on the lattice but NOT neighbours
along the chain. Nothing else. It is the standard coarse-grained abstraction of
the one force that drives folding — hydrophobic collapse — and finding its
ground state is NP-hard, which is why it survived thirty years as a benchmark.

WHY THIS SHAPE, GIVEN THIS LAB'S METHOD
    Every result here recovers a known answer blind and lets a checker
    re-derive it. The obvious way to do that for folding is to grade against
    published benchmark energies — but that would put a number I remembered
    into the gate, and hand-typed constants going stale is a failure this
    estate has already priced (``safety/pz-facts.md`` shrank for exactly that).

    So the answer is computed here instead. For short chains the ground state
    is EXHAUSTIVELY ENUMERABLE: every self-avoiding walk is visited and the
    true minimum is proven, not cited. The sampler is then run blind against
    the same sequence and has to find what enumeration proved. A positive
    control whose answer we own.

THE RECEIPT IS THE FOLD
    Reported conformations carry their coordinates, so ``check_p01`` recomputes
    the energy and re-validates self-avoidance from the geometry itself rather
    than trusting a reported number — a receipt, not an echo.
"""
from __future__ import annotations

import numpy as np

#: The four lattice steps on a square lattice, as (dx, dy).
STEPS: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

#: The eight symmetries of the square (rotations x reflections). A walk and its
#: images have identical energy, so enumeration explores one representative.
_ROTATIONS = ((1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0),
              (-1, 0, 0, 1), (1, 0, 0, -1), (0, 1, 1, 0), (0, -1, -1, 0))


def parse_sequence(seq: str) -> np.ndarray:
    """``"HPPH"`` → boolean array, True where the bead is hydrophobic."""
    s = seq.strip().upper()
    if not s or any(c not in "HP" for c in s):
        raise ValueError("an HP sequence contains only H and P")
    return np.array([c == "H" for c in s], dtype=bool)


def is_self_avoiding(coords: np.ndarray) -> bool:
    """Every site occupied once, and every consecutive pair a unit step apart.

    Both halves matter: a walk that revisits a site is two beads in one place,
    and a walk with a longer step has teleported. A conformation failing either
    is not a fold, whatever its energy evaluates to.
    """
    coords = np.asarray(coords, dtype=int)
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 2:
        return False
    steps = np.abs(np.diff(coords, axis=0)).sum(axis=1)
    if not np.all(steps == 1):
        return False
    return len({tuple(p) for p in coords}) == len(coords)


def energy(coords: np.ndarray, is_h: np.ndarray) -> int:
    """E = −(H-H contacts): lattice neighbours that are NOT chain neighbours.

    Chain neighbours are excluded because their contact is forced by the
    backbone and carries no folding information — counting them would reward
    the sequence for existing.
    """
    coords = np.asarray(coords, dtype=int)
    is_h = np.asarray(is_h, dtype=bool)
    occupied = {tuple(p): i for i, p in enumerate(coords)}
    contacts = 0
    for i, p in enumerate(coords):
        if not is_h[i]:
            continue
        for dx, dy in STEPS:
            j = occupied.get((int(p[0]) + dx, int(p[1]) + dy))
            if j is None or j <= i or not is_h[j]:
                continue
            if j - i > 1:                      # not a backbone neighbour
                contacts += 1
    return -contacts


# ── the exact answer, for chains short enough to prove it ────────────────────

def enumerate_ground_state(seq: str, progress=None) -> dict:
    """Visit every self-avoiding walk and return the PROVEN minimum energy.

    Depth-first over the lattice with two prunings that cost no generality:

    * **Symmetry.** The first step is fixed to +x and the first turn that is
      not along the axis is fixed to +y, which quotients out all eight symmetries
      of the square. Every distinct fold is still visited exactly once, up to
      an isometry that cannot change its energy.
    * **Optimistic bound.** A partial walk cannot beat the incumbent if even
      giving every remaining H bead its maximum of two new contacts would not
      reach it, so that branch is abandoned. The bound is admissible: it can
      only ever over-estimate what remains.

    Returns the minimum energy, one witnessing conformation, and how much of
    the tree was actually walked — the last so the claim "exhaustive" is
    accompanied by its own cost rather than asserted.
    """
    is_h = parse_sequence(seq)
    n = len(is_h)
    if n < 2:
        raise ValueError("a chain needs at least two beads")

    coords = np.zeros((n, 2), dtype=int)
    coords[1] = (1, 0)                                   # symmetry: first step +x
    occupied = {(0, 0): 0, (1, 0): 1}
    best = {"energy": 0, "coords": None, "nodes": 0, "axis_broken": False}

    remaining_h = np.cumsum(is_h[::-1])[::-1]            # H beads at index >= i

    def contacts_of(idx: int, point: tuple[int, int]) -> int:
        if not is_h[idx]:
            return 0
        got = 0
        for dx, dy in STEPS:
            j = occupied.get((point[0] + dx, point[1] + dy))
            if j is not None and idx - j > 1 and is_h[j]:
                got += 1
        return got

    def walk(idx: int, e: int, axis_broken: bool) -> None:
        best["nodes"] += 1
        if idx == n:
            if e < best["energy"]:
                best["energy"] = e
                best["coords"] = coords.copy()
            return
        # Admissible bound: two new contacts is the most any bead can add.
        if e - 2 * int(remaining_h[idx]) >= best["energy"]:
            return
        px, py = int(coords[idx - 1][0]), int(coords[idx - 1][1])
        for dx, dy in STEPS:
            point = (px + dx, py + dy)
            if point in occupied:
                continue
            broken = axis_broken
            if not axis_broken and dy != 0:
                if dy < 0:
                    continue                              # symmetry: first turn is +y
                broken = True
            occupied[point] = idx
            coords[idx] = point
            walk(idx + 1, e - contacts_of(idx, point), broken)
            del occupied[point]
        if progress is not None and idx == 2:
            progress(best["nodes"])

    walk(2, 0, False)
    return {"sequence": seq, "energy": int(best["energy"]),
            "coords": best["coords"].tolist() if best["coords"] is not None else None,
            "nodes_visited": int(best["nodes"]), "exhaustive": True}


# ── the blind search ─────────────────────────────────────────────────────────

def _pivot(coords: np.ndarray, site: int, rot: tuple[int, int, int, int]) -> np.ndarray:
    """Rotate the tail after ``site`` about it. The classic SAW pivot move."""
    a, b, c, d = rot
    out = coords.copy()
    rel = coords[site + 1:] - coords[site]
    out[site + 1:, 0] = coords[site][0] + a * rel[:, 0] + b * rel[:, 1]
    out[site + 1:, 1] = coords[site][1] + c * rel[:, 0] + d * rel[:, 1]
    return out


def fold(seq: str, *, n_sweeps: int = 200_000, n_replicas: int = 8,
         t_min: float = 0.15, t_max: float = 1.5, seed: int = 0,
         swap_every: int = 20) -> dict:
    """Replica-exchange Monte Carlo for the ground state — told nothing.

    The sampler receives a sequence and a budget. It never sees a target
    energy, and nothing about the run's acceptance depends on one, so a
    recovered optimum is a search result rather than a lookup.

    Pivot moves on a temperature ladder, the same shape M12's spin glass uses
    and for the same reason: the landscape is rugged, and a single cold chain
    freezes into whichever funnel it fell down first. Rejected proposals
    (self-intersections) simply keep the current fold, which is the standard
    treatment for lattice SAW pivots.
    """
    is_h = parse_sequence(seq)
    n = len(is_h)
    rng = np.random.default_rng(seed)
    temps = np.geomspace(t_min, t_max, n_replicas)

    # Every replica starts from the straight rod — a legal, maximally unfolded
    # walk, and one that plants no information about the answer.
    chains = [np.stack([np.arange(n), np.zeros(n, dtype=int)], axis=1)
              for _ in range(n_replicas)]
    energies = [energy(c, is_h) for c in chains]
    best_e, best_c = min(energies), chains[int(np.argmin(energies))].copy()
    swaps_attempted = np.zeros(n_replicas - 1, dtype=int)
    swaps_accepted = np.zeros(n_replicas - 1, dtype=int)

    for sweep in range(n_sweeps):
        for r in range(n_replicas):
            site = int(rng.integers(0, n - 1))
            rot = _ROTATIONS[int(rng.integers(1, len(_ROTATIONS)))]
            cand = _pivot(chains[r], site, rot)
            if not is_self_avoiding(cand):
                continue
            e_new = energy(cand, is_h)
            de = e_new - energies[r]
            if de <= 0 or rng.random() < np.exp(-de / temps[r]):
                chains[r], energies[r] = cand, e_new
                if e_new < best_e:
                    best_e, best_c = e_new, cand.copy()
        if swap_every > 0 and sweep % swap_every == 0:
            parity = (sweep // swap_every) % 2
            for r in range(parity, n_replicas - 1, 2):
                swaps_attempted[r] += 1
                delta = (1.0 / temps[r] - 1.0 / temps[r + 1]) * (energies[r + 1] - energies[r])
                if delta <= 0 or rng.random() < np.exp(-delta):
                    swaps_accepted[r] += 1
                    chains[r], chains[r + 1] = chains[r + 1], chains[r]
                    energies[r], energies[r + 1] = energies[r + 1], energies[r]

    rate = swaps_accepted / np.maximum(swaps_attempted, 1)
    return {"sequence": seq, "energy": int(best_e), "coords": best_c.tolist(),
            "n_sweeps": int(n_sweeps), "n_replicas": int(n_replicas),
            "temperatures": temps.tolist(), "seed": int(seed),
            "swap_rate": rate.tolist(),
            "swap_health": "ok" if float(rate.min()) > 0.0 else
                           f"degraded — gaps never swapped: "
                           f"{[i for i, x in enumerate(rate) if x == 0.0]}"}


def enumerate_degeneracy(seq: str, target: int | None = None) -> dict:
    """Count EVERY conformation achieving the ground-state energy, exactly.

    `enumerate_ground_state` answers *what is the minimum*; it cannot answer
    *how many ways*, and not by omission — its bound prunes a branch that cannot
    **beat** the incumbent (``>= best``), which discards ties by construction.
    Degeneracy needs a bound that prunes only what cannot **reach** the target
    (``> target``), and a target fixed in advance so the criterion never moves
    mid-walk.

    Two passes: the existing enumerator proves E*, then this walks the tree again
    counting every conformation at E*. Both share the same symmetry quotient —
    first step +x, first non-axial turn +y — so the count is of distinct folds
    **up to the eight symmetries of the square**, which is the quantity
    designability is defined on.

    This is the rarest kind of number this lab can produce: **exact and provable,
    with no statistics, no equilibration argument, and no error bar to defend.**
    Either the tree was walked or it was not.
    """
    is_h = parse_sequence(seq)
    n = len(is_h)
    if n < 2:
        raise ValueError("a chain needs at least two beads")
    if target is None:
        target = int(enumerate_ground_state(seq)["energy"])

    coords = np.zeros((n, 2), dtype=int)
    coords[1] = (1, 0)
    occupied = {(0, 0): 0, (1, 0): 1}
    remaining_h = np.cumsum(is_h[::-1])[::-1]
    stats = {"count": 0, "nodes": 0}

    def contacts_of(idx: int, point: tuple[int, int]) -> int:
        if not is_h[idx]:
            return 0
        got = 0
        for dx, dy in STEPS:
            j = occupied.get((point[0] + dx, point[1] + dy))
            if j is not None and idx - j > 1 and is_h[j]:
                got += 1
        return got

    def walk(idx: int, e: int, axis_broken: bool) -> None:
        stats["nodes"] += 1
        if idx == n:
            if e == target:
                stats["count"] += 1
            return
        # Prunes only what cannot REACH the target — ties survive, which is the
        # single line that separates counting from minimising.
        if e - 2 * int(remaining_h[idx]) > target:
            return
        px, py = int(coords[idx - 1][0]), int(coords[idx - 1][1])
        for dx, dy in STEPS:
            point = (px + dx, py + dy)
            if point in occupied:
                continue
            broken = axis_broken
            if not axis_broken and dy != 0:
                if dy < 0:
                    continue
                broken = True
            occupied[point] = idx
            coords[idx] = point
            walk(idx + 1, e - contacts_of(idx, point), broken)
            del occupied[point]

    walk(2, 0, False)
    return {"sequence": seq, "energy": target, "degeneracy": stats["count"],
            "nodes": stats["nodes"], "unique": stats["count"] == 1}
