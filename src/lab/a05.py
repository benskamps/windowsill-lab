"""A05 — the survey-grade hunt: orchestrator, receipt, and the run pipeline.

A04 proved the instrument (blind BLS + vetting recovers known planets and
measures its own false-alarm floor). The wave-1 A05 modules sharpened it:
:mod:`lab.a05_stats` gives every graded candidate a per-target permutation FAP,
:mod:`lab.a05_vetting` replaces harmonic inference with a measured pulsation
spectrum plus pixel-level blend gates, and :mod:`lab.a05_sensitivity` turns the
binary injection control into a per-host depth limit with a whole-pipeline
placebo. This module WIRES them into one pipeline whose output is the hunt
receipt of ``docs/a05-receipt-schema.md`` — the cross-lane contract that
``checks.check_a05`` re-derives without trust.

### The disposition ladder — every above-threshold row earns a machine word

An SDE >= 8 detection walks a fixed ladder and stops at the first rung that
names it:

1. **extended_vet** (:func:`lab.a05_vetting.extended_vet`): pulsation
   commensurability first (measured frequency as evidence), then A04's rail /
   odd-even / secondary / brightening / alias gates on the PREWHITENED flux.
2. **centroid gate**: a vetting survivor whose in-transit centroid points at a
   neighbour is ``centroid-shift`` — the pixels say the lost light was not the
   target's. Crowding bookkeeping (CROWDSAP) rides along as reported evidence
   either way, full structured dicts under ``disposition_evidence.blend``.
3. **catalog cross-check, at report time only**: a survivor already known to
   the catalog is ``recovery-or-known`` — EXCEPT when the TOI table carries a
   community false-positive disposition. The 2026-08-14 wide hunt surfaced TIC
   278866211 at SDE 10.3 (P = 2.19516 d, 3790 ppm), vetting said
   planet-candidate — and the catalog says TOI 189.01, TFOPWG disposition FP.
   A community-refuted false positive is NOT a recovery (nothing real was
   re-found) and NOT a lead (humans already killed it); it gets its own word,
   ``toi-known-fp``, and serves as a free validation target for the blend
   gates. Treated the same: TFOPWG ``FA`` (false alarm). The inverse boundary
   (WASP-18): a CONFIRMED planet whose only physics verdict is the bare
   ``eclipsing-binary-secondary`` — its own occultation, expected physics,
   not an EB tell — is regraded ``known-planet`` with the verdict preserved
   as evidence; see :func:`resolve_catalog`.
4. **the terminal machine state**: an uncatalogued survivor is
   ``lead-awaiting-human-review`` with a full evidence dossier. The machine's
   vocabulary has no word for "planet" — contract rule 3.

### Stage 2 — who pays for the bootstrap

A B=256 permutation null costs ~257 periodograms, so only two kinds of target
pay: anything above the :func:`lab.a05_stats.triage_level` heuristic line, and
a PREDECLARED control subsample chosen by consistent hash of the TIC alone —
membership decided before any flux is seen, so the control ensemble is a true
random subsample and its iid-scheme FAPs calibrate the calibrator
(:func:`lab.a05_stats.uniformity_stat`). The uniformity block grades the IID
scheme's p-values deliberately: the graded ``fap_graded`` is the max of two
dependent p-values and is conservative BY CONSTRUCTION (stochastically larger
than uniform), so it would fail a uniformity test in the direction the design
chose on purpose; the iid empirical FAP is the exactly-exchangeable statistic
whose uniformity is the honest health check, and it still fails loudly when
the null is wrong for the data (red targets pile it near zero).

### Injection recovery — the honest field

:func:`lab.a05_sensitivity.injection_grid` grades recovery on the SDE
threshold (its lane-1 TODO). Swapping every injection onto the batched FAP
engine multiplies each host's ladder cost by ~B and is not affordable inside a
survey budget, so this module DECLARES the rule instead of hiding it: every
host's injection block carries ``injections_recovery_rule: "sde-threshold"``
(or ``"fap-injection-iid"`` when a run opts into ``injection_fap_B >= 100`` —
the per-injection number is a single-scheme reduced-B FAP, named so it can
never be confused with the row-level graded contract), and the check refuses
a receipt that omits the declaration. An honest label on the cheaper rule
beats a silent upgrade nobody can audit.

Numpy + stdlib only. Network touches (MAST, Exoplanet Archive) are injectable
callables so the whole pipeline runs on synthetic curves in tests.
"""
from __future__ import annotations

import hashlib
import inspect
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from . import (a01, a04, a05_fold, a05_physical, a05_sensitivity, a05_shape,
               a05_sky, a05_stats, a05_vetting)

EXPERIMENT = "a05-survey-hunt"
SCHEMA_VERSION = 1

#: Sample seed — same value as A04's, so the consistent-hash ranking is the
#: SAME deterministic ordering the graded run and the pilots used and "the next
#: slice" means what it says.
DEFAULT_SEED = 2026

#: Fraction of the slice predeclared into the uniformity control subsample by
#: consistent hash of the TIC. 0.1 of a 500-target slice gives the ~50-member
#: ensemble the receipt schema sizes its KS test for.
CONTROL_FRACTION = 0.10

#: Epoch-scrambled curves pushed through the FULL search+vet ladder at wrap.
N_PLACEBO = 25

#: TFOPWG dispositions that mean "the community already refuted this signal".
#: FP = false positive (astrophysical impostor, e.g. a blend), FA = false
#: alarm (instrumental). Either way nothing real was re-found: the row is
#: neither a recovery nor a lead.
#:
#: Both this and :data:`MACHINE_DISPOSITIONS` are re-exported from
#: :mod:`lab.a05_vocab`, NOT restated here: the checker grades receipts
#: against the same objects, and a restated contract drifts (VET-F1 — the
#: checker sat five verdicts behind the engine from 2026-08-20).
from .a05_vocab import (  # noqa: E402  (contract import, kept beside its docs)
    MACHINE_DISPOSITIONS,
    TOI_REFUTED_DISPOSITIONS,
)

