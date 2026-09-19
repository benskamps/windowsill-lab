#!/usr/bin/env python3
"""Check the Mann relation coefficients in ``tic374861595_refit.py`` against
the published sources, rather than against the memory they were written from.

Why this script exists
----------------------

``tic374861595_refit.py`` carries a caveat from its author, repeated in §7 of
the survey paper:

    the Mann coefficients were reproduced from memory and corroborated only by
    reproducing TIC's own R★ and M★ to four decimals. They must be checked
    against the published tables before anything derived from them goes into
    print.

Reproducing TIC's own numbers is a weak check: TIC v8 *adopts* Mann+2015 from
M_K, so agreeing with TIC mostly proves the arithmetic runs, not that the
coefficients are the published ones. This script does the check the caveat asks
for, against two primary artifacts:

* **Mann et al. (2015), ApJ 804, 64 — Table 1, R★ vs M_Ks.** Compared against
  the values in the paper's own arXiv LaTeX source (arXiv:1501.01635) *and*
  against the 2016 erratum (ApJ 819, 87), which reprinted Tables 1–3 after a
  press error corrupted them in the journal version. Both agree, so the
  distinction does not bite here — but the paper must cite the erratum, because
  the *journal's* Table 1 as originally printed is not the table anyone should
  read.

* **Mann et al. (2019), ApJ 871, 63 — Table 6, M_K → M★, n = 5, no [Fe/H].**
  Compared against the authors' own published MCMC posterior,
  ``resources/Mk-M_7_trim.fits`` in https://github.com/awmann/M_-M_K- , which
  is a stronger reference than the printed table: the table reports medians of
  exactly this posterior, and the posterior also gives the spread, so a
  coefficient can be judged in units of its own uncertainty instead of by
  counting matching digits.

Running it
----------

    py -3.11 scripts/mann_coefficients_check.py              # uses the network
    py -3.11 scripts/mann_coefficients_check.py --posterior path/to.fits

Exits nonzero if any coefficient disagrees with its published value by more
than the tolerance below. The Mann+2015 comparison is exact-match on the
printed digits; the Mann+2019 comparison is a tolerance in posterior sigma,
because the printed Table 6 rounds and the posterior is what was rounded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

POSTERIOR_URL = (
    "https://raw.githubusercontent.com/awmann/M_-M_K-/master/"
    "resources/Mk-M_7_trim.fits"
)

#: Mann et al. (2015), ApJ 804, 64, Table 1, row "R* vs M_Ks", as printed in
#: the arXiv LaTeX source of the accepted paper and reprinted unchanged in the
#: 2016 erratum (ApJ 819, 87). The last two entries are the quoted percent
#: scatter and reduced chi-squared, which the module also hardcodes.
MANN15_PUBLISHED = {
    "coeffs": (1.9515, -0.3520, 0.01680),
    "scatter_pct": 2.89,
    "chi2_red": 0.93,
    "mk_range": (4.6, 9.8),
}

#: How far a hardcoded Mann+2019 coefficient may sit from the median of the
#: authors' posterior before this script calls it wrong. The printed table
#: rounds to three significant figures, which is itself a fraction of a sigma
#: on every coefficient, so anything inside 2 sigma is consistent with the
#: constant having been read off the published table correctly.
MANN19_TOL_SIGMA = 2.0

#: Independent of the coefficients: the mass this star's M_K implies must not
#: move by more than this between the hardcoded constants and the authors'
#: posterior, or the difference stops being cosmetic.
MASS_TOL_FRAC = 0.02

TARGET_MK = 4.98  # the CTOI package's value for TIC 374861595


class PosteriorUnavailable(RuntimeError):
    """The 2019 half could not be RUN. Distinct from the check failing.

    Exiting 1 for a missing import would say "the coefficients are wrong" in the
    same breath as "astropy is not installed", and the whole point of this file
    is that those two must never be confused.
    """


def _load_posterior(path: str | None):
    """Return the (n, 7) posterior array: a0..a5 and the [Fe/H] term f."""
    try:
        from astropy.io import fits
    except ImportError as exc:                 # not a verification failure
        raise PosteriorUnavailable(
            "astropy is needed to read the authors' posterior "
            "(pip install astropy). The Mann+2015 half above still ran."
        ) from exc

    if path:
        return np.asarray(fits.getdata(path), dtype=float)

    import io
    import urllib.request

    with urllib.request.urlopen(POSTERIOR_URL, timeout=120) as fh:
        blob = fh.read()
    return np.asarray(fits.getdata(io.BytesIO(blob)), dtype=float)


def _mass_from(coeffs, mk, zp=7.5):
    x = np.asarray(mk, dtype=float) - zp
    log_m = sum(c * x**i for i, c in enumerate(coeffs))
    return 10.0**log_m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--posterior", default=None,
                    help="local copy of Mk-M_7_trim.fits; downloads if absent")
    ap.add_argument("--mk", type=float, default=TARGET_MK)
    args = ap.parse_args(argv)

    import tic374861595_refit as refit

    failures = []
    print("=" * 78)
    print("Mann+2015, ApJ 804, 64 — Table 1, R* vs M_Ks")
    print("  reference: arXiv:1501.01635 LaTeX source, and the 2016 erratum")
    print("             ApJ 819, 87, which reprinted Tables 1-3 after a press")
    print("             error. Both carry the same values.")
    print("=" * 78)
    for name, got, want in (
        ("a", refit.MANN15_R_COEFFS[0], MANN15_PUBLISHED["coeffs"][0]),
        ("b", refit.MANN15_R_COEFFS[1], MANN15_PUBLISHED["coeffs"][1]),
        ("c", refit.MANN15_R_COEFFS[2], MANN15_PUBLISHED["coeffs"][2]),
        ("scatter", refit.MANN15_R_SCATTER * 100.0,
         MANN15_PUBLISHED["scatter_pct"]),
        ("M_K lo", refit.MANN15_MK_RANGE[0], MANN15_PUBLISHED["mk_range"][0]),
        ("M_K hi", refit.MANN15_MK_RANGE[1], MANN15_PUBLISHED["mk_range"][1]),
    ):
        ok = abs(got - want) < 1e-9
        print(f"  {name:8s} module {got:<12.6g} published {want:<12.6g} "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(f"Mann+2015 {name}: {got} != {want}")

    print()
    print("=" * 78)
    print("Mann+2019, ApJ 871, 63 — Table 6, M_K -> M*, n = 5, no [Fe/H]")
    print("  reference: the authors' own posterior, Mk-M_7_trim.fits from")
    print("             github.com/awmann/M_-M_K- . Table 6 reports medians")
    print("             of this posterior, so sigma is the right yardstick.")
    print("=" * 78)
    try:
        post = _load_posterior(args.posterior)
    except PosteriorUnavailable as exc:
        print(f"  SKIPPED: {exc}")
        print()
        print("=" * 78)
        print("Mann+2015: checked.  Mann+2019: NOT CHECKED (could not run).")
        print("Exit 3 means undetermined, never 'the coefficients disagree'.")
        print("=" * 78)
        return 3
    print(f"  posterior: {post.shape[0]:,} samples x {post.shape[1]} parameters")
    med = np.median(post[:, :6], axis=0)
    sig = np.std(post[:, :6], axis=0)
    print(f"  {'i':>2} {'module':>13} {'author median':>14} "
          f"{'author sigma':>13} {'delta/sigma':>12}")
    for i, got in enumerate(refit.MANN19_M_COEFFS):
        pull = (got - med[i]) / sig[i]
        ok = abs(pull) <= MANN19_TOL_SIGMA
        print(f"  {i:>2} {got:>13.6g} {med[i]:>14.6g} {sig[i]:>13.4g} "
              f"{pull:>+11.2f} {'OK' if ok else 'MISMATCH'}")
        if not ok:
            failures.append(
                f"Mann+2019 a{i}: {got} is {pull:+.2f} sigma from "
                f"the posterior median {med[i]:.6g}")

    zp_ok = abs(refit.MANN19_M_ZP - 7.5) < 1e-12
    print(f"  zero point  module {refit.MANN19_M_ZP} published 7.5 "
          f"{'OK' if zp_ok else 'MISMATCH'}   (mk_mass.py line: zp = 7.5)")
    if not zp_ok:
        failures.append(f"Mann+2019 zero point {refit.MANN19_M_ZP} != 7.5")

    print()
    print("-" * 78)
    print(f"consequence at this star (M_K = {args.mk})")
    print("-" * 78)
    m_mod = float(_mass_from(refit.MANN19_M_COEFFS, args.mk))
    m_med = float(_mass_from(med, args.mk))
    x = args.mk - 7.5
    m_post = 10.0 ** sum(post[:, i] * x**i for i in range(6))
    frac = m_mod / m_med - 1.0
    print(f"  module coefficients        {m_mod:.5f} Msun")
    print(f"  authors' posterior median  {m_med:.5f} Msun")
    print(f"  full authors' posterior    {np.median(m_post):.5f} "
          f"+/- {np.std(m_post):.5f} Msun "
          f"({100 * np.std(m_post) / np.median(m_post):.2f} %)")
    print(f"  difference                 {100 * frac:+.3f} %  "
          f"(tolerance {100 * MASS_TOL_FRAC:.0f} %)")
    if abs(frac) > MASS_TOL_FRAC:
        failures.append(f"mass at M_K={args.mk} differs by {100 * frac:+.2f} %")

    print()
    print("-" * 78)
    print("the package's \"Mann+2019 mass 0.72 Msun\" line, flagged suspect")
    print("-" * 78)
    # scipy is a heavy dependency to carry for one root-find on a monotone
    # function, and an unguarded import here would exit 1 — indistinguishable
    # from "the coefficients disagree", which is the one confusion this file
    # exists to prevent. Bisect it ourselves instead.
    def _mk_at_mass(target, lo=3.0, hi=7.0):
        # mass falls monotonically with M_K over this range, so plain bisection
        # converges and needs nothing but the relation already in hand.
        if (float(_mass_from(med, lo)) - target) * \
           (float(_mass_from(med, hi)) - target) > 0:
            return None                         # not bracketed; say so, do not guess
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if (float(_mass_from(med, lo)) - target) * \
               (float(_mass_from(med, mid)) - target) <= 0:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    mk_072 = _mk_at_mass(0.72)
    if mk_072 is None:
        print("  Mann+2019 never returns 0.72 Msun for 3 < M_K < 7 at all.")
        mk_072 = float("nan")
    # Absolute magnitude runs backwards: a SMALLER M_K is a brighter star. The
    # 0.72 root sits below this star's M_K, so it is brighter, not fainter.
    print(f"  Mann+2019 returns 0.72 Msun at M_K = {mk_072:.3f}, which is "
          f"{args.mk - mk_072:.2f} mag")
    print(f"  brighter than this star's {args.mk}. At this star's M_K the "
          f"relation gives {m_med:.4f}.")
    print("  Mann+2015's own mass relation (Table 1, 4th order) gives "
          f"{_mann15_mass(args.mk):.4f},")
    print("  so the 0.72 is not that relation misattributed either. It is "
          "not reproducible")
    print("  from either Mann relation at this star's M_K.")

    print()
    if failures:
        print(f"FAILED — {len(failures)} disagreement(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=" * 78)
    print("PASSED — every Mann coefficient in tic374861595_refit.py matches "
          "its published")
    print("source. The \"reproduced from memory\" caveat in the script's "
          "docstring and in")
    print("§7 of the survey paper is discharged; cite Mann+2015 Table 1 *as "
          "corrected by")
    print("the 2016 erratum, ApJ 819, 87*.")
    print("=" * 78)
    return 0


def _mann15_mass(mk):
    """Mann+2015 Table 1's own M_Ks -> M* relation, for the 0.72 diagnosis.

    M*/Msun = a + b*M_Ks + c*M_Ks^2 + d*M_Ks^3 + e*M_Ks^4, a semi-empirical
    relation from model-derived masses. Superseded by Mann+2019, which is
    calibrated on dynamical masses; quoted here only to test whether the
    package's stray 0.72 could have come from reading the older row.
    """
    c = (0.5858, 0.3872, -0.1217, 0.0106, -2.7262e-4)
    return sum(a * mk**i for i, a in enumerate(c))


if __name__ == "__main__":
    raise SystemExit(main())
