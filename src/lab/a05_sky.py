"""Whose light is this?  The gates that ask a question about the sky.

Every other gate in the A05 ladder is a function of ``f(t)`` on one star: does
the depth alternate, is there a secondary, did the centroid move, is the star
pulsating, how big is the occulter. All of them can be satisfied by a signal
that is not on the target at all.

TIC 77044472 walked the entire ladder as a `planet-candidate` and was the last
lead standing on 2026-08-20. It is HATS-16 b — a published hot Jupiter on
TIC 77044471, 15.01 arcsec away (0.71 TESS pixels) and 10.5x brighter, whose
light fills 88 % of the target's aperture. The light curve was never wrong.
The pipeline simply never asked whose light it was.

This module adds the three questions that are about the sky rather than the
series, cheapest first:

1. :func:`flux_budget` — arithmetic on numbers already in the dossier. The
   eclipse's absolute flux drop is fixed; ask what *fractional* depth that
   implies on each star sharing the aperture, and let physics rank them.
2. :func:`neighbour_crosscheck` — the target's own TIC is the one place a
   blended known planet can never be filed. Query the neighbours.
3. :func:`cluster_detections` — one astrophysical event contaminating N
   neighbouring apertures currently manufactures N independent leads. Cluster
   them and the contamination becomes a direction-finder instead.

### The flux-budget argument, in full

SPOC's PDCSAP has already removed the contaminating flux (measured directly in
``docs/investigations/2026-08-20-...``: the SAP/PDCSAP depth ratio tracks
1/CROWDSAP across CROWDSAP 0.12-0.999, pinned to 0.2 % by TIC 287328866 at
0.806). So a PDCSAP depth ``d`` already *is* the depth on the target — under the
assumption the target is the source.

Convert it back to a share of the whole aperture, which is source-independent::

    d_aperture = d_pdcsap * CROWDSAP

That number is a property of the *eclipse*, not of any star. Any star i holding
a share ``s_i`` of aperture flux could produce it by dimming ``d_aperture / s_i``
of its own light. A star holding 12 % of the aperture must dim seven times
harder than one holding 86 % to make the same dip — and past a certain point
"dim that hard" means "is a star", which :mod:`lab.a05_physical` already knows
how to say.

The shares come from the CROWDSAP budget and the catalogue: the target holds
``CROWDSAP``, the rest is divided among catalogued neighbours in proportion to
their flux. Without a PSF model that split is approximate, which is why this
gate REPORTS a ranking and only refutes when the target's own implied companion
is stellar *and* some neighbour's is not. See :data:`SUPERIOR_MARGIN`.
"""
from __future__ import annotations

import math

import numpy as np

from . import a01, a04, a05_physical, exofop

#: Pixel scale. TESS is 21 arcsec per pixel; separations are reported in both.
ARCSEC_PER_PIXEL = 21.0

#: A neighbour beyond this many pixels cannot plausibly share the aperture.
#: SPOC apertures for faint targets are a few pixels across; 4 px is generous
#: and keeps the query cheap.
NEIGHBOUR_MAX_PX = 4.0

#: Below this CROWDSAP the target is a minority shareholder in its own
#: aperture and the sky gates become load-bearing rather than advisory.
#: Deliberately looser than ``a05_vetting.CROWDSAP_MIN`` (0.8): this is the
#: line where we *ask the question*, not the line where we refuse.
CROWDSAP_ASK = 0.8

#: To refute a target in favour of a neighbour, the neighbour's implied
#: companion must be smaller than the target's by at least this factor. The
#: aperture-share split is approximate; a bare ordering is not enough.
SUPERIOR_MARGIN = 1.5

#: Period agreement for two detections to be called the same event, and the
#: harmonics tried in both directions (a blend often lands on an alias).
CLUSTER_PERIOD_TOL_FRAC = 0.01
CLUSTER_HARMONICS = (1, 2, 3, 4)

#: Two detections must fall within this many pixels to be the same event.
CLUSTER_MAX_SEP_PX = 6.0