#: Prior false-alarm-floor measurements, appended to every receipt so the
#: triage extrapolation stays testable (schema `floor_history`). Sources are
#: the COMMITTED receipt basenames under ``reports/hunts/`` (so every point is
#: one click from its evidence): the A04 graded run, the 2026-08-14 discovery
#: pilot's first checkpoint (n=153), and the same day's wide slice (n=551 —
#: the first real test datum for the two-point triage line, which overpredicts
#: it by ~0.47; see :func:`lab.a05_stats.triage_level`). The runner folds in
#: any later hunt summaries it finds on disk before writing the receipt.
PRIOR_FLOOR_HISTORY = (
    {"n": 22, "floor_max": 6.6, "source": "run-2026-08-08-2338-a04"},
    {"n": 153, "floor_max": 7.65, "source": "hunt-2026-08-14-s2-pilot-158"},
    {"n": 551, "floor_max": 7.875, "source": "hunt-2026-08-14-s2-pilot-570"},
)

#: Default declared cap on any single target's share of the soft wall-clock
#: budget. Clock semantics: a row's ``wall_seconds`` is the PER-WORKER wall
#: measured inside :func:`process_target` (plus loader time), while the soft
#: budget is the survey's serial wall — with 12 workers the sum of row clocks
#: legitimately exceeds the survey wall severalfold. A measured stage-2 target
#: costs ~180 s of worker wall (B=256 double-scheme null + injection ladder),
#: so 2 % of the 3000 s soft default (= 60 s) refused every HONEST stage-2
#: row; 10 % (= 300 s) clears the measured cost with margin while still
#: refusing a pathological target that ate a triple share. Mirrored by
#: ``checks.A05_PER_TARGET_SHARE`` — change both or the lockstep test fails.
PER_TARGET_SHARE = 0.10


class A05Error(RuntimeError):
    pass


# ------------------------------------------------------------ deterministic --

