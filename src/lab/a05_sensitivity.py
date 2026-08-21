"""A05 lane 3 — per-host sensitivity, whole-pipeline placebo, and the dossier.

A04 proved the search can find planted transits and measured a survey-wide
false-alarm floor. Three things it could not say, and this module exists to say
them properly:

1. **What a null result means, per host.** A04's positive control was binary
   and survey-wide: inject three boxes into ONE host and demand all three back,
   else ``control_passed: false``. The discovery pilot hit the defect head-on —
   one host with unlucky photometry missed one injection and the receipt
   declared a *healthy hunt* failed. The repair is to stop asking "did the
   control pass?" and start asking "**how deep can this host see?**" Every
   Stage-2 host gets the full predeclared ladder (depth × period × two
   epochs); a missed 0.2 % injection is not a failure, it *is the measurement*
   — it degrades that host's depth limit ``d_min`` and weakens the null
   statement the survey may make about that host, nothing more. Only a host
   that cannot even see a 1.0 % transit is declared ``insensitive`` and barred
   from aggregate sensitivity statements — a survey must not average in hosts
   whose photometry could never have answered the question.

2. **That the WHOLE pipeline, not just the ranker, refuses a phase-scrambled
   sky.** A04's negative control was the SDE floor of undisturbed targets,
   which tests the statistic but not the vetting chain behind it. The placebo
   here permutes flux against its own cadence times — same values, same gaps,
   same noise distribution, zero phase coherence — and runs the FULL search +
   vetting ladder. Anything that emerges as a "planet-candidate" from a curve
   with no coherent signal is a manufactured discovery, and one is too many.

3. **That a surviving lead is EVIDENCE, never a promotion.** The dossier folds
   the candidate at P, P/2 and 2P (the aliases that caught TIC 140940493 and
   TIC 287328866), splits odd from even epochs, interrogates the secondary
   window, and re-injects the candidate's own (depth, period) to show the
   pipeline can recover what it claims to have found. Its terminal status is
   ``lead-awaiting-human-review`` — the machine's vocabulary has no word for
   "planet", by contract rule 3 of the receipt schema.

Numpy + stdlib only. Search and vetting are borrowed from :mod:`lab.a04`
verbatim so the controls exercise the pipeline that actually hunts.
"""
from __future__ import annotations

import html as _html

import numpy as np

from . import a04

#: Predeclared injection ladder — depths in fractional flux. Predeclared means
#: exactly that: chosen before any hunt ran, never tuned to make a host pass.
DEPTHS = (0.002, 0.004, 0.010)

#: Predeclared ladder periods in days. All sit inside the blind grid, away from
#: its rails, with >= 5 transits in a 27-day sector.
PERIODS = (2.3, 3.7, 5.1)

#: The full grid, row-major: every depth at every period.
LADDER = tuple((d, p) for d in DEPTHS for p in PERIODS)

#: Two distinct off-grid epoch offsets, as fractions of the injected period.
#: Neither is a round fraction of anything the search grids over; recovering a
#: cell must not depend on where in its orbit the transit happens to sit.
EPOCH_FRACTIONS = (0.37, 0.63)

#: Injections per ladder cell — one per epoch fraction. A cell is recovered
#: only if EVERY epoch is, so a lucky alignment cannot buy sensitivity.
N_EPOCHS = 2

#: Half-widths of the host mask are padded by this factor beyond the measured
#: duration, so ingress/egress wings do not leak into the "clean" baseline.
MASK_PAD = 1.5

#: Refuse to mask if it would leave less than this fraction of the cadences:
#: a floor measured on a stub is not a floor.
MASK_MIN_KEPT = 0.5

#: Missing an injection this deep at ANY period flags the host ``insensitive``:
#: photometry that cannot see a 1 % transit cannot support any null statement,
#: so the host is excluded from every aggregate sensitivity claim.
INSENSITIVE_DEPTH = max(DEPTHS)

#: FAP threshold quoted in null statements, and the recovery bar when a run
#: opts into ``injection_fap_B`` (recovery then grades on
#: ``fap_injection_iid <= FAP_ALPHA``; B must be >= 100 or the empirical
#: bound's 1/(B+1) floor sits above this alpha and nothing could ever pass).
FAP_ALPHA = 0.01

#: Base seed for the epoch-scramble placebo. Fixed so the scrambled sky is
#: reproducible: a placebo that cannot be re-run is not a control.
SCRAMBLE_SEED = 20260814

