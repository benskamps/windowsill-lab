"""The guard that would have caught it — DAIDO/HONG as the regression fixture.

Two defects, one pair of constants, and the point of this file is that they fail
differently. The arithmetic half (both papers predict gamma = 0.25, so the
supercritical branch discriminates nothing) was found by a human after four
GPU-hours and lived on as a comment. The observable half (both papers are about
``N*Var_t(r)``; K03 measures ``d<r>/dh``) is invisible to that arithmetic — on
gamma_prime the numbers separate cleanly at 1.0 vs 0.25, so a numbers-only guard
returns "discriminating" and funds a run comparing a response slope to a
fluctuation exponent.

The three assertions that pin the lane are ``test_the_asymmetric_pair_*``: RAISE
on the bench K03 actually instruments, PASS only on the fluctuation observable,
and RAISE on gamma whatever the bench is doing.
"""
import json
import pathlib

import pytest

from lab import k03
from lab.rivals import Rival, discriminates_on


PAIR = (k03.DAIDO, k03.HONG)


def _rival(name="a", **over):
    """A minimal well-formed rival; override one field to test one refusal."""
    kw = dict(name=name, claim="a claim", observable="observable X",
              predicts={"gamma": 1.0}, resolvable_at={"gamma": 0.1},
              source="Someone, Some Journal 1, 1 (2000)",
              frequency_class="regular", distribution="Lorentzian")
    kw.update(over)
    return Rival(**kw)


# ── the regression fixture: the run that must never be green-lit again ───────

def test_the_asymmetric_pair_is_refused_on_the_observable_k03_instruments():
    """gamma_prime separates numerically (1.0 vs 0.25) and is STILL refused,
    because the bench measures a response and the papers predict a fluctuation.

    This is the assertion the numeric guard could not make. Both branches of the
    instrument are checked: the brief's ``d<r>/dh`` and the subcritical
    ``d<cos theta>/dh`` the below branch actually reads.
    """
    for branch in ("above", "below"):
        with pytest.raises(ValueError) as exc:
            discriminates_on(PAIR, "gamma_prime",
                             k03.INSTRUMENT_OBSERVABLE[branch])
        assert "different quantities" in str(exc.value)
        assert k03.FLUCTUATION_OBSERVABLE in str(exc.value)


def test_instrument_for_hands_the_guard_the_truth_about_the_bench():
    """The ergonomic path must lead to the refusal, not around it. If asking the
    module what it measures returns something the pair passes against, the guard
    is decoration."""
    assert k03.instrument_for("gamma_prime") == (
        k03.INSTRUMENT_OBSERVABLE["below"])
    assert k03.instrument_for("gamma") == k03.INSTRUMENT_OBSERVABLE["above"]
    # And the two branches must stay DIFFERENT strings. Collapsing them passed
    # every other assertion in this file, because both branches are equally
    # wrong for a fluctuation exponent — but K03 really does read two
    # quantities (``obs_key = "m_mean" if branch == "below" else "r_mean"``,
    # k03.measure_grid), and a bench that misdescribes its own subcritical
    # observable on the receipt is this lane's defect wearing a smaller hat.
    assert (k03.INSTRUMENT_OBSERVABLE["below"]
            != k03.INSTRUMENT_OBSERVABLE["above"])
    with pytest.raises(ValueError, match="different quantities"):
        discriminates_on(PAIR, "gamma_prime", k03.instrument_for("gamma_prime"))
    with pytest.raises(KeyError, match="names no branch"):
        k03.instrument_for("beta")


def test_the_asymmetric_pair_passes_only_on_the_fluctuation_observable():
    """The same pair, the same exponent, on the quantity the papers are about."""
    record = discriminates_on(PAIR, "gamma_prime", k03.FLUCTUATION_OBSERVABLE)
    assert record["narrowest_gap"] == pytest.approx(0.75)
    assert record["resolvable_at"] == pytest.approx(k03.EXPONENT_RESOLUTION)
    assert record["rivals"] == ["daido", "hong"]


def test_the_supercritical_branch_is_refused_regardless_of_observable():
    """The older defect, kept: both papers predict gamma = 0.25, so that branch
    carries no information about which is right and costs four GPU-hours to say
    so. It must refuse on the CORRECT observable too — otherwise a degenerate
    pair hides behind whichever error the caller happened to make second."""
    for instrument in (k03.FLUCTUATION_OBSERVABLE,
                       k03.INSTRUMENT_OBSERVABLE["above"],
                       k03.INSTRUMENT_OBSERVABLE["below"]):
        with pytest.raises(ValueError) as exc:
            discriminates_on(PAIR, "gamma", instrument)
        assert "cannot tell" in str(exc.value)