def target_seed(run_seed: int, tic: str) -> int:
    """Per-target RNG seed for the permutation null — content-derived.

    Hashing ``(run_seed, tic)`` rather than using call order means a resumed
    run, a re-ordered run, and the auditor's replay all draw the SAME
    permutations for the same target; the receipt stores the value so the null
    is pinned even if this derivation ever changes.
    """
    digest = hashlib.sha256(f"{run_seed}|a05-fap|{tic}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**63)


def is_control_member(tic: str, seed: int = DEFAULT_SEED,
                      fraction: float = CONTROL_FRACTION) -> bool:
    """Predeclared uniformity-control membership by consistent hash.

    Decided from the TIC string alone — before any photon is looked at — so
    membership cannot correlate with what the data show. Same consistent-hash
    idea as :func:`lab.a04.sample_targets`: adding or removing other targets
    never flips anyone's membership.
    """
    digest = hashlib.sha256(f"{seed}|a05-control|{tic}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64) < fraction


def hunt_slice(sector: int, n: int, already: set[str],
               seed: int = DEFAULT_SEED, max_pages: int = 8,
               ) -> tuple[int, list[str]]:
    """(n_enumerated, targets): the next ``n`` in the consistent-hash ranking.

    Reuses :func:`lab.a04.sector_targets` for enumeration and the hunt
    convention for the slice: rank every TIC by ``sha256(seed|tic)``, skip
    everything ``already`` searched, take the next ``n``, then add the
    designated recovery targets unconditionally — they are calibration
    anchors, not hunt territory, and they land in the receipt's
    ``recoveries`` section rather than counting against the slice.
    """
    tics = a04.sector_targets(sector, max_pages=max_pages)
    pool = [t for t in tics if t not in already and t not in a04.RECOVERY_TARGETS]

    def rank(tic: str) -> bytes:
        return hashlib.sha256(f"{seed}|{tic}".encode()).digest()

    chosen = sorted(pool, key=rank)[:n]
    return len(tics), sorted(set(chosen) | set(a04.RECOVERY_TARGETS))


# ------------------------------------------------------------------ loading --

def curve_from_blob(blob: bytes) -> dict:
    """One cached FITS byte string -> the pipeline's per-target inputs.

    Exposed as its own function because the spot-reproduction gate in
    ``checks.check_a05`` must replay EXACTLY this path from the SHA-256-pinned
    bytes: quality mask + ancillary columns via
    :func:`lab.a05_vetting.normalise_with_ancillary`, time-sort applied to the
    flux AND the centroids together, then :func:`lab.a04.detrend`. Returns
    ``{"t", "f", "cx", "cy", "crowdsap", "sha256"}`` with ``f`` detrended.
    """
    curve = a01.read_tess_light_curve(blob, ancillary=True)
    t, f, aux = a05_vetting.normalise_with_ancillary(curve)
    order = np.argsort(t, kind="stable")
    t, f = t[order], f[order]
    cx = aux.get("cx")
    cy = aux.get("cy")
    if cx is not None:
        cx = np.asarray(cx, dtype=float)[order]
    if cy is not None:
        cy = np.asarray(cy, dtype=float)[order]
    td, fd = a04.detrend(t, f)
    if td.shape != t.shape or not np.array_equal(td, t):
        raise A05Error("detrend reordered cadences; centroid alignment lost")
    return {"t": td, "f": fd, "cx": cx, "cy": cy,
            "crowdsap": aux.get("CROWDSAP"),
            # The host's radius, straight from the light curve's own PRIMARY
            # header, so the admissibility gate needs no second catalog.
            "r_star_sun": curve.get("RADIUS"),
            "teff_k": curve.get("TEFF"),
            "sha256": hashlib.sha256(blob).hexdigest()}


def load_curve(tic: str, sector: int, cache_dir=None) -> dict | None:
    """Network loader: SPOC product for ``tic`` in ``sector``, or None.

    The bytes are cached by :func:`lab.a01._download_product`; the receipt row
    pins them by SHA-256 and remembers the cache basename so the spot check
    can find the exact file again.
    """
    cache_dir = cache_dir or a01.CACHE_DIR
    products = a01.discover_spoc_light_curves(tic, max_sectors=4)
    product = next((p for p in products if p.get("sector") == sector), None)
    if product is None:
        return None
    blob, meta = a01._download_product(product, cache_dir)
    out = curve_from_blob(blob)
    out["cache_file"] = str(meta.get("filename") or "")
    return out


# ------------------------------------------------------------ the per-target --

def _fap_block(t: np.ndarray, f: np.ndarray, observed_sde: float, *,
               B: int, seed: int, n_periods: int) -> dict:
    """Both null schemes, graded conservatively, tail reported-never-graded.

    ``fap_graded`` is the LARGER of the two schemes' empirical bounds — the
    contract's conservative-of-two rule. The Gumbel tail is fit on the graded
    scheme's own maxima (extrapolating the cleaner scheme's tail while grading
    the other's bulk would mix two nulls) and is nulled entirely when the fit
    refuses calibration.
    """
    schemes: dict[str, dict] = {}
    for scheme in a05_stats.SCHEMES:
        maxima = a05_stats.batched_null(t, f, B=B, scheme=scheme, seed=seed,
                                        n_periods=n_periods)
        entry = {"raw_maxima": [float(x) for x in maxima],
                 "fap_empirical": a05_stats.fap_empirical(observed_sde, maxima)}
        if scheme == "block":
            entry = {"block_days": a05_stats.BLOCK_DAYS, **entry}
        schemes[scheme] = entry
    graded_scheme = max(a05_stats.SCHEMES,
                        key=lambda s: schemes[s]["fap_empirical"])
    fit = a05_stats.gumbel_fit(
        np.asarray(schemes[graded_scheme]["raw_maxima"], dtype=float))
    gumbel = None
    if fit is not None:
        gumbel = {"mu": fit["mu"], "beta": fit["beta"],
                  "bulk_calibration_pass": True,
                  "fap_tail": a05_stats.gumbel_tail_fap(
                      observed_sde, fit["mu"], fit["beta"])}
    return {"B": int(B), "seed": int(seed), "schemes": schemes,
            "fap_graded": schemes[graded_scheme]["fap_empirical"],
            "graded_scheme": graded_scheme, "gumbel": gumbel}


def process_target(item: dict) -> dict:
    """The pure-compute stage for ONE target — safe to run in a worker process.

    ``item`` carries everything picklable: the curve arrays, the predeclared
    decisions (triage level, control membership, per-target seed) and the
    grid/budget parameters. No network, no disk, single-target numpy — the
    shape the runner's multiprocessing pool expects on Windows spawn.

    Steps: prewhiten -> blind search on the WHITENED flux -> stage-2 decision
    (above triage OR predeclared control member) -> both-scheme FAP -> the
    vetting + blend rungs of the disposition ladder. Catalog rungs and the
    dossier happen at report time in the main process (network + policy live
    there). Rows whose ladder is still unresolved leave ``disposition: None``
    with ``pending_catalog: True``.
    """
    t0 = time.time()
    tic = item["tic"]
    t = np.asarray(item["t"], dtype=float)
    f = np.asarray(item["f"], dtype=float)
    n_periods = int(item["n_periods"])
    prewhiten_kwargs = item.get("prewhiten_kwargs") or {}
    fw, components = a05_vetting.prewhiten(t, f, **prewhiten_kwargs)
    det = a04.blind_search(t, fw, n_periods=n_periods)
    control = bool(item["control_member"])
    # The triage line is a compute-SAVER, never a compute-excuse: at large n
    # the extrapolated line can rise above the detection threshold itself, and
    # a threshold-clearing candidate must NEVER skip its FAP just because the
    # noise ceiling grew — so the stage-2 bar is the LOWER of the two.
    stage2_line = min(float(item["triage_level"]), a04.SDE_THRESHOLD)
    stage2 = bool(det.sde >= stage2_line or control)
    row: dict = {
        "tic": tic, "outcome": "searched",
        "cache_sha256": item.get("cache_sha256"),
        "cache_file": item.get("cache_file"),
        "sde": float(det.sde), "period_days": float(det.period_days),
        "depth": float(det.depth), "phase": float(det.phase),
        "components": [[float(nu), float(amp)] for nu, amp in components],
        "stage2": stage2, "control_subsample": control,
        "fap": None, "disposition": None, "disposition_evidence": {},
        "injections": None, "injections_recovery_rule": None,
        "d_min": None, "insensitive": None,
        "known_planet": None, "published_period_days": None,
    }
    if stage2:
        row["fap"] = _fap_block(t, fw, det.sde, B=int(item["B"]),
                                seed=int(item["seed"]), n_periods=n_periods)
        # Mask the host's own transits first (2026-08-20). Injecting on top of
        # a strong native signal measures nothing: the blind search re-finds
        # the host, every row grades unrecovered, and the target that most
        # needs a depth floor is the one that ends up without one.
        t_inj, f_inj = t, fw
        if det.sde >= a04.SDE_THRESHOLD and det.period_days:
            dur = a05_shape.duration_fraction(t, fw, det.period_days)
            if dur.get("t14_frac"):
                t_inj, f_inj = a05_sensitivity.mask_detection(
                    t, fw, det.period_days, det.phase, dur["t14_frac"])
        inj = a05_sensitivity.injection_grid(t_inj, f_inj, n_periods=n_periods)
        rule = "sde-threshold"
        inj_B = int(item.get("injection_fap_B") or 0)
        if inj_B > 0:
            # Opt-in honesty upgrade: grade each injection's recovery on its
            # own (cheaper, reduced-B, IID-ONLY) permutation FAP instead of
            # the SDE bar. The field is named fap_injection_iid on purpose:
            # it is a single-scheme reduced-B number and must never be
            # mistaken for the row-level GRADED contract (conservative max of
            # two schemes at full B).
            rule = "fap-injection-iid"
            for r in inj:
                fi = a04.inject_box(t, fw, r["period_days"], r["depth"],
                                    t0=float(t[0]) + a05_sensitivity.EPOCH_FRACTIONS[
                                        r["epoch"]] * r["period_days"])
                maxima = a05_stats.batched_null(
                    t, fi, B=inj_B, scheme="iid",
                    seed=int(item["seed"]) + 1 + r["epoch"],
                    n_periods=n_periods)
                r["fap_injection_iid"] = a05_stats.fap_empirical(r["sde"], maxima)
                r["recovered"] = bool(
                    r["period_error_frac"] <= a04.PERIOD_TOL_FRAC
                    and r["fap_injection_iid"] <= a05_sensitivity.FAP_ALPHA)
        row["injections"] = inj
        row["injections_recovery_rule"] = rule
        sens = a05_sensitivity.host_sensitivity(inj)
        row["d_min"] = sens["d_min"]
        row["insensitive"] = sens["insensitive"]
    if det.sde >= a04.SDE_THRESHOLD:
        vet = a05_vetting.extended_vet(t, fw, det, components=components)
        row["disposition_evidence"]["vet"] = vet
        verdict = vet.get("verdict")
        if verdict != "planet-candidate":
            row["disposition"] = verdict
        else:
            # Fold gates before blend gates: they are pure numpy on arrays
            # already in hand (no ancillary columns, no network), and they ask
            # the question the fold-based vet could not — is the DETECTED
            # period half the true one? See lab.a05_fold.
            fold_ev = a05_fold.fold_gate(t, fw, det)
            row["disposition_evidence"]["fold"] = fold_ev
            if fold_ev.get("verdict") is not None:
                row["disposition"] = fold_ev["verdict"]
                row["wall_seconds"] = (time.time() - t0
                                       + float(item.get("load_seconds") or 0.0))
                return row
            # How big was the occulter? The cheapest question in the ladder
            # and, until 2026-08-19, the one nobody asked: TIC 287328866 stayed
            # a `planet-candidate` while implying 2.5 R_Jup on an F subgiant.
            phys = a05_physical.companion_radius(
                det.depth, item.get("r_star_sun"), item.get("crowdsap"))
            row["disposition_evidence"]["physical"] = phys
            centroid = a05_vetting.centroid_shift(
                t, item.get("cx"), item.get("cy"), det)
            contam = a05_vetting.contamination(det.depth, item.get("crowdsap"))
            row["disposition_evidence"]["blend"] = {
                "centroid": centroid, "contamination": contam}
            if phys.get("verdict") == "companion-too-large":
                row["disposition"] = "companion-too-large"
            elif centroid.get("verdict") == "centroid-shift":
                row["disposition"] = "centroid-shift"
            else:
                row["pending_catalog"] = True
    row["wall_seconds"] = (time.time() - t0
                           + float(item.get("load_seconds") or 0.0))
    return row


# --------------------------------------------------- report-time resolution --

def resolve_catalog(row: dict, catalog_row: dict,
                    designated: dict | None = None) -> None:
    """The catalog rungs of the ladder — run at report time, never during the
    search, mutating ``row`` in place.

    * a designated recovery target, a known planet, or a known TOI whose
      TFOPWG disposition is NOT community-refuted -> ``recovery-or-known``;
    * a known TOI with disposition FP/FA -> ``toi-known-fp`` (the TIC
      278866211 / TOI 189.01 lesson: a refuted signal is neither a recovery
      nor a lead — it is a validation target for the blend gates);
    * uncatalogued -> ``lead-awaiting-human-review`` (dossier attached by the
      caller, which still holds the curve).

    A physics verdict normally outranks catalog identity — with ONE carve-out,
    the WASP-18 boundary: a hot Jupiter's occultation is EXPECTED physics, not
    an EB tell (WASP-18 b's real 399 ppm secondary dispositioned its own
    recovery ``eclipsing-binary-secondary`` with no way back). When the
    catalog identifies a CONFIRMED planet — a designated recovery target, a
    ps-table match, or TOI disposition KP/CP — a BARE
    ``eclipsing-binary-secondary`` verdict is outranked and the row becomes
    ``known-planet``, with the physics verdict preserved verbatim as
    ``disposition_evidence.initial_verdict`` (the TIC 140940493 pattern:
    never erase what the flux first said). Catalog identity outranks ONLY
    that verdict, and ONLY for confirmed planets; every other physics rung
    (odd-even, pulsation, centroid…) still stands.
    """
    row["disposition_evidence"]["catalog"] = catalog_row
    row.pop("pending_catalog", None)
    disp = str(catalog_row.get("disposition") or "").strip().upper()
    known_toi = catalog_row.get("known_toi")
    known_planet = catalog_row.get("known_planet") or (
        designated["name"] if designated else None)
    row["known_planet"] = known_planet
    row["published_period_days"] = catalog_row.get("published_period_days") or (
        designated["period_days"] if designated else None)
    if row.get("published_period_days"):
        err = abs(row["period_days"] / float(row["published_period_days"]) - 1.0)
        row["period_error_frac"] = err
        row["recovered"] = bool(err <= a04.PERIOD_TOL_FRAC
                                and row["sde"] >= a04.SDE_THRESHOLD)
    if row.get("disposition") is not None:
        # A physics verdict (pulsation, EB, centroid…) outranks catalog
        # identity: the ladder never renames what the flux already named —
        # except the WASP-18 boundary (see docstring): a confirmed planet's
        # bare secondary verdict is its own occultation, not an EB tell.
        confirmed = bool(designated or catalog_row.get("known_planet")
                         or disp in ("KP", "CP"))
        if confirmed and row["disposition"] == "eclipsing-binary-secondary":
            row["disposition_evidence"]["initial_verdict"] = row["disposition"]
            row["disposition"] = "known-planet"
        return
    if known_toi is not None and disp in TOI_REFUTED_DISPOSITIONS:
        row["disposition"] = "toi-known-fp"
    elif known_planet or known_toi is not None or designated:
        row["disposition"] = "recovery-or-known"
    elif catalog_row.get("known_ctoi"):
        # Somebody already filed this signal on ExoFOP. That is not a planet,
        # not a TOI and not a refutation — it is only "not a fresh lead", which
        # is exactly enough to take the row off the shelf without claiming
        # anything about what the signal IS. Promotion, refutation and
        # confirmation all stay human work.
        row["disposition"] = "ctoi-known"
    elif catalog_row.get("lookup_error"):
        # An outage answered NOTHING: "uncatalogued" cannot be concluded from
        # a failed lookup, so no lead is minted. The row stays
        # pending_catalog, which keeps the run incomplete — ``to_report``
        # refuses it and the runner resumes when the catalog answers.
        row["pending_catalog"] = True
    else:
        row["disposition"] = "lead-awaiting-human-review"


def apply_sky_gates(row: dict, neighbours, catalog_lookup) -> None:
    """The last thing asked before a lead is minted: whose light was that?

    ``resolve_catalog`` has already established that the TARGET's own TIC
    carries no TOI, no CTOI and no confirmed planet. That is exactly the
    condition a blended known planet produces, because a blended planet is by
    construction filed under a different TIC. TIC 77044472 read
    ``known_toi: null, known_planet: null, n_ctoi: 0`` — all true, all
    irrelevant — while its neighbour 0.71 px away was TOI 228.01, HATS-16 b.

    Two gates, cheapest first, both recorded either way:

    * :func:`lab.a05_sky.neighbour_crosscheck` — a catalogue hit on a
      neighbour at the detected period (alias-aware) is a REFUTATION of this
      target, not of the signal.
    * :func:`lab.a05_sky.flux_budget` — with no catalogue hit, ask which star
      in the aperture can produce the dip without needing a stellar companion.
      Refutes only on the asymmetry (target stellar, neighbour planetary).

    Mutates ``row`` in place; a no-op unless the row is about to become a lead.
    """
    if row.get("disposition") != "lead-awaiting-human-review":
        return
    # The outage guard covers the NEIGHBOUR CATALOG CALL as well as the
    # neighbour resolution. `neighbour_crosscheck` skips a neighbour whose
    # lookup returns nothing, so a TOI/CTOI outage that returned None would be
    # indistinguishable from "this neighbour carries no planet" — an unasked
    # question reading as a cleared gate, which is the exact failure mode
    # VET-F4 is about. `a05_sky.sky_catalog_lookup` raises instead, and a raise
    # lands here: the row loses its disposition, goes `pending_catalog`, and
    # `run_a05` refuses to call the slice complete.
    try:
        near = list(neighbours(row["tic"]) or [])
        ev: dict = {"n_neighbours": len(near)}
        cross = a05_sky.neighbour_crosscheck(row.get("period_days"), near,
                                             catalog_lookup)
    except Exception as exc:  # noqa: BLE001 — an outage must not mint a lead
        row["disposition_evidence"]["sky"] = {"lookup_error": type(exc).__name__}
        row["pending_catalog"] = True
        del row["disposition"]
        return
    ev["neighbour_crosscheck"] = cross
    blend = row["disposition_evidence"].get("blend") or {}
    budget = a05_sky.flux_budget(
        row.get("depth"),
        (blend.get("contamination") or {}).get("crowdsap"),
        near, row.get("r_star_sun"))
    ev["flux_budget"] = budget
    row["disposition_evidence"]["sky"] = ev
    if cross.get("verdict"):
        row["disposition"] = cross["verdict"]
    elif budget.get("verdict"):
        row["disposition"] = budget["verdict"]


def _downsample_spectrum(freqs: np.ndarray, amps: np.ndarray,
                         max_points: int = 2000) -> dict:
    """Max-pooled spectrum for the dossier: peaks survive, the receipt stays
    small. Max, not mean — a decimated mean would erase the very peaks the
    panel exists to show."""
    n = len(freqs)
    if n <= max_points:
        return {"cpd": [float(x) for x in freqs],
                "amplitude": [float(x) for x in amps]}
    stride = int(np.ceil(n / max_points))
    cut = (n // stride) * stride
    a = np.asarray(amps[:cut], dtype=float).reshape(-1, stride)
    fgrid = np.asarray(freqs[:cut], dtype=float).reshape(-1, stride)
    j = np.argmax(a, axis=1)
    rows = np.arange(a.shape[0])
    return {"cpd": [float(x) for x in fgrid[rows, j]],
            "amplitude": [float(x) for x in a[rows, j]]}


def build_dossier(row: dict, curve: dict, n_periods: int,
                  prewhiten_kwargs: dict | None = None) -> tuple[dict, str]:
    """Evidence file for one surviving lead, with the lane-2 extras wired in:
    the measured amplitude spectrum (down-sampled, peak-preserving) and the
    centroid-gate output already sitting in the row's blend evidence. The
    spectrum is computed over the SAME band the run prewhitened with, so the
    panel shows exactly what the pulsation gate saw."""
    kw = prewhiten_kwargs or {}
    t = curve["t"]
    fw, _ = a05_vetting.prewhiten(t, curve["f"], **kw)
    det = a04.Detection(row["period_days"], row["depth"], row["phase"], row["sde"])
    freqs, amps = a05_vetting.amplitude_spectrum(
        t, curve["f"], f_lo=kw.get("f_lo", a05_vetting.F_LO_CPD),
        f_hi=kw.get("f_hi", a05_vetting.F_HI_CPD))
    extras = {"amplitude_spectrum": _downsample_spectrum(freqs, amps)}
    blend = row.get("disposition_evidence", {}).get("blend")
    if blend and blend.get("centroid"):
        extras["centroid"] = blend["centroid"]
    panels, html = a05_sensitivity.dossier(t, fw, det, extras=extras,
                                           n_periods=n_periods)
    panels["html_sha256"] = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return panels, html


# ----------------------------------------------------------------- the run --

@dataclass
class A05Result:
    sector: int
    seed: int
    slice_rule: str
    n_enumerated: int
    triage_n: int
    control_fraction: float = CONTROL_FRACTION
    rows: list[dict] = field(default_factory=list)
    recoveries: list[dict] = field(default_factory=list)
    uniformity: dict | None = None
    placebo: dict | None = None
    dossiers: dict = field(default_factory=dict)      # tic -> html
    budget: dict = field(default_factory=dict)
    search_grid: dict = field(default_factory=dict)
    #: Affirmative record of whether the sky gates RAN — see `run_a05`. Never
    #: left empty on a completed run: a receipt has to be able to say "this
    #: gate did not run" out loud (VET-F4 / shelf-exit contract section 2).
    sky_gates: dict = field(default_factory=dict)
    complete: bool = False
    wall_seconds: float = 0.0
    hunt_id: str = ""


def run_a05(sector: int = a04.DEFAULT_SECTOR, n_targets: int = 500,
            seed: int = DEFAULT_SEED, *,
            targets: list[str] | None = None,
            already: set[str] | None = None,
            curve_loader=None, catalog=None,
            B: int = a05_stats.DEFAULT_B,
            n_periods: int = a04.N_PERIODS,
            control_fraction: float = CONTROL_FRACTION,
            n_placebo: int = N_PLACEBO,
            prewhiten_kwargs: dict | None = None,
            injection_fap_B: int = 0,
            soft_budget_seconds: float = 3000.0,
            per_target_share: float = PER_TARGET_SHARE,
            deadline: float | None = None,
            max_new_targets: int | None = None,
            done_rows: list[dict] | None = None,
            on_row=None, pool_map=None,
            neighbours=None, sky_catalog=None,
            progress=None, hunt_id: str = "") -> A05Result:
    """Run the survey pipeline; return an :class:`A05Result` for ``to_report``.

    Injectable seams (all default to the real thing):

    * ``targets`` — explicit slice; otherwise enumerate + consistent-hash.
    * ``curve_loader(tic)`` — returns the :func:`curve_from_blob` dict (plus
      ``cache_file``) or ``None``; defaults to the MAST loader.
    * ``catalog(tic)`` — the report-time cross-check; defaults to
      :func:`lab.a04.catalog_crosscheck`.
    * ``neighbours(tic)`` — catalogued stars sharing the aperture, each
      ``{"tic", "sep_px", "flux_rel", "r_star_sun"}``. Supplied, the sky gates
      (:func:`apply_sky_gates`) run before any lead is minted; omitted, the
      ladder behaves exactly as it did before 2026-08-20 and every lead
      carries the un-asked question. There is no default: resolving neighbours
      needs the network, and a survey must be able to run without it.
    * ``sky_catalog(tic)`` — TOI/CTOI lookup for a NEIGHBOUR's tic, returning
      ``{"period_days", "disposition", "toi"/"name"}`` or None.
    * ``done_rows`` / ``on_row`` — resume state and the per-target checkpoint
      hook (the runner appends JSONL); a row is passed to ``on_row`` exactly
      once, when complete.
    * ``deadline`` (epoch seconds) and ``max_new_targets`` — the two clean
      early-stop paths; ``max_new_targets`` is the deterministic stand-in a
      test uses for a mid-run kill. An early-stopped result has
      ``complete=False`` and MUST NOT be turned into a receipt.
    * ``pool_map`` — a ``map``-alike over :func:`process_target` items (the
      runner passes a multiprocessing pool's map); default serial ``map``.

    The stage-2 decision, control membership, and per-target seeds are all
    fixed before any flux is seen, so a resumed run and a fresh run produce
    identical rows for identical inputs.
    """
    t_start = time.time()
    if injection_fap_B and injection_fap_B < 100:
        raise A05Error(
            f"injection_fap_B={injection_fap_B} cannot resolve the "
            f"FAP_ALPHA={a05_sensitivity.FAP_ALPHA:g} recovery rule: the "
            "empirical bound floors at 1/(B+1), so B < 100 can never grade "
            "an injection recovered — use 0 (sde-threshold rule) or B >= 100")
    catalog = catalog or a04.catalog_crosscheck
    # The detected period disambiguates multi-planet catalog rows (the
    # TOI-125 b-vs-c lesson); injected test doubles may keep the 1-arg shape.
    try:
        catalog_takes_period = "detected_period_days" in inspect.signature(
            catalog).parameters
    except (TypeError, ValueError):
        catalog_takes_period = False
    loader = curve_loader or (lambda tic: load_curve(tic, sector))
    already = already or set()
    if targets is None:
        n_enumerated, targets = hunt_slice(sector, n_targets, already, seed)
    else:
        n_enumerated = len(targets)
        targets = sorted(targets)
    triage_n = max(1, len(targets))
    level = a05_stats.triage_level(triage_n)
    slice_rule = (f"consistent-hash ranking, seed {seed}, "
                  f"{len(already)} prior targets excluded")

    result = A05Result(
        sector=sector, seed=seed, slice_rule=slice_rule,
        n_enumerated=n_enumerated, triage_n=triage_n, hunt_id=hunt_id,
        control_fraction=float(control_fraction),
        search_grid={"p_lo_days": a04.P_LO, "p_hi_days": a04.P_HI,
                     "n_periods": int(n_periods),
                     "detrend_window_days": a04.DETREND_WINDOW_DAYS,
                     # The EFFECTIVE prewhiten parameters, spelled as the
                     # function's own kwargs so the spot-reproduction check
                     # can replay the run verbatim from the receipt alone.
                     "prewhiten": {
                         "f_lo": (prewhiten_kwargs or {}).get(
                             "f_lo", a05_vetting.F_LO_CPD),
                         "f_hi": (prewhiten_kwargs or {}).get(
                             "f_hi", a05_vetting.F_HI_CPD),
                         "max_components": (prewhiten_kwargs or {}).get(
                             "max_components",
                             a05_vetting.PREWHITEN_MAX_COMPONENTS)}},
        budget={"soft_budget_seconds": float(soft_budget_seconds),
                "per_target_share": float(per_target_share)})

    rows_by_tic: dict[str, dict] = {}
    for row in (done_rows or []):
        rows_by_tic[row["tic"]] = row
    mapper = pool_map or map

    pending = [tic for tic in targets if tic not in rows_by_tic]
    new_done = 0
    stopped = False
    chunk_size = 12
    for lo in range(0, len(pending), chunk_size):
        if stopped:
            break
        items = []
        for tic in pending[lo:lo + chunk_size]:
            if deadline is not None and time.time() > deadline:
                stopped = True
                break
            if max_new_targets is not None and new_done + len(items) >= max_new_targets:
                stopped = True
                break
            t_load = time.time()
            try:
                curve = loader(tic)
            except Exception as exc:  # noqa: BLE001 — one target never sinks a survey
                row = {"tic": tic, "outcome": f"error:{type(exc).__name__}",
                       "wall_seconds": time.time() - t_load}
                rows_by_tic[tic] = row
                new_done += 1
                if on_row:
                    on_row(row)
                continue
            if curve is None:
                row = {"tic": tic, "outcome": "skipped-no-product",
                       "wall_seconds": time.time() - t_load}
                rows_by_tic[tic] = row
                new_done += 1
                if on_row:
                    on_row(row)
                continue
            items.append({
                "tic": tic, "t": curve["t"], "f": curve["f"],
                "cx": curve.get("cx"), "cy": curve.get("cy"),
                "crowdsap": curve.get("crowdsap"),
                "r_star_sun": curve.get("r_star_sun"),
                "teff_k": curve.get("teff_k"),
                "cache_sha256": curve.get("sha256"),
                "cache_file": curve.get("cache_file"),
                "triage_level": level,
                "control_member": is_control_member(tic, seed, control_fraction),
                "B": B, "seed": target_seed(seed, tic),
                "n_periods": n_periods,
                "prewhiten_kwargs": prewhiten_kwargs,
                "injection_fap_B": injection_fap_B,
                # Loader wall (download/parse in the main process) rides into
                # the row's wall_seconds so the budget gate sees the target's
                # WHOLE cost, not just its compute — error/skip rows already
                # bill their load time, and success rows must not bill less.
                "load_seconds": time.time() - t_load,
            })
        for row in mapper(process_target, items):
            rows_by_tic[row["tic"]] = row
            new_done += 1
            if on_row:
                on_row(row)
            if progress:
                progress(row)

    result.rows = [rows_by_tic[tic] for tic in targets if tic in rows_by_tic]
    result.complete = len(result.rows) == len(targets) and not stopped
    if not result.complete:
        result.wall_seconds = time.time() - t_start
        return result

    # ---- report-time resolution: catalog rungs, recoveries, dossiers -------
    curves_cache: dict[str, dict] = {}

    def _curve(tic: str) -> dict | None:
        if tic not in curves_cache:
            try:
                curves_cache[tic] = loader(tic)
            except Exception:  # noqa: BLE001
                curves_cache[tic] = None
        return curves_cache[tic]

    # Positive evidence that the sky gates ran — recorded whether they did or
    # not, because "no sky verdict on this receipt" is ambiguous between "the
    # gate ran and cleared every lead" and "the gate was never wired", and for
    # a day in August 2026 it silently meant the second (VET-F4). `status` is
    # the word a human reads; the counters are what a checker re-derives.
    sky_record: dict = {
        "status": "ran" if neighbours is not None else "not-wired",
        "neighbours_wired": neighbours is not None,
        "catalog_wired": sky_catalog is not None,
        "rows_examined": 0, "rows_refuted": 0, "lookup_errors": 0,
        "verdicts": {},
    }

    for row in result.rows:
        if row.get("outcome") != "searched":
            continue
        designated = a04.RECOVERY_TARGETS.get(row["tic"])
        if row.get("pending_catalog") or designated:
            try:
                if catalog_takes_period:
                    cat = catalog(row["tic"],
                                  detected_period_days=row.get("period_days"))
                else:
                    cat = catalog(row["tic"])
            except Exception as exc:  # noqa: BLE001 — outage must not sink the wrap
                cat = {"lookup_error": type(exc).__name__, "known_toi": None,
                       "known_planet": None, "published_period_days": None,
                       "disposition": None}
            resolve_catalog(row, cat, designated)
            if designated or row["disposition"] == "recovery-or-known":
                result.recoveries.append(row)
            elif row["disposition"] == "lead-awaiting-human-review":
                if neighbours is not None:
                    sky_record["rows_examined"] += 1
                    apply_sky_gates(row, neighbours,
                                    sky_catalog or (lambda _t: None))
                    sky_ev = (row.get("disposition_evidence") or {}).get("sky") or {}
                    after = row.get("disposition")
                    if sky_ev.get("lookup_error"):
                        sky_record["lookup_errors"] += 1
                    elif after != "lead-awaiting-human-review":
                        sky_record["rows_refuted"] += 1
                        sky_record["verdicts"][after] = (
                            sky_record["verdicts"].get(after, 0) + 1)
                if row.get("disposition") != "lead-awaiting-human-review":
                    continue
                curve = _curve(row["tic"])
                if curve is not None:
                    panels, html = build_dossier(row, curve, n_periods,
                                                 prewhiten_kwargs)
                    row["dossier"] = panels
                    result.dossiers[row["tic"]] = html

    result.sky_gates = sky_record

    # A catalog outage that left rows unresolved makes the run INCOMPLETE:
    # the slice was searched but the ladder did not finish, and an unfinished
    # ladder must never become a receipt (to_report refuses).
    if any(r.get("pending_catalog") for r in result.rows):
        result.complete = False
        result.wall_seconds = time.time() - t_start
        return result

    # ---- calibration of the calibrator -------------------------------------
    controls = [r for r in result.rows
                if r.get("outcome") == "searched" and r.get("control_subsample")
                and r.get("fap")]
    p_values = [float(r["fap"]["schemes"]["iid"]["fap_empirical"])
                for r in controls]
    if len(p_values) >= 5:
        stat, ok = a05_stats.uniformity_stat(np.asarray(p_values))
        result.uniformity = {"n_control": len(p_values), "p_values": p_values,
                             "ks_stat": float(stat), "pass": bool(ok)}
    else:
        result.uniformity = {"n_control": len(p_values), "p_values": p_values,
                             "ks_stat": None, "pass": None}

    # ---- placebo: full ladder over an epoch-scrambled sky -------------------
    searched_tics = [r["tic"] for r in result.rows if r.get("outcome") == "searched"]
    placebo_tics = sorted(
        searched_tics,
        key=lambda t: hashlib.sha256(f"{seed}|a05-placebo|{t}".encode()).digest()
    )[:min(n_placebo, len(searched_tics))]
    placebo_curves = []
    for tic in placebo_tics:
        curve = _curve(tic)
        if curve is not None:
            fw, comps = a05_vetting.prewhiten(curve["t"], curve["f"],
                                              **(prewhiten_kwargs or {}))
            placebo_curves.append((tic, curve["t"], fw, comps))
    # The placebo exercises the SAME vetting chain as the hunt (extended
    # ladder, with each host's own measured components), not A04's shorter
    # one — a control that runs a laxer chain would grade a different pipeline.
    result.placebo = a05_sensitivity.scramble_placebo(
        placebo_curves, n_periods=n_periods,
        # Same null, same B, same grid as a real target — a control graded on
        # a cheaper null would be measuring a different pipeline.
        fap=lambda ts, fs, sde: _fap_block(ts, fs, sde, B=B, seed=seed,
                                           n_periods=n_periods),
        vet=lambda ts, fs, det, components=(): a05_vetting.extended_vet(
            ts, fs, det, components=components))

    result.wall_seconds = time.time() - t_start
    used = sum(float(r.get("wall_seconds") or 0.0) for r in result.rows)
    result.budget["survey_sum_reported"] = used / max(
        float(soft_budget_seconds), 1e-9)
    return result


# ---------------------------------------------------------------- the receipt

def to_report(result: A05Result,
              prior_floor_history: tuple = PRIOR_FLOOR_HISTORY,
              provenance: dict | None = None) -> dict:
    """Emit the receipt of ``docs/a05-receipt-schema.md`` — counts DERIVED.

    Every number in ``counts`` is recomputed here from the rows, never carried
    from run state, because ``check_a05`` re-derives them again and a receipt
    whose counts cannot be reproduced from its own rows is unreadable by
    contract rule 2. ``floor_history`` appends this run's measured floor to
    the prior points so the triage line stays a testable extrapolation.
    """
    if not result.complete:
        raise A05Error("refusing to write a receipt for an incomplete run — "
                       "resume it to the end of its predeclared slice first")
    rows = result.rows
    searched = [r for r in rows if r.get("outcome") == "searched"]
    skipped = [r for r in rows if r.get("outcome") == "skipped-no-product"]
    errors = [r for r in rows if str(r.get("outcome", "")).startswith("error:")]
    stage2 = [r for r in searched if r.get("stage2")]
    above = [r for r in searched if float(r.get("sde", 0.0)) >= a04.SDE_THRESHOLD]
    dispositioned = [r for r in above if r.get("disposition")]
    leads = [r for r in searched
             if r.get("disposition") == "lead-awaiting-human-review"]
    noise = [float(r["sde"]) for r in searched
             if float(r.get("sde", 0.0)) < a04.SDE_THRESHOLD]
    floor_point = {
        "n": len(noise),
        "floor_max": max(noise) if noise else None,
        "source": result.hunt_id or "this-run",
    }
    if floor_point["source"] in {p.get("source") for p in prior_floor_history}:
        raise A05Error(
            f"hunt_id {floor_point['source']!r} collides with an existing "
            "floor-history source — two floor points under one name would be "
            "indistinguishable; pick a distinct hunt id (suffix it)")
    return {
        "experiment": EXPERIMENT,
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sector": result.sector,
        # The control-membership derivation inputs, as STRUCTURED fields: with
        # (seed, control_fraction) in the receipt, ``check_a05`` re-derives
        # every row's ``control_subsample`` flag from the TIC alone and refuses
        # a receipt whose calibration ensemble was edited after the fact.
        "seed": int(result.seed),
        "control_fraction": float(result.control_fraction),
        "slice_rule": result.slice_rule,
        "n_enumerated": result.n_enumerated,
        "search_grid": result.search_grid,
        "targets": rows,
        "recoveries": result.recoveries,
        # Additive (VET-F4): the receipt states out loud whether the sky gates
        # ran. Absence of a sky verdict is not evidence a sky gate passed.
        "sky_gates": dict(result.sky_gates) if result.sky_gates else {
            "status": "not-wired", "neighbours_wired": False,
            "catalog_wired": False, "rows_examined": 0, "rows_refuted": 0,
            "lookup_errors": 0, "verdicts": {}},
        "uniformity": result.uniformity,
        "placebo": {k: v for k, v in (result.placebo or {}).items()},
        "floor_history": [dict(p) for p in prior_floor_history] + [floor_point],
        "triage": {"n": result.triage_n,
                   "level": a05_stats.triage_level(result.triage_n),
                   "mu": a05_stats.TRIAGE_MU, "beta": a05_stats.TRIAGE_BETA,
                   "safety_margin": a05_stats.TRIAGE_SAFETY_MARGIN},
        "budget": dict(result.budget),
        "counts": {"attempted": len(rows), "searched": len(searched),
                   "skipped": len(skipped), "errors": len(errors),
                   "stage2": len(stage2), "above_threshold": len(above),
                   "dispositioned": len(dispositioned),
                   "leads_awaiting_human_review": len(leads)},
        "wall_seconds": result.wall_seconds,
        "null_caveat": a05_stats.NULL_CAVEAT,
        "provenance": provenance or {},
        "claim_boundary": (
            "Per-target statistics over a predeclared consistent-hash slice of "
            "one sector's 2-minute SPOC targets: each graded number is an "
            "empirical permutation FAP bounded by (1+k)/(B+1), each "
            "above-threshold detection carries a machine disposition from a "
            "closed vocabulary, and each Stage-2 host carries its own measured "
            "injection depth limit. The survey claims completeness of "
            "DISPOSITION over that sample — every hit named, no hit promoted — "
            "not completeness of detection, not an occurrence rate, and no "
            "discovery: the terminal machine state is lead-awaiting-human-"
            "review, nothing is submitted anywhere on the strength of this "
            "receipt, and Gumbel tails plus survey-level sums are reported, "
            "never graded."
        ),
    }