#: Phase bins for dossier folds — coarse enough that a binned median is smooth,
#: fine enough that a VET_WINDOW_PHASE-wide transit spans several bins.
FOLD_BINS = 120

#: The machine-terminal status of every dossier. Contract rule 3: no machine
#: path may emit "planet"; the dossier presents evidence and stops.
DOSSIER_STATUS = "lead-awaiting-human-review"

#: Every dossier must carry all of these panels or a check refuses it.
DOSSIER_REQUIRED_PANELS = (
    "fold_p", "fold_half_p", "fold_2p",
    "odd_even", "secondary", "self_injection",
)


class A05SensitivityError(RuntimeError):
    pass


# ------------------------------------------------------------ injections ---

def mask_detection(t: np.ndarray, f: np.ndarray, period_days: float,
                   phase: float, duration_frac: float,
                   pad: float = MASK_PAD) -> tuple[np.ndarray, np.ndarray]:
    """Drop the host's OWN transits so an injection is searched against clean flux.

    Without this, a host with a strong signal has no measurable sensitivity: a
    blind search of ``inject_box(f)`` re-finds the *native* period rather than
    the injected one, the row grades ``recovered = False`` for the right reason
    and the wrong cause, and the host is flagged ``insensitive`` with
    ``d_min = {2.3: None, 3.7: None, 5.1: None}``.

    That is precisely backwards. The targets whose depth floor matters most —
    the ones carrying a candidate — are the ones the survey currently cannot
    measure. TIC 77044472's injections all "recovered" period 2.6857 d: the
    host's own signal, not the 2.3 d box that was planted.

    Removes rather than flattens: replacing in-transit cadences with a baseline
    constant inserts a stretch of zero-variance data that the periodogram reads
    as real quiet. Returns ``(t_masked, f_masked)``.
    """
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    try:
        P = float(period_days)
        ph0 = float(phase)
        half = 0.5 * float(duration_frac) * float(pad)
    except (TypeError, ValueError):
        return t, f
    if not (P > 0) or not (half > 0):
        return t, f
    # a04.Detection.phase is measured as np.mod(t, period)/period — absolute,
    # not relative to t[0]. Match that convention exactly; deriving a t0 from
    # it by hand is how an off-by-one-fold mask gets written.
    ph = np.mod(t, P) / P
    keep = np.abs(((ph - ph0 + 0.5) % 1.0) - 0.5) > half
    if int(keep.sum()) < MASK_MIN_KEPT * t.size:
        # Masking would take too much of the series to leave a searchable
        # baseline; better to report the host unmeasured than to measure a
        # floor on a stub.
        return t, f
    return t[keep], f[keep]


def injection_grid(t: np.ndarray, f: np.ndarray,
                   ladder: tuple = LADDER, epochs: int = N_EPOCHS,
                   n_periods: int = a04.N_PERIODS,
                   t0_anchor: float | None = None,
                   progress=None) -> list[dict]:
    """Run the predeclared ladder against one host; one row per injection.

    Each (depth, period) cell is injected at ``epochs`` distinct off-grid
    epochs via :func:`lab.a04.inject_box` and searched blind with
    :func:`lab.a04.blind_search`. Runs opting into ``injection_fap_B`` (see
    :func:`lab.a05.process_target`) fill ``fap_injection_iid`` — a
    single-scheme reduced-B permutation FAP, named so it cannot be mistaken
    for the row-level graded contract — and regrade recovery on it.

    A row is ``recovered`` iff the blind period lands within
    ``a04.PERIOD_TOL_FRAC`` of the injected one AND the detection clears
    ``a04.SDE_THRESHOLD`` — the same two-part criterion the hunt itself grades
    recoveries with, because a sensitivity limit measured under a laxer rule
    than the hunt's would be a lie about the hunt.

    Row shape matches the receipt schema's ``injections`` entries verbatim:
    ``{depth, period_days, epoch, sde, fap_injection_iid, recovered}`` plus
    the recovered period and its fractional error for audit.

    ``t0_anchor`` shifts where the epoch fractions are measured from
    (default: the first cadence). The dossier's self-injection anchors to the
    candidate's own transit time so the planted epochs land 0.37 and 0.63 of a
    period AWAY from the masked-out candidate transits — anchored to ``t[0]``
    they can fall exactly into the mask's periodic gaps and be injected onto
    cadences that no longer exist.
    """
    if epochs < 1 or epochs > len(EPOCH_FRACTIONS):
        raise A05SensitivityError(
            f"epochs must be 1..{len(EPOCH_FRACTIONS)} (predeclared fractions)")
    rows: list[dict] = []
    base = float(t[0]) if t0_anchor is None else float(t0_anchor)
    for depth, period in ladder:
        for k in range(epochs):
            t0 = base + EPOCH_FRACTIONS[k] * period
            det = a04.blind_search(
                t, a04.inject_box(t, f, period, depth, t0=t0),
                n_periods=n_periods)
            err = abs(det.period_days / period - 1.0)
            row = {
                "depth": depth,
                "period_days": period,
                "epoch": k,
                "sde": det.sde,
                "fap_injection_iid": None,   # filled when injection_fap_B opts in
                "recovered": bool(err <= a04.PERIOD_TOL_FRAC
                                  and det.sde >= a04.SDE_THRESHOLD),
                "recovered_period_days": det.period_days,
                "period_error_frac": err,
            }
            rows.append(row)
            if progress:
                progress(row)
    return rows