def aperture_shares(crowdsap: float, neighbours: list[dict]) -> dict:
    """Split aperture flux between the target and its catalogued neighbours.

    ``neighbours`` are dicts with ``flux_rel`` (flux relative to the target,
    from Tmag) and ``sep_px``. The target's share is CROWDSAP by definition;
    the remaining ``1 - CROWDSAP`` is divided in proportion to neighbour flux,
    which assumes the aperture captures each neighbour with the same
    efficiency. That is wrong in detail and right in ordering, which is all
    this gate spends it on.

    Returns ``{"target": share, "neighbours": {tic: share}, "captured_frac"}``
    where ``captured_frac`` is the implied per-neighbour aperture capture — a
    diagnostic, not a measurement. Values above 1 mean the catalogue cannot
    account for the reported crowding and the split is refused (``None``).
    """
    try:
        c = float(crowdsap)
    except (TypeError, ValueError):
        return {"target": None, "neighbours": {}, "captured_frac": None,
                "reason": "no-crowdsap"}
    if not (0.0 < c <= 1.0):
        return {"target": None, "neighbours": {}, "captured_frac": None,
                "reason": "crowdsap-out-of-range"}
    near = [n for n in neighbours
            if n.get("sep_px") is not None
            and 0.0 < float(n["sep_px"]) <= NEIGHBOUR_MAX_PX
            and n.get("flux_rel") is not None and float(n["flux_rel"]) > 0]
    total_rel = sum(float(n["flux_rel"]) for n in near)
    foreign = 1.0 - c
    if foreign <= 0 or total_rel <= 0:
        return {"target": c, "neighbours": {}, "captured_frac": None,
                "reason": None if foreign <= 0 else "no-catalogued-neighbours"}
    # foreign share is divided in proportion to catalogued neighbour flux
    shares = {str(n["tic"]): foreign * float(n["flux_rel"]) / total_rel
              for n in near}
    # implied capture efficiency: what fraction of each neighbour's light the
    # aperture would have to hold for the catalogue to explain this CROWDSAP
    captured = foreign / (c * total_rel)
    return {"target": c, "neighbours": shares,
            "captured_frac": float(captured),
            "reason": None if captured <= 1.0 else "catalogue-underexplains-crowding"}


def flux_budget(depth: float, crowdsap: float, neighbours: list[dict],
                r_star_sun=None) -> dict:
    """What fractional depth does this eclipse imply on each aperture star?

    ``depth`` is the PDCSAP depth (already deblended for the target — see the
    module docstring). ``neighbours`` carry ``tic``, ``sep_px``, ``flux_rel``
    and optionally ``r_star_sun``.

    Returns a ranked list under ``candidates``, each with the implied depth,
    the implied companion radius where a stellar radius is known, and whether
    that companion is admissible as a planet. ``verdict`` is
    ``"blended-known-planet"``-shaped only when a neighbour explains the event
    with a planet-sized body while the target requires a stellar one — that is
    the asymmetry :data:`SUPERIOR_MARGIN` guards.
    """
    out: dict = {"verdict": None, "reason": None, "d_aperture": None,
                 "candidates": [], "crowdsap": None}
    try:
        d = float(depth)
    except (TypeError, ValueError):
        out["reason"] = "no-depth"
        return out
    if not (0.0 < d < 1.0):
        out["reason"] = "depth-out-of-range"
        return out
    shares = aperture_shares(crowdsap, neighbours)
    if shares["target"] is None:
        out["reason"] = shares.get("reason") or "no-crowdsap"
        return out
    c = shares["target"]
    out["crowdsap"] = c
    # The source-independent quantity: the dip as a share of ALL aperture light.
    d_ap = d * c
    out["d_aperture"] = float(d_ap)

    def entry(tic, share, r, sep_px, is_target):
        implied = d_ap / share if share > 0 else float("inf")
        row = {"tic": str(tic), "aperture_share": float(share),
               "implied_depth": float(implied), "is_target": bool(is_target),
               "sep_px": None if sep_px is None else float(sep_px),
               "r_star_sun": None if r is None else float(r),
               "r_companion_jup": None, "admissible": None}
        if implied >= 1.0:
            row["admissible"] = False          # cannot lose more light than it has
            row["reason"] = "implied-depth-exceeds-unity"
            return row
        phys = a05_physical.companion_radius(implied, r)
        row["r_companion_jup"] = phys.get("r_companion_jup")
        if phys.get("r_companion_jup") is not None:
            row["admissible"] = bool(
                phys["r_companion_sun"] <= a05_physical.MAX_PLANET_R_SUN)
        else:
            row["reason"] = phys.get("reason")
        return row

    rows = [entry(None, c, r_star_sun, 0.0, True)]
    by_tic = {str(n["tic"]): n for n in neighbours if n.get("tic") is not None}
    for tic, share in shares["neighbours"].items():
        n = by_tic.get(tic, {})
        rows.append(entry(tic, share, n.get("r_star_sun"), n.get("sep_px"), False))
    # rank by implied depth: the least strained explanation first
    rows.sort(key=lambda r: r["implied_depth"])
    out["candidates"] = rows
    out["captured_frac"] = shares.get("captured_frac")

    target_row = next(r for r in rows if r["is_target"])
    others = [r for r in rows if not r["is_target"]]
    if not others or c >= CROWDSAP_ASK:
        return out
    # Refute only on the asymmetry: target needs a star, a neighbour does not.
    best = min(others, key=lambda r: r["implied_depth"])
    if (target_row["admissible"] is False and best["admissible"] is True
            and best["implied_depth"] * SUPERIOR_MARGIN <= target_row["implied_depth"]):
        out["verdict"] = "blend-favours-neighbour"
        out["favoured_tic"] = best["tic"]
        out["reason"] = (
            f"target needs {target_row['implied_depth']*100:.2f} % depth, "
            f"TIC {best['tic']} needs {best['implied_depth']*100:.2f} %")
    return out


