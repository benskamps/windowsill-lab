"""Find your own planet — the lab's method, packaged for one person
and one star.

This is the A05 survey pipeline (``lab.a05``) cut down to the shape a
newcomer actually has: one TIC, a few TESS sectors, a laptop, and a coding
agent. It runs the SAME ladder the survey runs — prewhitening, blind box
search, a per-target permutation null in two schemes, the injection ladder,
the vetting / fold / size / centroid gates, the catalog rungs — and it adds
the three things a one-star hunt is most tempted to skip:

1. **A preregistration it will not run without.** The parameters live in a
   committed file (``kit/PREREGISTRATION.md`` is the template). The run
   refuses if the data or parameters differ from what was declared, and
   records whether that file was committed to git before the run.
2. **A placebo on the star's own photons.** The light curve is scrambled
   against its own timestamps and pushed through the same ladder. If the
   scrambled sky produces anything the ladder calls a candidate, the run says
   nothing about the real one.
3. **A verdict in plain words, chosen from a closed list.** Every disposition
   comes from :mod:`lab.a05_vocab` (read, never restated) and the kit's own
   star-level status words are listed in :data:`STAR_STATUSES`. Neither list
   contains the word "planet". The best thing this kit can say about a star
   is ``lead-awaiting-human-review``.

The method these steps implement is written down, with its sources and an
honest note on what is and is not new, in ``kit/PROTOCOL.md``.

Numpy + stdlib only. The network (MAST download, catalog lookup) is reached
through injectable callables, so the whole path runs offline in tests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import a04, a05, a05_sensitivity, a05_stats, a05_vetting
from .a05_vocab import (
    GATE_DISPOSITIONS,
    IDENTITY_DISPOSITIONS,
    LEAD_DISPOSITION,
    MACHINE_VOCABULARY,
)

KIT = "find-your-own-planet"
KIT_VERSION = 1

#: The kit's star-level words. Like the machine vocabulary, closed, and with
#: no word for "planet". A star gets exactly one.
STAR_STATUSES = (
    "nothing-above-threshold",   # searched, nothing crossed SDE 8
    "refuted",                   # something crossed, and a gate explained it
    "already-known",             # something crossed, and a catalog has it
    "lead-awaiting-human-review",  # crossed, every gate ran and was silent
    "incomplete",                # a gate did not run; no conclusion
    "control-failed",            # the placebo produced a candidate; no conclusion
)

#: Parameters a preregistration must fix, with the defaults the template ships.
#: The SDE threshold is deliberately NOT here: it is the survey's (8.0), and a
#: threshold chosen per star is the first thing a reader stops trusting.
PREREG_DEFAULTS = {
    "seed": 2026,
    "B": a05_stats.DEFAULT_B,
    "n_periods": a04.N_PERIODS,
    "n_placebo": 10,
}

#: Quick mode, for checking that the plumbing works. Its receipts are marked
#: and its statuses carry a warning: a B=64 null cannot reach the FAP floor
#: the survey grades at.
QUICK = {"B": 64, "n_periods": 600, "n_placebo": 3}

CLAIM_BOUNDARY = (
    "This receipt reports what one automated search did on one star. "
    "It contains no planet claim and cannot: the vocabulary has no such word. "
    "A transit-like signal that survives every gate here is a lead for a "
    "human to review, not a discovery. Confirmation needs independent "
    "observations (high-resolution imaging, radial velocities, or new "
    "photometry) and peer review."
)

#: One plain sentence per machine word, for people who have never read a
#: light curve. Keyed on the vocabulary module's own words; a word missing
#: here falls back to its raw name rather than failing the run.
PLAIN = {
    "stellar-pulsation":
        "the star itself pulses at a rhythm that explains the dips",
    "harmonic-alias":
        "the 'period' is an echo of a different, real rhythm in the data",
    "eclipsing-binary-odd-even":
        "alternate dips have different depths, which is what two stars "
        "eclipsing each other look like",
    "eclipsing-binary-secondary":
        "there is a second, shallower dip halfway round the orbit, the "
        "signature of a glowing companion star",
    "eclipsing-binary-p2-alias":
        "folding at twice the period shows two different eclipses, so the "
        "real period is double and it is two stars",
    "phased-brightening":
        "the star brightens in step with the signal, which a planet's shadow "
        "does not do",
    "low-significance":
        "the signal is not strong enough to tell apart from this star's own "
        "noise",
    "insufficient-coverage":
        "there are too few dips in the data to test anything",
    "period-railed":
        "the best period sits at the edge of what was searched, so it is "
        "not a measurement",
    "centroid-shift":
        "the light that dims comes from beside the target, so it is a "
        "neighbouring star",
    "companion-too-large":
        "whatever blocks the light is too big to be a planet",
    "blended-known-planet":
        "a known planet on a nearby star explains the dips",
    "blend-favours-neighbour":
        "a nearby star explains the dips better than the target does",
    "recovery-or-known":
        "somebody has already catalogued this signal",
    "known-planet":
        "this is a planet that is already known",
    "toi-known-fp":
        "TESS's own team already looked at this signal and ruled it out",
    "ctoi-known":
        "someone else has already filed this signal as a community candidate",
    LEAD_DISPOSITION:
        "a repeating dip that every automatic test failed to explain",
}


class KitError(RuntimeError):
    """A refusal. The message says what to change; the kit never guesses."""


# ------------------------------------------------------------ preregistration

_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def read_prereg(path: Path) -> dict:
    """Parse the one ```json block of a preregistration file.

    Returns ``{"path", "sha256", "declared", "git"}``. ``declared`` must name
    ``tic`` and ``sectors``; every key of :data:`PREREG_DEFAULTS` is filled in
    from the defaults when absent, and the receipt records which ones were.
    """
    raw = Path(path).read_bytes()
    blocks = _JSON_BLOCK.findall(raw.decode("utf-8"))
    if len(blocks) != 1:
        raise KitError(f"{path}: expected exactly one ```json block, found "
                       f"{len(blocks)}")
    try:
        declared = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise KitError(f"{path}: the json block does not parse ({exc})") from exc
    tic = str(declared.get("tic") or "").upper().removeprefix("TIC").strip()
    if not tic.isdigit():
        raise KitError(f"{path}: 'tic' must be a TIC number, got "
                       f"{declared.get('tic')!r}")
    sectors = declared.get("sectors")
    if (not isinstance(sectors, list) or not sectors
            or not all(isinstance(s, int) for s in sectors)):
        raise KitError(f"{path}: 'sectors' must be a non-empty list of "
                       "integers, fixed before you look")
    if "sde_threshold" in declared and float(declared["sde_threshold"]) != \
            a04.SDE_THRESHOLD:
        raise KitError(
            f"{path}: the detection threshold is fixed at SDE "
            f"{a04.SDE_THRESHOLD} for every star; remove 'sde_threshold'")
    defaulted = sorted(k for k in PREREG_DEFAULTS if k not in declared)
    full = {**PREREG_DEFAULTS, **declared, "tic": tic,
            "sectors": sorted(set(sectors))}
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "declared": full, "defaulted": defaulted,
            "git": git_provenance(Path(path))}