def test_the_two_defects_are_reported_separately():
    """A caller fixing one must not be told it fixed the other."""
    numeric = str(pytest.raises(
        ValueError, discriminates_on, PAIR, "gamma",
        k03.FLUCTUATION_OBSERVABLE).value)
    observable = str(pytest.raises(
        ValueError, discriminates_on, PAIR, "gamma_prime",
        k03.INSTRUMENT_OBSERVABLE["above"]).value)
    assert "different quantities" not in numeric
    assert "cannot tell" not in observable


# ── the discrimination arithmetic ────────────────────────────────────────────

def test_a_gap_at_the_resolution_is_refused_and_just_outside_it_passes():
    """The boundary, pinned: ``<`` not ``<=``. A pair exactly one resolution
    apart is the marginal case the design is allowed to attempt.

    The values are binary-exact on purpose. Written with 0.1/1.1 this assertion
    pinned nothing: ``1.1 - 1.0`` is 0.10000000000000009, so the "edge" case
    sits *outside* the resolution by a float artefact and passes under ``<=``
    just as it does under ``<``. 1.0/1.25 at a resolution of 0.25 gives a gap of
    exactly 0.25, which is the only arithmetic that can tell the two operators
    apart.
    """
    a = _rival("a", predicts={"gamma": 1.0}, resolvable_at={"gamma": 0.25})
    inside = _rival("b", predicts={"gamma": 1.125},
                    resolvable_at={"gamma": 0.25})
    edge = _rival("c", predicts={"gamma": 1.25}, resolvable_at={"gamma": 0.25})
    assert abs(1.25 - 1.0) == 0.25, "the boundary case must be exact, not near"
    with pytest.raises(ValueError, match="cannot tell"):
        discriminates_on((a, inside), "gamma", "observable X")
    assert discriminates_on((a, edge), "gamma", "observable X")["rivals"]


def test_the_coarser_of_the_two_resolutions_governs():
    """A rival that admits it is only good to 0.5 cannot be separated at 0.2 by
    an opponent who claims more precision than the pair jointly has."""
    coarse = _rival("coarse", predicts={"gamma": 1.0},
                    resolvable_at={"gamma": 0.5})
    fine = _rival("fine", predicts={"gamma": 1.3}, resolvable_at={"gamma": 0.01})
    with pytest.raises(ValueError, match="cannot tell"):
        discriminates_on((coarse, fine), "gamma", "observable X")


def test_a_lone_claim_is_not_a_rival_pair():
    with pytest.raises(ValueError, match="at least two rivals"):
        discriminates_on((_rival(),), "gamma", "observable X")


def test_an_exponent_no_rival_predicts_is_refused():
    with pytest.raises(ValueError, match="nothing here to discriminate"):
        discriminates_on((_rival("a"), _rival("b")), "nu_bar", "observable X")


def test_one_mismatched_rival_in_an_otherwise_sound_field_is_enough():
    """Three rivals, two on the bench's observable and one not: still refused,
    and the refusal names the one that does not belong."""
    on = _rival("on1", predicts={"gamma": 1.0})
    also = _rival("on2", predicts={"gamma": 2.0})
    off = _rival("off", predicts={"gamma": 3.0}, observable="observable Y")
    with pytest.raises(ValueError, match="off"):
        discriminates_on((on, also, off), "gamma", "observable X")


def test_the_record_reports_frequency_class_without_gating_on_it():
    """Daido measured a Lorentzian, Hong a Gaussian. Two ensembles can
    legitimately disagree, so this is surfaced for the reader and never
    raises — refusing it would forbid the interesting case."""
    record = discriminates_on(PAIR, "gamma_prime", k03.FLUCTUATION_OBSERVABLE)
    assert "Lorentzian" in record["frequency_classes"]["daido"]
    assert "Gaussian" in record["frequency_classes"]["hong"]
    assert record["citations_verified_from_bytes"] is False


def test_a_half_verified_pair_is_not_a_verified_pair():
    """``all``, not ``any``. Both rivals in this repo carry an empty
    ``verified_from``, so the assertion above is green under either operator —
    which means the flag that tells a reader "these citations were read, not
    recalled" could quietly start reporting True the moment ONE of a pair got
    backing bytes. A field whose whole job is to say what is verified must not
    round a half-read pair up to read."""
    read = _rival("read", verified_from="evidence/literature/somebody-1989.json")
    recalled = _rival("recalled", predicts={"gamma": 2.0})
    record = discriminates_on((read, recalled), "gamma", "observable X")
    assert record["citations_verified_from_bytes"] is False
    both = _rival("both", predicts={"gamma": 2.0},
                  verified_from="evidence/literature/someone-else-1990.json")
    assert discriminates_on((read, both), "gamma",
                            "observable X")["citations_verified_from_bytes"]