def neighbour_crosscheck(detection_period_days: float, neighbours: list[dict],
                         catalog_lookup) -> dict:
    """Is this event a KNOWN planet filed under a star that is not the target?

    ``catalog_lookup(tic)`` returns ``None`` or a dict with ``period_days`` and
    a disposition — the caller supplies it so this stays offline-testable and
    so the TOI and CTOI tables can both be routed through one gate.

    Alias-aware in both directions, like :mod:`lab.exofop`: a blended event is
    routinely detected at a harmonic of the filed period.
    """
    out = {"verdict": None, "matches": [], "reason": None}
    try:
        p = float(detection_period_days)
    except (TypeError, ValueError):
        out["reason"] = "no-period"
        return out
    if not (p > 0):
        out["reason"] = "period-out-of-range"
        return out
    for n in neighbours:
        tic = str(n.get("tic"))
        sep = n.get("sep_px")
        if sep is None or float(sep) <= 0 or float(sep) > NEIGHBOUR_MAX_PX:
            continue
        rec = catalog_lookup(tic)
        if not rec:
            continue
        try:
            q = float(rec["period_days"])
        except (TypeError, ValueError, KeyError):
            continue
        hit = None
        for h in CLUSTER_HARMONICS:
            for cand in (q * h, q / h):
                if abs(cand - p) / p < CLUSTER_PERIOD_TOL_FRAC:
                    hit = h
                    break
            if hit:
                break
        if hit:
            out["matches"].append({
                "tic": tic, "sep_px": float(sep), "alias_n": hit,
                "catalog_period_days": q,
                "disposition": rec.get("disposition"),
                "name": rec.get("name"), "toi": rec.get("toi")})
    if out["matches"]:
        out["verdict"] = "blended-known-planet"
        out["reason"] = "; ".join(
            f"TIC {m['tic']} at {m['sep_px']:.2f} px is "
            f"{m.get('toi') or m.get('name') or 'catalogued'}"
            f" ({m.get('disposition')}) with P={m['catalog_period_days']:.6f} d"
            f" [n={m['alias_n']}]" for m in out["matches"])
    return out