def git_provenance(path: Path) -> dict:
    """When was this file first committed, and is the working copy that commit?

    A preregistration nobody can date is a note to self. This records the
    first commit that added the file and whether the bytes on disk still
    match HEAD; it does not refuse an uncommitted file (people try things),
    it says so in the receipt and in the verdict.
    """
    path = Path(path).resolve()
    out = {"committed": False, "first_commit": None, "first_commit_time": None,
           "clean": None}

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(path.parent), *args],
                              capture_output=True, text=True, timeout=20,
                              check=True).stdout.strip()
    try:
        added = git("log", "--diff-filter=A", "--follow", "--format=%H %cI",
                    "--", path.name).splitlines()
        if not added:
            return out
        commit, when = added[-1].split(" ", 1)
        out.update(committed=True, first_commit=commit, first_commit_time=when)
        out["clean"] = git("status", "--porcelain", "--", path.name) == ""
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def prereg_template(tic: str, sectors: list[int], question: str = "") -> str:
    """The text ``planetkit prereg`` writes: the template with the numbers in."""
    block = json.dumps({"tic": tic, "sectors": sectors, **PREREG_DEFAULTS},
                       indent=2)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    q = question or ("Does TIC {tic} show a repeating transit-like signal in "
                     "sectors {s} that survives the full ladder?").format(
        tic=tic, s=", ".join(map(str, sectors)))
    return f"""# Preregistration: TIC {tic}

Written {today}, before any light curve for this star was opened.
Commit this file before you run the kit. The receipt records the commit.

## The question

{q}

## Fixed before looking

```json
{block}
```

The detection threshold is SDE {a04.SDE_THRESHOLD}, the same for every star.

## What each answer will mean

- **nothing-above-threshold**: I will say the search found nothing, and
  quote the depth it could have found on this star (`d_min`).
- **refuted**: I will say what explained the signal, in the kit's words.
- **already-known**: I will say I recovered a known signal.
- **lead-awaiting-human-review**: I will say I found a signal the tests
  could not explain. I will not say I found a planet.
- **incomplete / control-failed**: I will say the run did not finish, and
  why, and post nothing else.

## What I will not do

- Change the sectors, seed, B or period grid after seeing a result.
- Re-run until I get an answer I like. If I re-run, I write a new
  preregistration and keep both receipts.
"""


