"""Two rivals are only rivals if the bench can tell them apart — on the quantity
the bench actually measures.

The estate has now made the same design mistake twice on one experiment, and the
two halves fail differently, which is why one guard is not enough.

**The first half, caught by arithmetic.** ``k03.DAIDO`` and ``k03.HONG`` both
predict gamma = 0.25 above K_c. The supercritical branch therefore carried zero
discriminating power, and K03 spent four GPU-hours measuring it anyway. A human
found that afterwards by reading two papers, wrote it down as a module constant
(``u_k01_window.DISCRIMINATING_GAP``) and a prose note, and never promoted it to
a constructor. ``discriminates_on`` promotes it: two predictions closer than the
resolution that separates them RAISE instead of being funded.

**The second half, invisible to that arithmetic.** Daido's and Hong's numbers are
FLUCTUATION exponents — the divergence of ``chi = N*Var_t(r)``, the intrinsic
noise of the order parameter. K03 does not measure that. K03 measures a linear
RESPONSE, ``d<r>/dh`` to an explicit pinning field, and says so in its own
docstring heading, directly above the two constants that contradict it. The
numeric guard is blind to this: on gamma_prime the pair separates cleanly
(1.0 vs 0.25), so the arithmetic returns "discriminating" and green-lights a run
comparing a response slope to a fluctuation exponent.

And the failure that produces is not an honest null. It is a FALSE POSITIVE. A
subcritical response slope landing anywhere near 1 coincides, to the eye and to
the sigma-distance, with ``DAIDO["gamma_prime"] = 1.0``; the receipt prints
"Daido confirmed, Hong refuted" at high confidence and both halves of that
sentence are wrong. A null costs GPU-hours. This costs a published claim.

So the missing dimension is not another number. A value and a resolution say
nothing about WHAT WAS MEASURED, and no amount of precision on the wrong
quantity becomes an answer about the right one. Every ``Rival`` therefore names
the observable its numbers live on, and ``discriminates_on`` refuses when that
observable is not the one on the bench.

No registry, no framework, no base class. A rival is five facts about a
published claim and a constructor that will not let three of them be blank.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType

#: The fields a rival cannot be constructed without. ``claim`` is here on
#: purpose alongside the numbers: a rival stated only as a float pair is a row
#: in a table, and a table has never stopped anyone from testing the wrong
#: thing. Saying what the paper asserts, in words, is what makes the observable
#: mismatch visible to a reader before the constructor has to catch it.
REQUIRED = ("name", "claim", "observable", "source", "frequency_class",
            "distribution")


@dataclass(frozen=True, eq=False)
class Rival:
    """One published claim, in the shape that lets a bench refuse to test it.

    ``predicts`` maps exponent name to predicted value, and ``resolvable_at``
    maps the same names to the coarsest resolution at which that prediction is
    still a DISTINCT claim rather than a rounding of its opponent's. The
    resolution sits on the rival and not on the instrument deliberately: it has
    to exist before anyone builds the instrument, because its whole job is to
    answer "is this pair worth a measurement at all?" while that question is
    still cheap.

    ``frequency_class`` and ``distribution`` are recorded because two papers can
    predict different numbers for the same exponent and both be right, having
    measured different ensembles. They are REPORTED, never gated — see
    ``discriminates_on`` for why that line is drawn where it is.

    ``verified_from`` names the bytes under ``evidence/literature/`` that back
    the citation. Empty means the citation is RECALLED, not verified, which is
    the estate's F1/F2 failure mode and is the honest state of every rival in
    this repo today. It is legibility, not a gate: a constructor cannot tell a
    confident misremembering from a reading, so refusing on this field would buy
    a ValueError and no truth.

    ``eq=False`` keeps ``__hash__`` at object identity. A generated one would be
    a landmine — ``predicts`` is a dict and would raise on the first ``hash()``
    — and rivals are module-level singletons where identity is the right
    equality anyway.
    """

    name: str
    claim: str
    observable: str
    predicts: dict
    resolvable_at: dict
    source: str
    frequency_class: str
    distribution: str
    verified_from: str = ""

    def __post_init__(self) -> None:
        missing = [f for f in REQUIRED
                   if not str(getattr(self, f, "")).strip()]
        if missing:
            raise ValueError(
                f"{self.name or 'rival'} is missing {', '.join(missing)} — a "
                "claim that will not say whose it is, what it asserts, or what "
                "quantity it asserts it about cannot be argued with")
        if not self.predicts:
            raise ValueError(f"{self.name} predicts nothing")
        unpriced = [k for k in self.predicts if k not in self.resolvable_at]
        if unpriced:
            raise ValueError(
                f"{self.name} predicts {', '.join(sorted(unpriced))} with no "
                "resolvable_at. A number with no resolution cannot be shown to "
                "differ from anything, which is how a degenerate pair gets "
                "funded")
        # ``frozen=True`` guards the ATTRIBUTES and stops at the dict boundary,
        # which on this type is where the load-bearing numbers live: without
        # this, ``k03.DAIDO.predicts["gamma_prime"] = 0.25`` succeeds on a
        # module-level singleton and rewrites a published claim for the rest of
        # the process. A type whose whole argument is that a claim is a fixed
        # thing you must argue with cannot leave its claims editable.
        object.__setattr__(self, "predicts", MappingProxyType(dict(self.predicts)))
        object.__setattr__(self, "resolvable_at",
                           MappingProxyType(dict(self.resolvable_at)))

    def __getitem__(self, key: str):
        """Dict access, kept alive on purpose.

        The receipts ledger, ``k03._verdict`` and the U-K01 reach test all reach
        into these claims by key (``DAIDO["gamma_prime"]``). Migrating them to a
        dataclass is not worth breaking two committed receipts and a checker
        over, so a rival reads as the dict it replaced: predicted exponents
        first, then its own fields.

        The non-string guard earns less than an earlier draft of this docstring
        claimed, and the claim is corrected here rather than left standing,
        because prose that overstates what the code below it does is the exact
        defect this module was written to close. An integer key does NOT reach
        ``getattr`` and never raised ``TypeError: attribute name must be string``:
        the ``__dataclass_fields__`` test further down already turns it into a
        ``KeyError``. What the guard actually buys is the UNHASHABLE key —
        ``rival[["gamma"]]`` would otherwise die on ``key in self.predicts``
        with ``TypeError: unhashable type``, which says nothing true about the
        callsite. A KeyError does: this is keyed lookup.

        Keyed lookup and deliberately not a sequence. ``list(rival)`` raises
        ``KeyError(0)`` rather than yielding keys, because Python's legacy
        iteration protocol wants ``IndexError`` to stop and this type never
        promised iteration. Nothing in the estate iterates a claim — the
        serializer wants ``to_json``, and the three consumers named above all
        index by name — so ``__iter__`` would be machinery bought for no
        caller. The sharp edge is named here instead of padded.
        """
        if not isinstance(key, str):
            raise KeyError(key)
        if key in self.predicts:
            return self.predicts[key]
        if key not in self.__dataclass_fields__:
            # Its own FIELDS, not its whole namespace. A bare ``getattr`` here
            # answers ``rival["to_json"]`` with a bound method, which is a
            # value no caller wants and one that reaches a receipt as an
            # unserializable object rather than as a KeyError at the callsite.
            raise KeyError(key)
        return getattr(self, key)

    def __contains__(self, key) -> bool:
        """``"gamma" in rival`` — because the docstring above promises dict
        access, and membership is the next thing anyone writes after lookup."""
        return isinstance(key, str) and (key in self.predicts
                                         or key in self.__dataclass_fields__)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def to_json(self) -> dict:
        """The receipt shape — a SUPERSET of the dict this type replaced.

        The predicted exponents stay flattened at the top level next to
        ``source`` because that is exactly how the 2026-08-15 and 2026-08-23 K03
        receipts already carry them; the new fields are added alongside rather
        than nesting the old ones somewhere else. A reader diffing an old
        receipt against a new one should see additions and no moves.

        "No moves" is an ORDER claim, not only a key-set one, and this repo
        serializes without ``sort_keys`` — so the committed prefix
        ``gamma, gamma_prime, source`` is emitted in that order and everything
        new lands after it. Appending ``source`` at the end instead would still
        be a superset by keys while showing up in a receipt diff as a deleted
        line and a re-added one four fields lower, which is exactly the "moved"
        this docstring promises a reader they will not have to read past.
        """
        out = {k: float(v) for k, v in self.predicts.items()}
        out["source"] = self.source
        out.update({
            "name": self.name,
            "claim": self.claim,
            "observable": self.observable,
            "resolvable_at": {k: float(v)
                              for k, v in self.resolvable_at.items()},
            "frequency_class": self.frequency_class,
            "distribution": self.distribution,
            "verified_from": self.verified_from,
        })
        return out


def discriminates_on(rivals, exponent: str, instrument: str) -> dict:
    """Can this bench, measuring THIS quantity, tell these rivals apart?

    Raises ``ValueError`` if not. Returns the discrimination record if so, so a
    caller can put the arithmetic in the receipt rather than in a comment
    somebody writes after the money is spent.

    Two refusals, in this order:

    1. **Degeneracy between the rivals.** Any pair whose predictions for
       ``exponent`` differ by less than the coarser of their two resolutions.
    2. **Observable mismatch with the bench.** Any rival whose numbers are
       defined on a quantity other than ``instrument``.

    The order is deliberate and it is the opposite of the intuitive one.
    Degeneracy is a fact about the claims alone, not about the bench, so a
    degenerate pair reports itself as degenerate on EVERY bench — including a
    correctly-instrumented one — instead of hiding behind whichever error the
    caller happened to make second. That is the older, cheaper, more universal
    defect and it should be the first thing anyone hears.

    The cost of that order, stated rather than hidden: step 1 compares
    ``|v_a - v_b|`` across rivals that step 2 has not yet confirmed are talking
    about the same quantity, so a pair disagreeing with EACH OTHER on the
    observable can be reported as degenerate before it is reported as
    incomparable. Nothing escapes — two different observable strings cannot both
    equal one ``instrument``, so step 2 always fires on such a pair eventually —
    but the first message a caller sees may be the less fundamental one.

    What is deliberately NOT refused: a mismatch in ``frequency_class`` or
    ``distribution`` between rivals. Two papers measuring different ensembles
    may legitimately disagree, and that disagreement is sometimes the finding
    rather than the bug — refusing it would forbid the interesting case. It is
    returned in the record instead, where a reader can see it.
    """
    rivals = tuple(rivals)
    if len(rivals) < 2:
        raise ValueError(
            "discrimination needs at least two rivals — one claim and its "
            "negation is not a rival pair, it is the single pairing strong "
            "inference exists to forbid")
    silent = [r.name for r in rivals if exponent not in r.predicts]
    if silent:
        raise ValueError(
            f"{', '.join(silent)} make(s) no prediction for {exponent!r} — "
            "there is nothing here to discriminate")

    narrowest = None
    for a, b in combinations(rivals, 2):
        gap = abs(float(a.predicts[exponent]) - float(b.predicts[exponent]))
        resolution = max(float(a.resolvable_at[exponent]),
                         float(b.resolvable_at[exponent]))
        if narrowest is None or gap < narrowest[0]:
            narrowest = (gap, resolution)
        if gap < resolution:
            raise ValueError(
                f"this experiment cannot tell {a.name} and {b.name} apart on "
                f"{exponent}: they predict {a.predicts[exponent]:g} and "
                f"{b.predicts[exponent]:g}, a gap of {gap:g} inside the "
                f"{resolution:g} that separates them. Measuring it buys "
                "precision, not an answer")

    wrong = [r for r in rivals if r.observable != instrument]
    if wrong:
        named = '; '.join(f"{r.name} predicts {exponent} for {r.observable!r}"
                          for r in wrong)
        raise ValueError(
            f"{named} — but this bench measures "
            f"{instrument!r}. These are different quantities and no amount of "
            "precision on one is evidence about the other — a number landing "
            "near the prediction here would be a coincidence read as a "
            "confirmation, which is worse than measuring nothing")

    return {
        "exponent": exponent,
        "observable": instrument,
        "rivals": [r.name for r in rivals],
        "narrowest_gap": narrowest[0],
        "resolvable_at": narrowest[1],
        # Reported, not gated. Two ensembles, two legitimately different
        # answers — the reader decides whether that is the finding or the flaw.
        "frequency_classes": {r.name: f"{r.frequency_class} {r.distribution}"
                              for r in rivals},
        "citations_verified_from_bytes": all(bool(r.verified_from.strip())
                                             for r in rivals),
    }