def cluster_detections(rows: list[dict]) -> list[dict]:
    """Group detections that are one astrophysical event seen through N apertures.

    A bright eclipsing binary bleeds into every aperture around it, so the
    survey currently reports it once per contaminated neighbour and each copy
    walks the ladder alone. Clustering turns that redundancy into evidence:
    the member whose implied depth is least strained is the likely source, and
    the rest are its shadows.

    ``rows`` need ``tic``, ``period_days``, ``ra``, ``dec`` and — where the
    flux budget has run — ``implied_depth``. Returns one dict per cluster with
    ``members``, ``source_tic`` (least-strained member, or ``None`` when no
    member carries an implied depth) and ``n_shadows``.
    """
    live = [r for r in rows
            if r.get("period_days") and r.get("ra") is not None
            and r.get("dec") is not None]
    unassigned = list(range(len(live)))
    clusters = []
    while unassigned:
        seed = unassigned.pop(0)
        members = [seed]
        changed = True
        while changed:
            changed = False
            for i in list(unassigned):
                if any(_same_event(live[i], live[m]) for m in members):
                    members.append(i)
                    unassigned.remove(i)
                    changed = True
        group = [live[i] for i in members]
        scored = [g for g in group if g.get("implied_depth") is not None]
        source = (min(scored, key=lambda g: g["implied_depth"])["tic"]
                  if scored else None)
        clusters.append({
            "members": [str(g["tic"]) for g in group],
            "n_members": len(group),
            "period_days": float(group[0]["period_days"]),
            "source_tic": None if source is None else str(source),
            "n_shadows": len(group) - 1,
        })
    return clusters


def _same_event(a: dict, b: dict) -> bool:
    """Same period (to an alias) and close enough on the sky to share flux."""
    pa, pb = float(a["period_days"]), float(b["period_days"])
    if pa <= 0 or pb <= 0:
        return False
    alias = any(abs(pb * h - pa) / pa < CLUSTER_PERIOD_TOL_FRAC
                or abs(pb / h - pa) / pa < CLUSTER_PERIOD_TOL_FRAC
                for h in CLUSTER_HARMONICS)
    if not alias:
        return False
    return separation_px(a["ra"], a["dec"], b["ra"], b["dec"]) <= CLUSTER_MAX_SEP_PX


def separation_px(ra1, dec1, ra2, dec2) -> float:
    """Angular separation in TESS pixels (small-angle, adequate under 1 degree)."""
    d1, d2 = math.radians(float(dec1)), math.radians(float(dec2))
    dra = math.radians(float(ra2) - float(ra1)) * math.cos(0.5 * (d1 + d2))
    ddec = d2 - d1
    arcsec = math.degrees(math.hypot(dra, ddec)) * 3600.0
    return arcsec / ARCSEC_PER_PIXEL


# ------------------------------------------------------------ the resolvers --
#
# The two gates above are pure functions over data someone else fetched, which
# is what made them testable — and what let them sit UNWIRED in production for
# a day: `scripts/a05_hunt.py` called `run_a05` without a `neighbours`
# resolver, so `apply_sky_gates` was a no-op exactly where leads are minted
# (VET-F4). These are the production seams the hunt driver passes. They need
# the network, which is why they are not defaults inside `run_a05`: a survey
# must still be able to run offline, and it must SAY SO in its receipt rather
# than let an unrun gate read as a passed one.


class SkyLookupError(RuntimeError):
    """A sky lookup could not be completed.

    Raised rather than returning "nothing found", because the two are
    opposite facts: "no catalogued neighbour carries this period" clears the
    gate, "we could not ask" must not. `apply_sky_gates` catches this and
    marks the row ``pending_catalog``, which makes the whole run incomplete —
    an unrun gate is not a passed gate.
    """


#: TIC columns the sky gates need: position for the separation, Tmag for the
#: flux share, rad for the implied-companion physics.
TIC_COLUMNS = "ID,ra,dec,Tmag,rad"


def _tic_row(tic: str, deadline: float | None = None) -> dict:
    rows = a01._mast("Mast.Catalogs.Filtered.Tic", {
        "columns": TIC_COLUMNS,
        "filters": [{"paramName": "ID", "values": [str(tic)]}],
    }, deadline=deadline)
    if not rows:
        raise SkyLookupError(f"TIC {tic} not in the TIC catalog")
    return rows[0]