# ------------------------------------------------------------------ loading

def curve_from_csv(text: str) -> dict:
    """``time,flux`` (TESS BTJD days, any flux unit) -> detrended curve dict.

    No centroids and no stellar radius come with a CSV, so the centroid and
    size gates will say they could not run. That is reported, not hidden.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if rows and not _is_number(rows[0][0]):
        rows = rows[1:]
    data = np.array([[float(r[0]), float(r[1])] for r in rows
                     if len(r) >= 2 and _is_number(r[0]) and _is_number(r[1])])
    if data.size == 0:
        raise KitError("CSV has no numeric time,flux rows")
    t, f = data[:, 0], data[:, 1]
    keep = np.isfinite(t) & np.isfinite(f)
    t, f = t[keep], f[keep] / np.median(f[keep])
    t, f = a04.detrend(t, f)
    return {"t": t, "f": f, "cx": None, "cy": None, "crowdsap": None,
            "r_star_sun": None, "teff_k": None,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


_FITS_NAME = re.compile(r"-s(\d{4})-(\d{16})-")


def identify_fits(name: str) -> tuple[str | None, int | None]:
    """(tic, sector) from a SPOC file name, e.g. ``tess…-s0002-…0100100827-…``."""
    m = _FITS_NAME.search(name)
    if not m:
        return None, None
    return str(int(m.group(2))), int(m.group(1))


# ------------------------------------------------------------------ the run

def search_sector(curve: dict, tic: str, *, B: int, seed: int,
                  n_periods: int, n_placebo: int) -> dict:
    """One sector, the full per-target ladder plus its own placebo."""
    row = a05.process_target({
        "tic": tic, "t": curve["t"], "f": curve["f"],
        "cx": curve.get("cx"), "cy": curve.get("cy"),
        "crowdsap": curve.get("crowdsap"),
        "r_star_sun": curve.get("r_star_sun"),
        # One star: everyone pays for the null. The survey's triage line is
        # a compute-saver for 500-star slices and means nothing here.
        "triage_level": 0.0, "control_member": False,
        "B": int(B), "seed": a05.target_seed(seed, tic),
        "n_periods": int(n_periods), "cache_sha256": curve.get("sha256")})
    # The FAP block carries 2 x B raw maxima; keep the receipt readable.
    fap = row.get("fap")
    if fap:
        for scheme in fap["schemes"].values():
            maxima = np.asarray(scheme.pop("raw_maxima"), dtype=float)
            scheme["null_max"] = float(maxima.max())
            scheme["null_median"] = float(np.median(maxima))
    fw, components = a05_vetting.prewhiten(curve["t"], curve["f"])
    placebo = a05_sensitivity.scramble_placebo(
        [(tic, curve["t"], fw, components)] * int(n_placebo),
        seed=seed, n_periods=n_periods,
        vet=lambda ts, fs, det, components=(): a05_vetting.extended_vet(
            ts, fs, det, components=components))
    return {"row": row, "placebo": placebo}


def fold_svg(t, f, period: float, phase: float, *, title: str,
             note: str) -> str:
    """The folded light curve as a standalone SVG: every dip lined up on top
    of each other at the period the search picked. Numpy and string
    formatting only, so the kit still needs nothing beyond numpy.

    ``phase`` is the search's own box centre (fraction of ``t mod P``), so
    the dip sits at 0. Grey dots are cadences (thinned to 4,000), the dark
    line is the median in 120 phase bins.
    """
    t, f = np.asarray(t, float), np.asarray(f, float)
    x = np.mod(t / period - phase + 0.5, 1.0) - 0.5
    hours = x * period * 24.0
    W, H, L, R, T, B = 720, 360, 64, 16, 40, 48
    lo, hi = np.percentile(f, [0.5, 99.5])
    pad = 0.08 * (hi - lo or 1e-3)
    lo, hi = lo - pad, hi + pad
    xmax = 0.5 * period * 24.0

    def px(h):
        return L + (h + xmax) / (2 * xmax) * (W - L - R)

    def py(v):
        return T + (hi - v) / (hi - lo) * (H - T - B)

    keep = np.random.default_rng(0).permutation(len(t))[:4000]
    dots = "".join(f'<circle cx="{px(hours[i]):.1f}" cy="{py(f[i]):.1f}" r="1"/>'
                   for i in keep if lo <= f[i] <= hi)
    edges = np.linspace(-0.5, 0.5, 121)
    idx = np.clip(np.digitize(x, edges) - 1, 0, 119)
    centres = 0.5 * (edges[:-1] + edges[1:]) * period * 24.0
    pts = [f"{px(c):.1f},{py(float(np.median(f[idx == k]))):.1f}"
           for k, c in enumerate(centres) if np.any(idx == k)]
    ticks = "".join(
        f'<line x1="{px(h):.1f}" y1="{H - B}" x2="{px(h):.1f}" y2="{H - B + 5}"/>'
        f'<text x="{px(h):.1f}" y="{H - B + 18}" text-anchor="middle">{h:g}</text>'
        for h in np.linspace(-xmax, xmax, 5).round(1))
    yt = "".join(
        f'<text x="{L - 6}" y="{py(v) + 4:.1f}" text-anchor="end">{v:.4f}</text>'
        for v in np.linspace(lo, hi, 4))
    esc = lambda s: (s.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
                     .replace(">", "&gt;"))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="system-ui, sans-serif" '
        f'font-size="12">'
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>'
        f'<text x="{L}" y="18" font-size="14" fill="#1a1a1a">{esc(title)}</text>'
        f'<text x="{L}" y="33" fill="#5a5a5a">{esc(note)}</text>'
        f'<g fill="#9aa4ad" fill-opacity="0.45">{dots}</g>'
        f'<polyline fill="none" stroke="#1f4e79" stroke-width="2" '
        f'points="{" ".join(pts)}"/>'
        f'<g stroke="#5a5a5a" fill="#5a5a5a">{ticks}</g>'
        f'<g fill="#5a5a5a">{yt}</g>'
        f'<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="#5a5a5a"/>'
        f'<text x="{(L + W - R) / 2}" y="{H - 8}" text-anchor="middle" '
        f'fill="#5a5a5a">hours from the middle of the dip</text>'
        f'<text transform="translate(14 {(T + H - B) / 2}) rotate(-90)" '
        f'text-anchor="middle" fill="#5a5a5a">relative brightness</text>'
        "</svg>\n")


def resolve(obs: dict, tic: str, catalog) -> None:
    """The catalog rungs, or an honest 'did not run'."""
    row = obs["row"]
    if not row.get("pending_catalog"):
        return
    if catalog is None:
        row["disposition_evidence"]["catalog"] = {"not_run": "offline"}
        return
    a05.resolve_catalog(row, catalog(tic, row["period_days"]),
                        designated=a04.RECOVERY_TARGETS.get(tic))


def star_status(observations: list[dict]) -> dict:
    """One star, all its sectors, one word from :data:`STAR_STATUSES`.

    Precedence: a failed control voids everything; an unresolved row means
    no conclusion; any refutation on any sector refutes the star (the shelf
    contract's 'every gate silent, on every sector'); a catalog identity
    beats a lead; a lead needs every crossing to be a lead.
    """
    failed = [o["sector"] for o in observations if not o["placebo"]["pass"]]
    if failed:
        return {"status": "control-failed", "sectors": failed}
    crossed = [o for o in observations
               if o["row"]["sde"] >= a04.SDE_THRESHOLD]
    if not crossed:
        return {"status": "nothing-above-threshold"}
    pending = [o["sector"] for o in crossed
               if o["row"].get("disposition") is None]
    if pending:
        return {"status": "incomplete", "sectors": pending,
                "reason": "catalog gate did not run (offline or outage)"}
    words = {o["sector"]: o["row"]["disposition"] for o in crossed}
    for w in words.values():
        if w not in MACHINE_VOCABULARY:
            raise KitError(f"disposition {w!r} is outside the vocabulary")
    gates = {s: w for s, w in words.items() if w in GATE_DISPOSITIONS}
    if gates:
        return {"status": "refuted", "by": gates}
    known = {s: w for s, w in words.items() if w in IDENTITY_DISPOSITIONS}
    if known:
        return {"status": "already-known", "by": known}
    periods = [o["row"]["period_days"] for o in crossed]
    agree = (len(periods) >= 2 and
             (max(periods) / min(periods) - 1.0) <= a04.PERIOD_TOL_FRAC)
    return {"status": LEAD_DISPOSITION,
            "sectors": sorted(words),
            "persistent": agree,
            # The shelf contract's multi-sector rule: one sector is
            # provisional at best, and the receipt must say which it is.
            "provisional_single_sector": len(crossed) < 2,
            "period_days": periods}


def plain_verdict(status: dict, observations: list[dict], prereg: dict,
                  quick: bool) -> dict:
    """What the person may say in public, and what they may not."""
    s = status["status"]
    may_not = ["I found a planet", "I discovered a planet",
               "NASA confirmed it", "a new world"]
    if s == "nothing-above-threshold":
        floors = {o["sector"]: a05_sensitivity.null_statement(o["row"])
                  for o in observations}
        insensitive = all(o["row"].get("insensitive") for o in observations)
        if insensitive:
            say = ("I searched this star and found nothing, but the star is "
                   "too noisy for that to mean anything.")
        else:
            say = ("I searched this star and found no repeating dip above the "
                   "threshold. What the search could have seen: " +
                   "; ".join(f"sector {k}: {v}" for k, v in floors.items())
                   + ".")
    elif s == "refuted":
        why = "; ".join(f"sector {k}: {PLAIN.get(v, v)}"
                        for k, v in status["by"].items())
        say = f"My search found a signal and then explained it ({why})."
    elif s == "already-known":
        why = "; ".join(f"sector {k}: {PLAIN.get(v, v)}"
                        for k, v in status["by"].items())
        say = f"My search independently re-found a known signal ({why})."
    elif s == LEAD_DISPOSITION:
        say = ("My search found a repeating dip that every automatic test "
               "failed to explain. It is a lead for a human to review, not a "
               "planet.")
        if status["provisional_single_sector"]:
            say += (" It is in one sector only, so it is provisional: the "
                    "next step is the same search on another sector.")
        elif not status["persistent"]:
            say += " The sectors disagree on the period, which needs a look."
    elif s == "incomplete":
        say = f"The run did not finish: {status['reason']}. No conclusion."
    else:
        say = ("My own placebo produced a candidate from scrambled data, so "
               "this run says nothing about the star.")
    warnings = []
    if not prereg["git"]["committed"]:
        warnings.append("The preregistration was never committed, so nobody "
                        "can tell it was written before the data were seen.")
    elif prereg["git"]["clean"] is False:
        warnings.append("The preregistration was edited after it was "
                        "committed; the receipt hashes the edited version.")
    if quick:
        warnings.append("Quick mode: the null is too small to grade. Do not "
                        "post this result.")
    return {"status": s, "may_say": say, "may_not_say": may_not,
            "warnings": warnings}


def run(prereg_path: Path, *, fits: list[Path] = (), csvs: list[Path] = (),
        download: bool = False, catalog="default", quick: bool = False,
        figures: dict | None = None,
        loader=None) -> dict:
    """Preregistration + light curves -> one receipt (a plain dict).

    ``catalog`` is ``"default"`` (the Exoplanet Archive + ExoFOP lookup the
    survey uses), ``None`` (offline: leads cannot be minted), or a callable
    ``(tic, period_days) -> catalog_row`` for tests. ``loader`` replaces the
    MAST download the same way.
    """
    t0 = time.time()
    prereg = read_prereg(Path(prereg_path))
    d = prereg["declared"]
    tic = d["tic"]
    params = {k: d[k] for k in PREREG_DEFAULTS}
    if quick:
        params.update(QUICK)
    if catalog == "default":
        catalog = lambda tic_, p: a04.catalog_crosscheck(  # noqa: E731
            tic_, detected_period_days=p)

    curves: list[tuple[int, str, dict]] = []
    for path in fits:
        ftic, sector = identify_fits(Path(path).name)
        if ftic != tic:
            raise KitError(f"{path} is TIC {ftic}, but the preregistration "
                           f"declares TIC {tic}")
        curves.append((sector, str(path),
                       a05.curve_from_blob(Path(path).read_bytes())))
    for i, path in enumerate(csvs):
        if len(csvs) != len(d["sectors"]):
            raise KitError("give one CSV per declared sector, in the order "
                           f"the preregistration lists them ({d['sectors']})")
        curves.append((d["sectors"][i], str(path),
                       curve_from_csv(Path(path).read_text())))
    if download:
        load = loader or (lambda tic_, s: a05.load_curve(tic_, s))
        for sector in d["sectors"]:
            curve = load(tic, sector)
            if curve is None:
                raise KitError(f"no SPOC 2-minute light curve for TIC {tic} "
                               f"in sector {sector}")
            curves.append((sector, f"mast:TIC{tic}:s{sector}", curve))
    if not curves:
        raise KitError("no light curves: pass --fits, --csv, or --download")
    got = sorted(s for s, _, _ in curves)
    if got != d["sectors"]:
        raise KitError(f"the preregistration declares sectors {d['sectors']} "
                       f"but the data are sectors {got}. Search what you "
                       "declared, or write a new preregistration.")

    observations = []
    for sector, source, curve in sorted(curves, key=lambda c: c[0]):
        obs = search_sector(curve, tic, B=params["B"], seed=params["seed"],
                            n_periods=params["n_periods"],
                            n_placebo=params["n_placebo"])
        resolve(obs, tic, catalog)
        observations.append({"sector": sector, "source": source,
                             "sha256": curve.get("sha256"), **obs})
        if figures is not None:
            r = obs["row"]
            word = r.get("disposition") or "below threshold"
            figures[sector] = fold_svg(
                curve["t"], curve["f"], r["period_days"], r["phase"],
                title=f"TIC {tic}, sector {sector}: folded at "
                      f"P = {r['period_days']:.4f} d",
                note=f"SDE {r['sde']:.1f} (threshold {a04.SDE_THRESHOLD:g})"
                     f", word: {word}. A picture, not a verdict.")

    status = star_status(observations)
    receipt = {
        "kit": KIT, "kit_version": KIT_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tic": tic,
        "prereg": prereg,
        "parameters": {**params, "sde_threshold": a04.SDE_THRESHOLD,
                       "fap_alpha": a05_sensitivity.FAP_ALPHA,
                       # The survey also gives each scramble a FAP; one star
                       # cannot afford n_placebo more full nulls, and the
                       # pass rule (zero candidates) does not need them.
                       "placebo_fap": False},
        "quick": bool(quick),
        "catalog_checked": catalog is not None,
        "observations": observations,
        "star": status,
        "verdict": plain_verdict(status, observations, prereg, quick),
        "claim_boundary": CLAIM_BOUNDARY,
        # Pinned literal, as in the survey ledger: no code path raises it.
        "planets_claimed": 0,
        "wall_seconds": round(time.time() - t0, 1),
    }
    check_receipt(receipt)
    return receipt


#: Phrases that turn a report into a claim. The plain glosses may say what a
#: thing is NOT ("too big to be a planet"); they may never say one was found.
_CLAIM = re.compile(r"\b(found|discovered|confirmed|new)\s+(a\s+)?(new\s+)?"
                    r"(planet|world|exoplanet)", re.I)


def check_receipt(receipt: dict) -> None:
    """Refuse a receipt that says more than the kit can. Raises KitError."""
    if receipt.get("planets_claimed") != 0:
        raise KitError("planets_claimed must be the literal 0")
    if receipt["star"]["status"] not in STAR_STATUSES:
        raise KitError(f"unknown star status {receipt['star']['status']!r}")
    for obs in receipt["observations"]:
        w = obs["row"].get("disposition")
        if w is not None and w not in MACHINE_VOCABULARY:
            raise KitError(f"sector {obs['sector']}: {w!r} is not a "
                           "vocabulary word")
    if _CLAIM.search(receipt["verdict"]["may_say"]):
        raise KitError("the plain verdict makes a planet claim")


# ------------------------------------------------------------------- doctor

#: The three services a full run talks to, and what breaks without each.
SERVICES = (
    ("MAST (light curves)", "https://mast.stsci.edu/api/v0/invoke",
     "--download will not work; fetch SPOC _lc.fits files by hand and "
     "use --fits"),
    ("NASA Exoplanet Archive (TOIs, known planets)",
     "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+1+from+toi&format=json",
     "the catalog gate cannot run, so no lead can be minted (--offline)"),
    ("ExoFOP (community candidates)",
     "https://exofop.ipac.caltech.edu/tess/",
     "the CTOI part of the catalog gate cannot run"),
)


def _reachable(url: str, timeout: float = 8.0) -> tuple[bool, str]:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "planetkit"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001 — reported, never raised
        code = getattr(exc, "code", None)
        if code is not None and 400 <= int(code) < 500 and int(code) != 403:
            return True, f"HTTP {code} (reachable)"
        return False, f"{type(exc).__name__}: {exc}"[:120]


def doctor(where: Path = Path("."), reach=_reachable) -> list[dict]:
    """Can this machine run the whole journey? One row per requirement."""
    rows = [{"check": "Python >= 3.11", "ok": sys.version_info >= (3, 11),
             "detail": sys.version.split()[0],
             "fix": "install Python 3.11 or newer"},
            {"check": "numpy", "ok": True, "detail": np.__version__,
             "fix": ""}]
    try:
        inside = subprocess.run(
            ["git", "-C", str(where), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        git_ok, git_detail = inside == "true", (
            "inside a git repository" if inside == "true"
            else "not a git repository")
    except (OSError, subprocess.SubprocessError) as exc:
        git_ok, git_detail = False, f"git not available ({exc})"
    rows.append({"check": "git, for dating your preregistration",
                 "ok": git_ok, "detail": git_detail,
                 "fix": "run `git init` here (a public repo is better: the "
                        "commit time is your proof of order)"})
    for name, url, without in SERVICES:
        ok, detail = reach(url)
        rows.append({"check": name, "ok": ok, "detail": detail,
                     "fix": f"without it, {without}"})
    return rows


# ---------------------------------------------------------------------- CLI

def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def explain(receipt: dict) -> str:
    v = receipt["verdict"]
    lines = [f"TIC {receipt['tic']}: {v['status']}", "", v["may_say"], ""]
    for obs in receipt["observations"]:
        r = obs["row"]
        lines.append(f"  sector {obs['sector']}: SDE {r['sde']:.1f}, "
                     f"P = {r['period_days']:.4f} d, "
                     f"word = {r.get('disposition') or '(below threshold)'}, "
                     f"placebo {'passed' if obs['placebo']['pass'] else 'FAILED'}")
    for w in v["warnings"]:
        lines.append(f"  ! {w}")
    lines += ["", "Do not say: " + "; ".join(v["may_not_say"])]
    return "\n".join(lines)


#: What a ledger tells you to do next, per star status. The ledger is the
#: reason to come back: every star you search joins your own denominator,
#: and some of them hand you a next step.
NEXT_STEP = {
    "nothing-above-threshold": "done; it counts in your denominator",
    "refuted": "done; the receipt says what it was",
    "already-known": "done; your search re-found a catalogued signal",
    "incomplete": "rerun online so the catalog gate can run",
    "control-failed": "report the failed control; do not tune until it passes",
}


def ledger(receipts: list[dict]) -> dict:
    """Your own survey: every star you searched, regraded across receipts.

    A star searched under two preregistrations (say sector 20, then sector
    47 to check a lead) is graded on all its sectors together, the latest
    receipt winning per sector. Quick runs and receipts that fail
    :func:`check_receipt` are counted and left out, never graded.
    """
    quick, refused, stars = 0, 0, {}
    for r in sorted(receipts, key=lambda r: r.get("created_utc", "")):
        try:
            check_receipt(r)
        except (KitError, KeyError, TypeError):
            refused += 1
            continue
        if r.get("quick"):
            quick += 1
            continue
        star = stars.setdefault(str(r["tic"]), {"by_sector": {}, "receipts": 0})
        star["receipts"] += 1
        for obs in r["observations"]:
            star["by_sector"][obs["sector"]] = obs
    rows = []
    for tic, star in sorted(stars.items()):
        status = star_status(list(star["by_sector"].values()))
        word = status["status"]
        if word == LEAD_DISPOSITION:
            nxt = ("ready for a human reviewer: see BEFORE-YOU-POST.md"
                   if status["persistent"] else
                   "preregister and search another sector"
                   if status["provisional_single_sector"] else
                   "periods disagree across sectors; a human should look")
        else:
            nxt = NEXT_STEP[word]
        rows.append({"tic": tic, "status": word,
                     "sectors": sorted(star["by_sector"]),
                     "receipts": star["receipts"], "next": nxt})
    counts = {w: sum(r["status"] == w for r in rows) for w in STAR_STATUSES}
    return {"stars": rows, "counts": counts,
            "sector_searches": sum(len(r["sectors"]) for r in rows),
            "calibrated": counts["already-known"] > 0,
            "quick_ignored": quick, "refused_ignored": refused,
            "planets_claimed": 0}


def ledger_text(book: dict) -> str:
    n = len(book["stars"])
    skipped = (f"(left out: {book['quick_ignored']} quick runs, "
               f"{book['refused_ignored']} refused receipts)")
    if not n:
        return "\n".join(["No graded receipts here yet. Run a star first "
                          "(kit/JOURNEY.md, steps 2 to 5)."]
                         + [skipped] * bool(book["quick_ignored"]
                                            or book["refused_ignored"]))
    lines = [f"{n} star{'s' * (n != 1)}, {book['sector_searches']} sector "
             f"searches, 0 planets claimed.", ""]
    for w, c in book["counts"].items():
        if c:
            lines.append(f"  {c:4d}  {w}")
    lines.append("")
    for r in book["stars"]:
        lines.append(f"TIC {r['tic']} (sectors "
                     f"{', '.join(map(str, r['sectors']))}): {r['status']}. "
                     f"Next: {r['next']}.")
    if not book["calibrated"]:
        lines += ["", "! None of your stars has come back already-known yet. "
                  "Run a known planet (WASP-18, TIC 100100827) so you know "
                  "your setup can find one."]
    if book["quick_ignored"] or book["refused_ignored"]:
        lines.append(skipped)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="planetkit", description=__doc__.split(
        "\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prereg", help="write a preregistration to fill in")
    pr.add_argument("tic")
    pr.add_argument("--sectors", type=int, nargs="+", required=True)
    pr.add_argument("--question", default="")
    pr.add_argument("--out", type=Path)
    rn = sub.add_parser("run", help="run the ladder on a preregistered star")
    rn.add_argument("--prereg", type=Path, required=True)
    rn.add_argument("--fits", type=Path, nargs="*", default=[])
    rn.add_argument("--csv", type=Path, nargs="*", default=[])
    rn.add_argument("--download", action="store_true",
                    help="fetch the declared sectors from MAST")
    rn.add_argument("--offline", action="store_true",
                    help="skip the catalog lookup (no lead can be minted)")
    rn.add_argument("--quick", action="store_true",
                    help="small null, for testing the plumbing only")
    rn.add_argument("--out", type=Path)
    ex = sub.add_parser("explain", help="print a receipt in plain words")
    ex.add_argument("receipt", type=Path)
    sub.add_parser("doctor", help="check this machine can run the journey")
    lg = sub.add_parser("ledger", help="your own survey: every star so far")
    lg.add_argument("receipts", type=Path, nargs="*",
                    help="receipt files (default: receipt-*.json here)")
    a = p.parse_args(argv)
    try:
        if a.cmd == "prereg":
            text = prereg_template(str(a.tic).upper().removeprefix("TIC").strip(),
                                   sorted(set(a.sectors)), a.question)
            if a.out:
                a.out.write_text(text)
                print(f"wrote {a.out}. Fill in the question, then commit it.")
            else:
                print(text)
        elif a.cmd == "run":
            figures: dict = {}
            receipt = run(a.prereg, fits=a.fits, csvs=a.csv,
                          download=a.download,
                          catalog=None if a.offline else "default",
                          quick=a.quick, figures=figures)
            out = a.out or Path(f"receipt-TIC{receipt['tic']}-"
                                f"{receipt['created_utc'][:10]}.json")
            out.write_text(json.dumps(receipt, indent=1,
                                      default=_json_default))
            print(explain(receipt))
            print(f"\nreceipt: {out}")
            for sector, svg in sorted(figures.items()):
                fig = out.with_name(f"{out.stem}-s{sector}-fold.svg")
                fig.write_text(svg)
                print(f"fold plot: {fig}")
            # One page with the system, the star and the candidate, drawn
            # from the receipt and the fold plots just written beside it.
            from .planetkit_dashboard import render as render_dashboard
            images = {s: out.with_name(f"{out.stem}-s{s}-fold.svg").read_text()
                      for s in figures}
            page = out.with_suffix(".html")
            page.write_text(render_dashboard(
                json.loads(out.read_text()), fold_images=images))
            print(f"dashboard: {page}")
        elif a.cmd == "doctor":
            rows = doctor()
            for r in rows:
                mark = "ok " if r["ok"] else "NO "
                print(f"[{mark}] {r['check']}: {r['detail']}")
                if not r["ok"]:
                    print(f"       {r['fix']}")
            return 0 if all(r["ok"] for r in rows) else 1
        elif a.cmd == "ledger":
            paths = a.receipts or sorted(Path(".").glob("receipt-*.json"))
            loaded = []
            for q in paths:
                try:
                    loaded.append(json.loads(q.read_text()))
                except (OSError, ValueError):
                    loaded.append({})      # unreadable: counted as refused
            print(ledger_text(ledger(loaded)))
        else:
            print(explain(json.loads(a.receipt.read_text())))
    except KitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
