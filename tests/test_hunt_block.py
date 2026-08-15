"""The hunt block — pot.json's survey ledger, a pure function of the committed
``reports/hunts/*.json`` receipts.

The contract under test (docs/a05-receipt-schema.md + Lane 5):

* receipts that cannot be honestly aggregated are REFUSED and named — an
  above-threshold hit with no machine disposition, a schema≥1 receipt with no
  injection coverage on its hits, a schema-0 receipt missing its pilot marker
  or run-level injections, and any receipt whose machine emitted ``planet``;
* every counter is re-derived from rows, never read from a receipt's own
  ``counts`` — a lying summary total is caught, not repeated;
* ``planets_discovered`` is pinned to a literal 0: no receipt content can
  raise it, because promotion to "planet" is a human act on MILESTONES.md,
  not a machine act on a JSON file;
* ``claim_boundary`` ships byte-identical from the newest accepted receipt,
  and ``as_of`` is that receipt's date — the page says "as of", never "live";
* the pre-A05 pilots ride in as schema 0 with an explicit pilot marker and a
  ``pilot (pre-A05 statistics)`` provenance label on the last-hunt line;
* a catalog match whose community disposition is FP (TIC 278866211 =
  TOI 189.01, TFOPWG FP) is machine-dispositioned ``toi-known-fp`` — not a
  recovery, not a lead.

Stdlib-only, like the rest of the publish tests.
"""
import json
from pathlib import Path

from lab.publish import (
    HUNT_KNOWN_FP, HUNT_SDE_THRESHOLD, PILOT_PROVENANCE,
    hunt_block, translate_pilot_summary,
)

ROOT = Path(__file__).resolve().parent.parent
HUNTS = ROOT / "reports" / "hunts"
PAGE = ROOT / "web" / "index.html"
PILOT_SUMMARY = (ROOT / "docs" / "investigations" /
                 "2026-08-14-a04-discovery-pilot-summary.json")
COMMITTED_PILOT = HUNTS / "hunt-2026-08-14-s2-pilot-158.json"


# ── Fixtures: minimal receipts in the shapes the aggregator must judge ───────

def _schema1_receipt(**overrides) -> dict:
    """A minimal well-formed schema-1 receipt: one dispositioned hit carrying
    its injection ladder, one sub-threshold row, honest counts."""
    receipt = {
        "experiment": "a05-survey-hunt",
        "schema": 1,
        "generated_at": "2026-08-20T03:00:00+00:00",
        "sector": 2,
        "sde_threshold": 8.0,
        "targets": [
            {"tic": "111", "outcome": "searched", "sde": 9.1,
             "disposition": "eclipsing-binary-secondary",
             "injections": [{"depth": 0.002, "period_days": 2.3,
                             "sde": 4.9, "recovered": False}]},
            {"tic": "222", "outcome": "searched", "sde": 5.0},
        ],
        "counts": {"attempted": 2, "searched": 2, "above_threshold": 1},
        "wall_seconds": 100.0,
        "claim_boundary": "schema-1 boundary sentence, verbatim.",
    }
    receipt.update(overrides)
    return receipt