def resolve_neighbours(tic: str, deadline: float | None = None) -> list[dict]:
    """Catalogued stars sharing the target's aperture, nearest first.

    Returns the row shape :func:`aperture_shares` and
    :func:`neighbour_crosscheck` consume: ``tic``, ``sep_px``, ``flux_rel``
    (flux relative to the TARGET, from the Tmag difference) and
    ``r_star_sun``. An empty list is a real answer — "nothing catalogued
    within :data:`NEIGHBOUR_MAX_PX`" — and clears the gate; a failure to ask
    raises :class:`SkyLookupError` instead.
    """
    target = _tic_row(tic, deadline=deadline)
    try:
        ra, dec = float(target["ra"]), float(target["dec"])
        t_mag = float(target["Tmag"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SkyLookupError(
            f"TIC {tic} carries no usable ra/dec/Tmag") from exc
    radius_deg = NEIGHBOUR_MAX_PX * ARCSEC_PER_PIXEL / 3600.0
    rows = a01._mast("Mast.Catalogs.Filtered.Tic.Position", {
        "columns": TIC_COLUMNS,
        "filters": [],
        "ra": ra, "dec": dec, "radius": radius_deg,
    }, deadline=deadline)
    out: list[dict] = []
    for r in rows:
        rid = str(r.get("ID"))
        if rid == str(tic):
            continue
        try:
            sep = separation_px(ra, dec, r["ra"], r["dec"])
            mag = float(r["Tmag"])
        except (KeyError, TypeError, ValueError):
            # A neighbour with no position or no magnitude cannot be given a
            # flux share; it is dropped from the budget, not guessed at.
            continue
        if not (0.0 < sep <= NEIGHBOUR_MAX_PX):
            continue
        rad = r.get("rad")
        out.append({
            "tic": rid,
            "sep_px": float(sep),
            # Flux relative to the target: >1 means BRIGHTER than the target,
            # which is the HATS-16 b geometry (10.5x, 0.71 px).
            "flux_rel": float(10.0 ** (-0.4 * (mag - t_mag))),
            "r_star_sun": float(rad) if isinstance(rad, (int, float)) else None,
        })
    out.sort(key=lambda n: n["sep_px"])
    return out


def sky_catalog_lookup(tic: str, deadline: float | None = None) -> dict | None:
    """TOI / confirmed-planet / CTOI lookup for a NEIGHBOUR's TIC.

    Returns the record :func:`neighbour_crosscheck` consumes — ``period_days``
    plus whatever names the hit — or ``None`` when the neighbour carries
    nothing. Raises :class:`SkyLookupError` when the question could not be
    asked, so an outage cannot read as a clean neighbour.
    """
    try:
        cat = a04.catalog_crosscheck(str(tic), deadline=deadline)
    except Exception as exc:  # noqa: BLE001 - re-raised as the typed error
        raise SkyLookupError(f"TOI lookup failed for TIC {tic}") from exc
    if cat.get("lookup_error"):
        raise SkyLookupError(
            f"TOI lookup failed for TIC {tic}: {cat['lookup_error']}")
    period = cat.get("published_period_days")
    if isinstance(period, (int, float)) and not isinstance(period, bool):
        return {"period_days": float(period),
                "disposition": cat.get("disposition"),
                "toi": cat.get("known_toi"),
                "name": cat.get("known_planet")}
    try:
        ct = exofop.ctoi_crosscheck(str(tic), deadline=deadline)
    except Exception as exc:  # noqa: BLE001 - re-raised as the typed error
        raise SkyLookupError(f"CTOI lookup failed for TIC {tic}") from exc
    if ct.get("lookup_error"):
        raise SkyLookupError(
            f"CTOI lookup failed for TIC {tic}: {ct['lookup_error']}")
    ct_period = ct.get("ctoi_period_days")
    if isinstance(ct_period, (int, float)) and not isinstance(ct_period, bool):
        return {"period_days": float(ct_period),
                "disposition": "CTOI",
                "toi": ct.get("known_ctoi"),
                "name": None}
    return None