def test_the_narrowest_pair_governs_the_margin_the_receipt_carries():
    """With three rivals the record's numbers stop being a formality.

    ``narrowest_gap`` is the margin a caller puts on the receipt to justify
    spending the GPU-hours, so it has to be the CLOSEST pair — the one that
    decides whether the run can adjudicate — not the first pair enumerated and
    not the widest. Every other test here poses exactly two rivals, where those
    three readings coincide and the field pins nothing. Reported alongside it,
    ``resolvable_at`` must be that same pair's resolution rather than the
    field's coarsest, or the two halves of the margin describe different pairs.
    """
    wide = _rival("wide", predicts={"gamma": 1.0}, resolvable_at={"gamma": 0.5})
    near_a = _rival("near_a", predicts={"gamma": 3.0},
                    resolvable_at={"gamma": 0.05})
    near_b = _rival("near_b", predicts={"gamma": 3.2},
                    resolvable_at={"gamma": 0.05})
    record = discriminates_on((wide, near_a, near_b), "gamma", "observable X")
    assert record["narrowest_gap"] == pytest.approx(0.2)
    assert record["resolvable_at"] == pytest.approx(0.05)


# ── the Rival constructor ────────────────────────────────────────────────────

@pytest.mark.parametrize("blank", ["name", "claim", "observable", "source",
                                   "frequency_class", "distribution"])
def test_a_rival_missing_any_required_fact_cannot_be_constructed(blank):
    with pytest.raises(ValueError, match="missing"):
        _rival(**{blank: "   "})


def test_a_prediction_with_no_resolution_is_refused():
    """A number with no resolution cannot be shown to differ from anything —
    which is precisely how the gamma branch got funded."""
    with pytest.raises(ValueError, match="resolvable_at"):
        _rival(predicts={"gamma": 1.0, "gamma_prime": 2.0},
               resolvable_at={"gamma": 0.1})


def test_a_rival_predicting_nothing_is_refused():
    with pytest.raises(ValueError, match="predicts nothing"):
        _rival(predicts={}, resolvable_at={})


def test_a_published_claim_cannot_be_quietly_rewritten():
    """``frozen=True`` stops at the dict boundary, and the dicts are where the
    numbers are. Before this was pinned, ``k03.DAIDO.predicts["gamma_prime"] =
    0.25`` succeeded — on a module-level singleton, for the rest of the process
    — and turned the asymmetric claim into the symmetric one with no error and
    no receipt. A type whose argument is that a published claim is a fixed
    thing you must argue with cannot leave its claims editable."""
    with pytest.raises(TypeError):
        k03.DAIDO.predicts["gamma_prime"] = 0.25
    with pytest.raises(TypeError):
        k03.DAIDO.resolvable_at["gamma_prime"] = 1e-9
    assert k03.DAIDO["gamma_prime"] == 1.0
    # And the constructor must not alias a caller's dict either: mutating the
    # dict you passed in is the same rewrite by a longer route.
    source = {"gamma": 1.0}
    r = _rival(predicts=source, resolvable_at={"gamma": 0.1})
    source["gamma"] = 99.0
    assert r["gamma"] == 1.0


# ── the dict access the estate already depends on ────────────────────────────

def test_rivals_still_read_as_the_dicts_they_replaced():
    """``k03._verdict``, the U-K01 reach test and two committed receipts index
    these claims by key. Converting to a dataclass must not break them."""
    assert k03.DAIDO["gamma"] == 0.25
    assert k03.DAIDO["gamma_prime"] == 1.0
    assert k03.HONG["gamma_prime"] == 0.25
    assert "1989" in k03.DAIDO["source"]
    assert k03.DAIDO.get("nu_bar") is None
    with pytest.raises(KeyError):
        k03.DAIDO["nu_bar"]