def _write(directory: Path, name: str, receipt: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(json.dumps(receipt), encoding="utf-8")
    return p


def _pilot_summary() -> dict:
    return json.loads(PILOT_SUMMARY.read_text(encoding="utf-8"))


# ── 1. Refusals: the aggregator's teeth ──────────────────────────────────────

def test_undispositioned_above_threshold_hit_is_refused(tmp_path):
    receipt = _schema1_receipt()
    del receipt["targets"][0]["disposition"]
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["targets_searched"] == 0          # excluded from every counter
    assert block["above_threshold"] == 0
    assert block["refused"] and "undispositioned" in block["refused"][0]["reason"]


def test_schema1_missing_injection_block_is_refused(tmp_path):
    receipt = _schema1_receipt()
    del receipt["targets"][0]["injections"]
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["above_threshold"] == 0
    assert any("missing-injection-block" in r["reason"] for r in block["refused"])


def test_a_machine_that_emitted_planet_is_refused_outright(tmp_path):
    """No machine path may emit ``planet`` — a receipt that carries it is not
    counted at all, rather than laundered into the histogram."""
    receipt = _schema1_receipt()
    receipt["targets"][0]["disposition"] = "planet"
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert "planet" not in block["dispositions"]
    assert block["planets_discovered"] == 0
    assert any("machine-emitted-planet" in r["reason"] for r in block["refused"])


def test_unreadable_receipt_is_refused_by_name(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "hunt-2026-08-20-s2.json").write_text("{trunc", encoding="utf-8")
    block = hunt_block(tmp_path)
    assert block["refused"] == [
        {"file": "hunt-2026-08-20-s2.json", "reason": "unreadable"}]


def test_refusal_excludes_but_does_not_sink_the_good_receipt(tmp_path):
    """One bad receipt beside one good one: the good one still aggregates and
    the bad one is named — a refusal is a published fact, not a silent skip."""
    _write(tmp_path, "hunt-2026-08-19-s2.json", _schema1_receipt(
        generated_at="2026-08-19T03:00:00+00:00",
        claim_boundary="the good receipt's boundary."))
    bad = _schema1_receipt()
    del bad["targets"][0]["disposition"]
    _write(tmp_path, "hunt-2026-08-20-s2.json", bad)
    block = hunt_block(tmp_path)
    assert block["above_threshold"] == 1
    assert block["claim_boundary"] == "the good receipt's boundary."
    assert len(block["refused"]) == 1


# ── 2. Counters from rows — a lying summary is caught ────────────────────────

def test_counters_come_from_rows_not_the_receipts_own_counts(tmp_path):
    """The receipt's ``counts`` block claims 40 searched and 7 above threshold;
    its rows show 2 and 1. The hunt block publishes the row-derived truth."""
    receipt = _schema1_receipt(
        counts={"attempted": 40, "searched": 40, "above_threshold": 7,
                "planets_discovered": 3})
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["targets_searched"] == 2
    assert block["above_threshold"] == 1
    assert block["dispositions"] == {"eclipsing-binary-secondary": 1}
    assert block["planets_discovered"] == 0


def test_schema0_lying_declared_total_is_refused(tmp_path):
    """Schema 0 carries only the hit rows, so its searched count is derived
    ``floor.n + hits``; a declared total that disagrees means the receipt is
    lying about one of them and it cannot be honestly counted."""
    receipt = translate_pilot_summary(_pilot_summary())
    receipt["targets_searched"] = 500                      # the lie
    _write(tmp_path, "hunt-2026-08-14-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["targets_searched"] == 0
    assert any("mismatch" in r["reason"] for r in block["refused"])


# ── 3. planets_discovered is pinned ──────────────────────────────────────────

def test_planets_discovered_is_pinned_zero_against_a_hostile_receipt(tmp_path):
    """A receipt that *claims* discoveries in every field a receipt has cannot
    move the number: the block assigns it from a literal, after aggregation."""
    receipt = _schema1_receipt(
        planets_discovered=5,
        counts={"planets_discovered": 5},
    )
    receipt["hunt"] = {"planets_discovered": 5}
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["planets_discovered"] == 0
    # ...and the accepted receipt still counted normally otherwise.
    assert block["above_threshold"] == 1


def test_planets_discovered_zero_even_with_leads_on_the_books(tmp_path):
    """A lead awaiting human review is the machine's TERMINAL state — it counts
    as a lead and never escalates itself into a discovery."""
    receipt = _schema1_receipt()
    receipt["targets"][0]["disposition"] = "lead-awaiting-human-review"
    _write(tmp_path, "hunt-2026-08-20-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["leads_awaiting_human_review"] == 1
    assert block["planets_discovered"] == 0


# ── 4. claim_boundary verbatim + as_of dating ────────────────────────────────

def test_claim_boundary_is_byte_identical_to_the_newest_receipt(tmp_path):
    old = _schema1_receipt(generated_at="2026-08-19T03:00:00+00:00",
                           claim_boundary="the OLD boundary.")
    boundary = ("A newest-receipt boundary — with unicode punctuation "
                "and  double  spaces kept exactly.")
    new = _schema1_receipt(generated_at="2026-08-21T03:00:00+00:00",
                           claim_boundary=boundary)
    _write(tmp_path, "hunt-2026-08-19-s2.json", old)
    _write(tmp_path, "hunt-2026-08-21-s2.json", new)
    block = hunt_block(tmp_path)
    assert block["claim_boundary"] == boundary            # byte-identical
    assert block["as_of"] == "2026-08-21"                 # the newest date
    assert block["last_hunt"]["date"] == "2026-08-21"


# ── 5 + 6. The schema-0 pilot: accepted, labeled, and toi-known-fp ───────────

def test_schema0_pilot_is_accepted_with_pilot_labeling(tmp_path):
    receipt = translate_pilot_summary(_pilot_summary())
    _write(tmp_path, "hunt-2026-08-14-s2-pilot-158.json", receipt)
    block = hunt_block(tmp_path)
    assert "refused" not in block
    assert block["targets_searched"] == 158               # floor.n 153 + 5 hits
    assert block["above_threshold"] == 5
    assert block["known_recovered"] == 0
    assert block["leads_awaiting_human_review"] == 0
    assert block["last_hunt"]["provenance"] == PILOT_PROVENANCE
    assert block["last_hunt"] == {"date": "2026-08-14", "sector": 2, "n": 158,
                                  "wall": receipt["wall_seconds"],
                                  "provenance": PILOT_PROVENANCE}
    assert block["as_of"] == "2026-08-14"


def test_schema0_without_pilot_marker_or_injections_is_refused(tmp_path):
    receipt = translate_pilot_summary(_pilot_summary())
    del receipt["pilot"]
    _write(tmp_path, "hunt-a.json", receipt)
    block = hunt_block(tmp_path)
    assert any("pilot-marker" in r["reason"] for r in block["refused"])
    receipt = translate_pilot_summary(_pilot_summary())
    receipt["injections"] = []
    _write(tmp_path, "hunt-a.json", receipt)
    assert any("run-level-injections" in r["reason"]
               for r in hunt_block(tmp_path)["refused"])


def test_pilot_translation_regrades_the_refuted_candidate():
    """TIC 140940493 held ``planet-candidate`` for forty minutes on 2026-08-14
    and was refuted the same day (δ Scuti-type pulsator; the search latched
    onto its 5th harmonic). The committed schema-0 receipt records what the
    instrument now knows — ``harmonic-alias`` — and keeps the initial verdict
    in the evidence, so neither the mistake nor the correction is lost."""
    receipt = translate_pilot_summary(_pilot_summary())
    row = next(r for r in receipt["targets"] if r["tic"] == "140940493")
    assert row["disposition"] == "harmonic-alias"
    assert row["disposition_evidence"]["initial_verdict"] == "planet-candidate"
    assert row["disposition_evidence"]["pulsation_cpd"] == 8.035


def test_toi_known_fp_reaches_the_histogram_and_is_neither_lead_nor_recovery(tmp_path):
    """The fresh field fact: the 500-target hunt hit TIC 278866211 at SDE 10.3
    and vetting said planet-candidate — but the catalog says TOI 189.01 with
    TFOPWG disposition FP. A community-refuted false positive is NOT a
    recovery and NOT a lead; the translator stamps ``toi-known-fp`` on any
    schema-0 row for that target and the histogram carries it verbatim."""
    summary = _pilot_summary()
    summary["hits"].append({
        "tic": "278866211", "sde": 10.3, "period_days": 2.19516,
        "depth": 0.00379, "phase": 0.5,
        "vetting": {"verdict": "planet-candidate"},
        "catalog": {"known_toi": "TOI 189.01", "disposition": "FP"},
    })
    summary["targets_searched"] += 1                      # keep counts honest
    receipt = translate_pilot_summary(summary)
    row = next(r for r in receipt["targets"] if r["tic"] == "278866211")
    assert row["disposition"] == HUNT_KNOWN_FP
    assert row["disposition_evidence"]["initial_verdict"] == "planet-candidate"

    _write(tmp_path, "hunt-2026-08-14-s2-pilot-500.json", receipt)
    block = hunt_block(tmp_path)
    assert block["dispositions"][HUNT_KNOWN_FP] == 1
    assert block["known_recovered"] == 0                  # an FP is not a recovery
    assert block["leads_awaiting_human_review"] == 0      # ...and not a lead
    assert block["planets_discovered"] == 0


# ── The committed record itself ──────────────────────────────────────────────

def test_the_committed_pilot_receipt_matches_its_committed_source():
    """The receipt in reports/hunts/ is exactly what the translator derives
    from the committed pilot summary — regeneration is byte-stable, so the
    receipt cannot drift from its source without this failing."""
    assert COMMITTED_PILOT.exists(), "the pilot back-fill receipt is missing"
    committed = json.loads(COMMITTED_PILOT.read_text(encoding="utf-8"))
    assert committed == translate_pilot_summary(_pilot_summary())
    assert committed["schema"] == 0
    assert committed["sde_threshold"] == HUNT_SDE_THRESHOLD


def test_pot_json_hunt_block_is_in_sync_with_the_committed_receipts():
    """The same sync rule CI enforces for the milestones key: the committed
    pot.json's ``hunt`` block must equal a fresh aggregation of the committed
    receipts — both are pure functions of files in this repository."""
    pot = json.loads((ROOT / "pot.json").read_text(encoding="utf-8"))
    assert pot.get("hunt") == hunt_block()


def test_committed_hunt_block_headline_numbers():
    """Invariants of the committed ledger, whatever its current numbers.

    Until 2026-08-15 this test pinned the exact headline numbers and the
    windowsill sessions re-pinned it after every hunt. That convention
    predates the campaign + the loam sector split: with two boxes landing
    receipts 4-8x/day, exact pins guaranteed a red main between manual
    re-pins (four reds in the 24h before this rewrite). The numbers are
    data — the receipts and pot.json carry them; what a test can honestly
    hold fixed are the CONTRACT properties below. The one number that
    stays pinned is ``planets_discovered == 0``: flipping it red on a
    claimed discovery is the alarm working as designed."""
    from lab.checks import A05_MACHINE_VOCABULARY
    block = json.loads((ROOT / "pot.json").read_text(encoding="utf-8"))["hunt"]
    # The floor is history: the 2026-08-15 ledger stood at 1,439 searched /
    # 38 above threshold, and receipts only accumulate (a superseding
    # receipt is always the wider one).
    assert block["targets_searched"] >= 1439
    assert block["above_threshold"] >= 38
    # Disposition completeness: every threshold-crossing event carries a
    # machine disposition from the closed vocabulary — none invented,
    # none missing.
    assert set(block["dispositions"]) <= A05_MACHINE_VOCABULARY
    assert all(v > 0 for v in block["dispositions"].values())
    assert sum(block["dispositions"].values()) == block["above_threshold"]
    # An open lead is data, not a defect — but it must agree with its own
    # disposition row, and the community-refuted TOI 189.01 lesson stays.
    assert (block["leads_awaiting_human_review"]
            == block["dispositions"].get("lead-awaiting-human-review", 0))
    assert block["dispositions"].get("toi-known-fp", 0) >= 1
    assert block["known_recovered"] >= 5
    assert block["planets_discovered"] == 0               # THE alarm pin
    assert block["claim_boundary"]                        # verbatim, non-empty
    # as_of / last_hunt mirror the newest accepted receipt, not a constant.
    assert block["as_of"] == block["last_hunt"]["date"]
    assert block["last_hunt"]["n"] >= 1
    # The pilot day's supersession is permanent history: the wide 570-target
    # receipt replaced the 158-target checkpoint, whatever lands later.
    assert {"file": "hunt-2026-08-14-s2-pilot-158.json",
            "by": "hunt-2026-08-14-s2-pilot-570.json"} in block["superseded"]


def test_committed_toi_known_fp_row_is_the_fresh_field_fact():
    """TIC 278866211: SDE 10.3 at P=2.195 d, vetting said planet-candidate, the
    catalog says TOI 189.01 with TFOPWG disposition FP. The committed wide
    receipt carries ``toi-known-fp`` with the initial verdict preserved — a
    validation target for the blend/centroid gates, never a lead."""
    wide = json.loads((HUNTS / "hunt-2026-08-14-s2-pilot-570.json")
                      .read_text(encoding="utf-8"))
    row = next(r for r in wide["targets"] if r["tic"] == "278866211")
    assert row["disposition"] == HUNT_KNOWN_FP
    assert row["known_planet"] is None                    # an FP is nobody's planet
    assert row["disposition_evidence"]["known_toi"] == "189.01"
    assert row["disposition_evidence"]["catalog_disposition"] == "FP"
    assert row["disposition_evidence"]["initial_verdict"] == "planet-candidate"


def test_supersedes_prevents_double_counting(tmp_path):
    """Two receipts where the second's summary is cumulative over the first:
    without the ``supersedes`` link the sum would be 158 + 570 = 728 stars, 570
    of which exist. The superseded receipt stays on the books, named."""
    first = translate_pilot_summary(_pilot_summary())
    _write(tmp_path, "hunt-2026-08-14-s2-pilot-158.json", first)
    # A minimal cumulative second run: the first's floor grows, hits repeat.
    cumulative = _pilot_summary()
    cumulative["targets_searched"] = 200
    cumulative["floor_n"] = 195
    second = translate_pilot_summary(
        cumulative, supersedes="hunt-2026-08-14-s2-pilot-158.json")
    _write(tmp_path, "hunt-2026-08-14-s2-pilot-200.json", second)
    block = hunt_block(tmp_path)
    assert block["targets_searched"] == 200               # not 158 + 200
    assert block["above_threshold"] == 5
    assert block["superseded"] == [{"file": "hunt-2026-08-14-s2-pilot-158.json",
                                    "by": "hunt-2026-08-14-s2-pilot-200.json"}]


def test_a_refused_superseder_cannot_erase_the_receipt_it_names(tmp_path):
    """Only an ACCEPTED receipt's ``supersedes`` link excludes anything: a
    refused receipt claiming to supersede the pilot leaves the pilot counted."""
    first = translate_pilot_summary(_pilot_summary())
    _write(tmp_path, "hunt-2026-08-14-s2-pilot-158.json", first)
    bad = _schema1_receipt(supersedes="hunt-2026-08-14-s2-pilot-158.json")
    del bad["targets"][0]["disposition"]                  # refused
    _write(tmp_path, "hunt-2026-08-20-s2.json", bad)
    block = hunt_block(tmp_path)
    assert block["targets_searched"] == 158               # the pilot still counts
    assert "superseded" not in block
    assert len(block["refused"]) == 1


def test_known_recovered_dedupes_target_and_recovery_mentions(tmp_path):
    """A designated recovery appears BOTH as a target row and in the
    receipt's recoveries list — one star, two mentions, ONE recovery."""
    row = {"tic": "100100827", "outcome": "searched", "sde": 12.0,
           "disposition": "known-planet", "known_planet": "WASP-18 b",
           "injections": [{"depth": 0.002, "period_days": 2.3,
                           "sde": 4.9, "recovered": False}]}
    receipt = _schema1_receipt(
        targets=[row, {"tic": "222", "outcome": "searched", "sde": 5.0}],
        recoveries=[dict(row)],
        counts={"attempted": 2, "searched": 2, "above_threshold": 1})
    _write(tmp_path, "hunt-2026-08-21-s2.json", receipt)
    block = hunt_block(tmp_path)
    assert block["known_recovered"] == 1


def test_serendipitous_known_planets_count_as_recoveries_not_leads():
    """TOI 111.01 (HATS-34 b, KP) and TOI 125.01 (TOI-125 b, CP) surfaced in
    the wide slice and were identified at grading time — ``known-planet``
    dispositions that feed known_recovered and never the lead counter.
    (TOI 125.01 at P≈4.652 d is TOI-125 b; TOI-125 c is the 9.15 d planet.)"""
    wide = json.loads((HUNTS / "hunt-2026-08-14-s2-pilot-570.json")
                      .read_text(encoding="utf-8"))
    known = [r for r in wide["targets"] if r["disposition"] == "known-planet"]
    assert {r["known_planet"] for r in known} == {"HATS-34 b", "TOI-125 b"}
    for row in known:
        assert row["disposition_evidence"]["catalog_disposition"] in ("KP", "CP")


# ── 7. The page: counters, ledger, impostor card, dating, labels ─────────────
# Same style as test_turns' page sweep: static assertions over the shipped
# index.html, because the page is a single committed file and these strings
# are its contract with the feed.

def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_has_the_counter_strip_with_the_correct_terms():
    html = _page()
    for eid in ("hunt-searched", "hunt-events", "hunt-impostors",
                "hunt-known", "hunt-leads", "hunt-planets"):
        assert f'id="{eid}"' in html, f"counter {eid} missing"
    assert "stars searched blind" in html
    # The correct term for what crosses a detection threshold — an event, not
    # a planet and not a candidate.
    assert "threshold-crossing events" in html
    assert "impostors unmasked" in html
    assert "known planets re-found" in html
    assert "leads awaiting human review" in html


def test_page_planets_discovered_zero_is_the_prominent_stat():
    """Honesty as the design centerpiece: the zero renders at the largest size
    on the strip, and its markup defaults to 0 before any feed arrives."""
    html = _page()
    assert '<li class="hunt-zero"><b id="hunt-planets">0</b><span>planets discovered</span></li>' in html
    zero_rule = html.split(".hunt-zero b {", 1)[1].split("}", 1)[0]
    strip_rule = html.split(".hunt-strip b {", 1)[1].split("}", 1)[0]
    def _max_rem(rule):
        import re as _re
        m = _re.search(r"clamp\(([\d.]+)rem[^)]*?([\d.]+)rem\)", rule)
        return float(m.group(2))
    assert _max_rem(zero_rule) > _max_rem(strip_rule), \
        "the zero must be the biggest number on the strip"


def test_page_ledger_is_labeled_machine_disposition_and_renders_verbatim():
    html = _page()
    assert ">machine disposition<" in html
    assert 'id="hunt-dispositions"' in html
    # Verbatim = textContent from the feed's key, no prettifying map.
    assert "name.textContent = verdict;" in html


def test_page_impostors_derive_from_the_histogram_not_by_subtraction():
    """An impostor is an event the machine POSITIVELY unmasked. The counter
    sums disposition buckets and excludes ``low-significance`` (unresolved
    weak signals), ``known-planet``, and the open lead states — the old
    events − known − leads subtraction silently dressed unresolved signals
    up as unmasked impostors."""
    html = _page()
    assert "above - known - leads" not in html, \
        "impostors must come from the dispositions histogram, not subtraction"
    assert "if (verdict === 'low-significance') { unresolved += n; return; }" in html
    assert "verdict === 'known-planet'" in html
    assert "verdict === 'lead-awaiting-human-review'" in html
    # And the unresolved count is surfaced as a ledger note, so the strip's
    # arithmetic (impostors + known + leads + unresolved = events) stays
    # legible to a reader.
    assert 'id="hunt-unresolved"' in html
    assert "never as impostors." in html


def test_page_dates_the_strip_as_of_the_last_published_run_never_live():
    html = _page()
    assert "as of the last published run" in html
    hunt_section = html.split('id="hunt"', 1)[1].split("</section>", 1)[0]
    assert "live" not in hunt_section.lower(), \
        "the hunt section must never claim to be live"


def test_page_impostor_card_tells_the_forty_minutes_story():
    html = _page()
    assert "For forty minutes this was a planet." in html
    # Sourced from the committed pilot data — the numbers are behind a
    # disclosure, and the source receipt is named.
    assert "TIC 140940493" in html
    assert "hunt-2026-08-14-s2-pilot-158.json" in html
    # The 42-event count and the 1.7σ odd/even figure live in the pilot
    # investigation summary, not in the receipt — both sources are named.
    assert "docs/investigations/2026-08-14-a04-discovery-pilot-summary.json" in html
    assert "harmonic-alias" in html


def test_page_renders_claim_boundary_verbatim_from_the_feed():
    html = _page()
    assert 'id="hunt-boundary"' in html
    assert "$('hunt-boundary').textContent = hunt.claim_boundary || '';" in html
    # And the label says exactly where the sentence comes from.
    assert "claim boundary — verbatim from the newest receipt" in html


def test_page_carries_the_classical_math_credit():
    """No AI-washing: the search algorithm is 2002 astronomy, and the page says
    so in one line — the agents run the instrument, the math is classical."""
    html = _page()
    assert "box least squares" in html
    assert "Zucker &amp; Mazeh (2002)" in html
    assert "the math is classical" in html


def test_page_hunt_section_hidden_until_a_feed_arrives_and_wired_to_render():
    html = _page()
    assert '<section class="hunt" id="hunt" hidden' in html
    assert "drawHunt(state.hunt);" in html
    # Graceful degradation: a feed with no hunt block hides the section.
    assert "box.hidden = true; return;" in html