def host_sensitivity(rows: list[dict]) -> dict:
    """Fold injection rows into the host's ``d_min`` and sensitivity flag.

    ``d_min[period]`` is the SHALLOWEST depth whose every epoch was recovered
    at that period — the host's measured detection limit there. A missed
    shallow cell weakens the limit (the pilot's lesson: that is a *measurement*
    about this host, not a pipeline failure); a period where nothing was
    recovered gets ``None``. Missing any cell at ``INSENSITIVE_DEPTH`` flags
    the host ``insensitive`` and disqualifies it from aggregates.
    """
    by_cell: dict[tuple[float, float], list[bool]] = {}
    for r in rows:
        by_cell.setdefault((r["depth"], r["period_days"]), []).append(
            bool(r["recovered"]))
    periods = sorted({p for _, p in by_cell})
    d_min: dict[str, float | None] = {}
    insensitive = False
    missed: list[dict] = []
    for p in periods:
        recovered_depths = []
        for (d, pp), oks in by_cell.items():
            if pp != p:
                continue
            if all(oks):
                recovered_depths.append(d)
            else:
                missed.append({"depth": d, "period_days": pp})
                if d >= INSENSITIVE_DEPTH:
                    insensitive = True
        d_min[f"{p}"] = min(recovered_depths) if recovered_depths else None
    return {"d_min": d_min, "insensitive": insensitive, "missed": missed,
            "n_injections": len(rows)}


def aggregate_sensitivity(host_rows: list[dict]) -> dict:
    """Combine per-host sensitivity, EXCLUDING insensitive hosts.

    The survey-level statement is the WORST (largest) ``d_min`` per period over
    the sensitive hosts — the depth to which every counted host can see. Hosts
    flagged insensitive are named in ``excluded`` and contribute nothing: an
    average that quietly includes blind hosts overstates the survey.
    """
    sensitive = [h for h in host_rows if not h.get("insensitive")]
    excluded = [h.get("tic", "?") for h in host_rows if h.get("insensitive")]
    worst: dict[str, float | None] = {}
    for h in sensitive:
        for p, d in h.get("d_min", {}).items():
            if d is None:
                worst[p] = None
            elif p not in worst:
                worst[p] = d
            elif worst[p] is not None:
                worst[p] = max(worst[p], d)
    return {"n_hosts": len(host_rows), "n_sensitive": len(sensitive),
            "excluded": excluded, "d_min_worst": worst}


def null_statement(host_row: dict, alpha: float = FAP_ALPHA) -> str:
    """The sentence a report may print for a host that surfaced nothing.

    'Nothing found' is only meaningful next to 'and here is how deep we
    looked'. An insensitive host earns a refusal, not a statement.
    """
    if host_row.get("insensitive"):
        return ("host insensitive (missed a "
                f"{INSENSITIVE_DEPTH:.1%} injection); "
                "no null statement may be issued for this host")
    d_min = host_row.get("d_min", {})
    finite = [d for d in d_min.values() if d is not None]
    if not finite:
        return "no measured sensitivity; no null statement may be issued"
    per_period = ", ".join(
        f"P={p} d: " + (f">={d:.2%}" if d is not None else "no recovery")
        for p, d in sorted(d_min.items(), key=lambda kv: float(kv[0])))
    return (f"no candidate at FAP <= {alpha:g}; sensitive to depth "
            f">= {max(finite):.2%} on this host ({per_period})")