def test_membership_answers_instead_of_raising_about_integers():
    """``"gamma_prime" in DAIDO`` is the next thing anyone writes after
    ``DAIDO["gamma_prime"]``, and an object advertising dict access has to
    answer instead of raising about types.

    The integer case is belt AND braces: ``__dataclass_fields__`` already turns
    ``DAIDO[0]`` into a KeyError even with the ``isinstance`` guard removed, so
    that half is pinned here for the behaviour, not for the guard. The half
    only the guard can carry is the UNHASHABLE key, which without it dies on
    the ``in self.predicts`` lookup with ``TypeError: unhashable type: 'list'``
    — a message about Python's data model where a message about this callsite
    belongs."""
    assert "gamma_prime" in k03.DAIDO
    assert "source" in k03.DAIDO
    assert "nu_bar" not in k03.DAIDO
    with pytest.raises(KeyError):
        k03.DAIDO[0]
    with pytest.raises(KeyError):
        k03.DAIDO[["gamma_prime"]]
    assert ["gamma_prime"] not in k03.DAIDO
    # Its FIELDS, not its namespace. A bare getattr answers this with a bound
    # method, and a method that reaches `references` in a receipt is a crash at
    # publication time instead of a KeyError at the callsite that caused it.
    assert "to_json" not in k03.DAIDO
    with pytest.raises(KeyError):
        k03.DAIDO["to_json"]


def test_the_citation_correction_is_pinned():
    """The asymmetric pair is NOT in Prog. Theor. Phys. 75, 1460 (1986) — that
    paper gives the same exponent on both sides of the threshold. The asymmetry
    is in PTP 81, 727 (1989) and J. Stat. Phys. 60, 753 (1990), both of which
    are fluctuation papers, which is the observable mismatch stated twice."""
    assert "75, 1460" not in k03.DAIDO["source"]
    assert "81, 727 (1989)" in k03.DAIDO["source"]
    assert "60, 753 (1990)" in k03.DAIDO["source"]


def test_to_json_is_a_superset_of_the_committed_receipt_shape():
    """The 2026-08-15 and 2026-08-23 receipts carry gamma, gamma_prime and
    source at the top level. A reader diffing old against new must see
    additions and no moves."""
    blob = k03.DAIDO.to_json()
    assert set(blob) >= {"gamma", "gamma_prime", "source"}
    assert blob["gamma_prime"] == 1.0
    assert blob["observable"] == k03.FLUCTUATION_OBSERVABLE
    assert blob["distribution"] == "Lorentzian"
    # The honest empty string has to REACH the receipt. Dropping this key from
    # to_json broke nothing else in this file, and the reader of a published
    # run would then have no way to tell a citation that was read from one that
    # was remembered — which is the F1/F2 failure mode the field exists for.
    assert blob["verified_from"] == ""
    # "No moves" is an ORDER claim and this repo dumps without sort_keys, so a
    # key-set superset is not enough: the committed prefix has to still be the
    # prefix, or the diff shows `source` deleted here and re-added lower down.
    # Anchored on __file__, not cwd — the register test_publish.py uses. A
    # relative path here passes from the repo root and fails from anywhere else.
    root = pathlib.Path(__file__).resolve().parents[1]
    committed = json.loads(
        (root / "reports/receipts/run-2026-08-23-2216-k03.json")
        .read_text(encoding="utf-8"))["references"]["daido"]
    assert list(committed) == ["gamma", "gamma_prime", "source"], (
        "the receipt this test pins against has changed shape")
    assert list(blob)[:3] == list(committed)


def test_the_receipt_records_both_observables_side_by_side():
    """The mismatch has to be visible on the artifact, not only in a docstring
    — that is how it survived a year the first time."""
    result = k03.run_k03(n=8, n_points=2, rungs=2, t_burn=0.5, t_measure=1.0,
                         pilot_t_burn=0.25, pilot_t_measure=0.5, seed=3)
    report = k03.to_report(result)
    assert report["references"]["daido"]["observable"] == (
        k03.FLUCTUATION_OBSERVABLE)
    assert report["instrument_observable"]["above"] != (
        k03.FLUCTUATION_OBSERVABLE)


def test_the_report_still_serializes_to_json():
    """``references`` used to hold plain dicts and the receipts ledger dumps it.
    A dataclass leaking into the report would crash publication.

    Serialized exactly the way ``cli.py`` serializes a receipt — no ``default=``
    hook. This test was written with ``default=str``, which made it green on the
    precise defect it names: a leaked ``Rival`` is not JSON-serializable, but
    ``default=str`` catches the TypeError and writes ``"Rival(name='daido', …)"``
    into the receipt instead. Verified by mutation — putting the raw dataclass
    back into ``references`` passed under ``default=str`` and fails here.
    """
    result = k03.run_k03(n=8, n_points=2, rungs=2, t_burn=0.5, t_measure=1.0,
                         pilot_t_burn=0.25, pilot_t_measure=0.5, seed=3)
    report = k03.to_report(result)
    # No sort_keys: this repo's committed artifacts are order-sensitive.
    assert json.dumps(report)
    # And the exponents must survive as NUMBERS, not as a stringified object.
    assert isinstance(report["references"]["daido"]["gamma_prime"], float)