# --------------------------------------------------------------- placebo ---

def epoch_scramble(t: np.ndarray, f: np.ndarray,
                   seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Permute flux against its own cadence times.

    The times stay exactly where TESS put them — same gaps, same duty cycle,
    same window function — while the flux values are dealt to them in random
    order. Every marginal property of the photometry survives (distribution,
    outliers, noise level); the ONE thing destroyed is phase coherence, which
    is the only thing a real transit has. It is the whole-pipeline analogue of
    A04's noise floor: not "is the statistic calibrated?" but "does the entire
    ladder refuse a sky with nothing in it?"
    """
    rng = np.random.default_rng(seed)
    return t, f[rng.permutation(len(f))]


def scramble_placebo(curves: list[tuple], seed: int = SCRAMBLE_SEED,
                     n_periods: int = a04.N_PERIODS,
                     progress=None, vet=None) -> dict:
    """Search + vet an epoch-scrambled sky and demand zero planet-candidates.

    ``curves`` is a list of ``(tic, t, f)`` — optionally ``(tic, t, f,
    components)`` with the host's measured pulsation components — with ``f``
    already detrended, exactly what the hunt searches. Each curve is
    scrambled with its own derived seed (reproducible, distinct) and
    blind-searched; any above-threshold hit is vetted by ``vet(ts, fs, det,
    components=...)``, defaulting to A04's :func:`lab.a04.vet_candidate`.
    The default is NOT the extended ladder — no pulsation-spectrum gate, no
    blend gates — so callers wanting the placebo to exercise the same chain
    as the hunt (the honest configuration; :func:`lab.a05.run_a05` does this)
    must pass the extended vet explicitly. The pass criterion is absolute:
    ZERO planet-candidates. An EB verdict or a railed period on scrambled
    data is the vetting chain doing its job; a "planet-candidate" is the
    pipeline hallucinating, and one sinks the control.

    Returns the receipt's ``placebo`` block plus per-curve rows for audit.
    """
    vetter = vet or (
        lambda ts, fs, det, components=(): a04.vet_candidate(ts, fs, det))
    rows: list[dict] = []
    planet_candidates = 0
    for i, entry in enumerate(curves):
        tic, t, f = entry[0], entry[1], entry[2]
        components = entry[3] if len(entry) > 3 else ()
        ts, fs = epoch_scramble(t, f, seed=np.random.SeedSequence(
            [seed, i]).generate_state(1)[0])
        det = a04.blind_search(ts, fs, n_periods=n_periods)
        row = {"tic": tic, "sde": det.sde, "period_days": det.period_days}
        if det.sde >= a04.SDE_THRESHOLD:
            row["vetting"] = vetter(ts, fs, det, components=components)
            if row["vetting"].get("verdict") == "planet-candidate":
                planet_candidates += 1
        rows.append(row)
        if progress:
            progress(row)
    return {"n_scrambled": len(rows),
            "planet_candidates": planet_candidates,
            "pass": planet_candidates == 0,
            "rows": rows}


# --------------------------------------------------------------- dossier ---

def _binned_fold(t: np.ndarray, f: np.ndarray, period: float,
                 bins: int = FOLD_BINS) -> tuple[list[float], list[float]]:
    """Median flux in phase bins — the honest fold (means chase outliers)."""
    phase = np.mod(t, period) / period
    idx = np.minimum((phase * bins).astype(int), bins - 1)
    centers, medians = [], []
    for b in range(bins):
        m = idx == b
        centers.append((b + 0.5) / bins)
        medians.append(float(np.median(f[m])) if m.any() else float("nan"))
    return centers, medians


def _svg_polyline(xs, ys, title: str, width: int = 320,
                  height: int = 120) -> str:
    """One inline-SVG panel: a polyline, axis-free, self-contained.

    No namespaces, no fonts, no fetches — inline SVG inside an HTML document
    needs none of them, and the receipt contract wants a dossier that renders
    identically on an air-gapped machine in ten years.
    """
    pts = [(x, y) for x, y in zip(xs, ys) if np.isfinite(y)]
    if len(pts) < 2:
        body = ""
    else:
        ys_f = [y for _, y in pts]
        lo, hi = min(ys_f), max(ys_f)
        span = (hi - lo) or 1.0
        pad = 8
        coords = " ".join(
            f"{pad + x * (width - 2 * pad):.1f},"
            f"{pad + (1.0 - (y - lo) / span) * (height - 2 * pad):.1f}"
            for x, y in pts)
        body = (f'<polyline points="{coords}" fill="none" '
                f'stroke="#7a5c3e" stroke-width="1.2"/>')
    return (f'<figure><figcaption>{_html.escape(title)}</figcaption>'
            f'<svg viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img">{body}</svg></figure>')


def dossier(t: np.ndarray, f: np.ndarray, det: a04.Detection,
            extras: dict | None = None,
            n_periods: int = a04.N_PERIODS) -> tuple[dict, str]:
    """Assemble the evidence file for one surviving lead.

    Everything a human reviewer needs to kill or keep the lead, and nothing
    that decides for them:

    * **Folds at P, P/2 and 2P.** The three folds that catch the classic
      impostors: an EB folded at P instead of 2P stacks two different eclipses
      into one; a pulsator below the grid floor keeps its full dip at P/n
      where a true transit dilutes (TIC 140940493's tell).
    * **Odd vs even epochs**, separately folded — the discriminator that
      separated TIC 287328866 at 11 sigma.
    * **Secondary window stats** at phase 0.5: a planet's occultation can only
      dim, so brightening there is ellipsoidal variation or pulsation.
    * **Self-injection**: the candidate's own (depth, period) planted at both
      predeclared off-grid epochs — into the curve with the candidate's own
      transits masked, so the injection meets the host's noise rather than
      interfering with the very signal it mimics — and re-searched blind. A
      pipeline that cannot recover its own candidate's parameters has no
      business reporting them.
    * Optional panels arrive via ``extras``:
      TODO(lane-2): ``extras["amplitude_spectrum"]`` — {cpd, amplitude} arrays
      from the vetting module's pulsation gate.
      TODO(lane-2): ``extras["centroid"]`` — centroid-shift series hook.

    Returns ``(panels_dict, html)``. The HTML is one self-contained file:
    inline CSS, inline SVG polylines, zero external references. ``status`` is
    machine-terminal ``lead-awaiting-human-review`` by contract — the dossier
    presents EVIDENCE; promotion is a human act.
    """
    extras = extras or {}
    period, ph0 = det.period_days, det.phase
    panels: dict = {"status": DOSSIER_STATUS,
                    "detection": {"period_days": det.period_days,
                                  "depth": det.depth, "phase": det.phase,
                                  "sde": det.sde}}

    for key, p in (("fold_p", period), ("fold_half_p", period / 2.0),
                   ("fold_2p", period * 2.0)):
        centers, medians = _binned_fold(t, f, p)
        panels[key] = {"period_days": p, "phase": centers, "flux": medians}

    # Odd/even folds share the vetting window so numbers agree with the gate.
    phase = np.mod(t, period) / period
    epoch = np.floor((t - t[0]) / period).astype(int)
    in_transit = np.abs(((phase - ph0 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    out = ~in_transit
    base = float(np.median(f[out])) if out.any() else 1.0
    noise = float(np.std(f[out])) if out.any() else 0.0
    odd_c, odd_m = _binned_fold(t[epoch % 2 == 1], f[epoch % 2 == 1], period)
    even_c, even_m = _binned_fold(t[epoch % 2 == 0], f[epoch % 2 == 0], period)
    odd_f = f[in_transit & (epoch % 2 == 1)]
    even_f = f[in_transit & (epoch % 2 == 0)]
    panels["odd_even"] = {
        "phase": odd_c,
        "odd": odd_m, "even": even_m,
        "depth_odd": base - float(np.median(odd_f)) if len(odd_f) else None,
        "depth_even": base - float(np.median(even_f)) if len(even_f) else None,
    }

    sec = np.abs(((phase - ph0 - 0.5 + 0.5) % 1.0) - 0.5) < a04.VET_WINDOW_PHASE
    d_sec = base - float(np.median(f[sec])) if sec.sum() > 5 else float("nan")
    sec_sigma = (d_sec / (noise / np.sqrt(max(int(sec.sum()), 1)))
                 if sec.sum() > 5 and noise > 0 else 0.0)
    panels["secondary"] = {"depth": d_sec, "sigma": float(sec_sigma),
                           "window_phase": a04.VET_WINDOW_PHASE,
                           "n_in_window": int(sec.sum())}

    # Self-injection: this candidate's own parameters, both predeclared epochs,
    # into the curve with the candidate's OWN transits masked out first. Left
    # in, the real train and the planted one coexist at the same period and
    # interfere — the second dip pulls the out-of-transit level down and
    # doubles the alias structure, depressing the recovered SDE below what the
    # host photometry actually supports. The question this panel answers is
    # "could THIS host have shown us this signal?", so the injection must meet
    # the host's noise, not the candidate's own signal.
    # Anchor the epochs to the candidate's own transit time: the fractions
    # 0.37 / 0.63 then measure phase offsets FROM the masked window, so the
    # planted transits land on real cadences instead of inside the mask's
    # periodic gaps.
    masked = ~in_transit
    panels["self_injection"] = injection_grid(
        t[masked], f[masked], ladder=((det.depth, det.period_days),),
        n_periods=n_periods, t0_anchor=ph0 * period)

    # TODO(lane-2): amplitude-spectrum panel from the pulsation gate.
    if "amplitude_spectrum" in extras:
        panels["amplitude_spectrum"] = extras["amplitude_spectrum"]
    # TODO(lane-2): centroid-shift series.
    if "centroid" in extras:
        panels["centroid"] = extras["centroid"]

    return panels, _dossier_html(panels)


def _dossier_html(panels: dict) -> str:
    """Render the dossier as one self-contained HTML file.

    Minimal look borrowed from the lab reports: mono for machine numbers,
    quiet palette, no scripts, no fonts, no fetches of any kind.
    """
    d = panels["detection"]
    figs = []
    for key in ("fold_p", "fold_half_p", "fold_2p"):
        p = panels[key]
        figs.append(_svg_polyline(
            p["phase"], p["flux"],
            f'{key.replace("_", " ")} — {p["period_days"]:.5f} d'))
    oe = panels["odd_even"]
    figs.append(_svg_polyline(oe["phase"], oe["odd"], "odd epochs fold"))
    figs.append(_svg_polyline(oe["phase"], oe["even"], "even epochs fold"))
    if "amplitude_spectrum" in panels:
        sp = panels["amplitude_spectrum"]
        figs.append(_svg_polyline(
            np.asarray(sp["cpd"], dtype=float) /
            max(float(np.max(sp["cpd"])), 1e-12),
            sp["amplitude"], "amplitude spectrum"))

    inj_rows = "".join(
        f"<tr><td>{r['depth']:.4f}</td><td>{r['period_days']:.5f}</td>"
        f"<td>{r['epoch']}</td><td>{r['sde']:.2f}</td>"
        f"<td>{'yes' if r['recovered'] else 'NO'}</td></tr>"
        for r in panels["self_injection"])
    sec = panels["secondary"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>candidate dossier — {DOSSIER_STATUS}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 60rem; margin: 2rem auto;
          color: #2b2620; background: #faf7f2; padding: 0 1rem; }}
  h1 {{ font-size: 1.3rem; }} figure {{ display: inline-block; margin: .6rem; }}
  figcaption, td, th, .m {{ font-family: ui-monospace, monospace;
          font-size: .75rem; color: #6b6154; }}
  table {{ border-collapse: collapse; }} td, th {{ padding: .15rem .6rem;
          border-bottom: 1px solid #e4ddd2; }}
  .status {{ color: #7a5c3e; letter-spacing: .08em; text-transform: uppercase;
          font-family: ui-monospace, monospace; font-size: .7rem; }}
</style>
<h1>candidate dossier</h1>
<p class="status">status: {DOSSIER_STATUS}</p>
<p class="m">P = {d['period_days']:.5f} d &middot; depth = {d['depth']:.5f}
&middot; phase = {d['phase']:.4f} &middot; SDE = {d['sde']:.2f}</p>
{''.join(figs)}
<h2 class="m">secondary window</h2>
<p class="m">depth = {sec['depth']:.6f} &middot; sigma = {sec['sigma']:.2f}
&middot; n = {sec['n_in_window']}</p>
<h2 class="m">self-injection (candidate's own depth &times; period)</h2>
<table><tr><th>depth</th><th>P (d)</th><th>epoch</th><th>SDE</th>
<th>recovered</th></tr>{inj_rows}</table>
<p class="m">This dossier presents evidence. It contains no promotion path:
the terminal machine state is <strong>{DOSSIER_STATUS}</strong>, and only a
human review can move a lead beyond it.</p>
"""
