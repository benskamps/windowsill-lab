"""Tests for the seed-in-a-pot snapshot builder (stdlib-only, no torch)."""
import json
import os
import pytest
from datetime import date, datetime, timezone

from lab import publish
from lab.publish import build_snapshot, parse_milestones, run_cadence, today_local
from lab.publish import _newest_report


SAMPLE = """
## Phase 1 — verify (we are here)

- [x] **M01** — 2D Ising verification. Reproduce Onsager's M(T) curve, locate T_c via susceptibility peak. (done 2026-06-08 — peak at T=2.30 ± 0.05, Onsager: 2.2692)
- [ ] **M02** — Finite-size scaling: rerun at L = 32, 64, 128, 256, 512 and check collapse.
- [~] **M03** — Specific heat curve C(T). Should diverge. (binning unstable — failed calibration)
- [ ] **M04** — Verify lattice geometries beyond square: triangular (T_c ≈ 3.641).
- [?] **M15** — Domain growth. (attempted 2026-07-07 — n=0.486 from G(r,t), awaiting review)

## Conventions
- Each milestone PR includes the report it generated.
"""


def test_parses_all_milestone_lines_only():
    ms = parse_milestones(SAMPLE)
    assert [m["id"] for m in ms] == ["M01", "M02", "M03", "M04", "M15"]


def test_status_mapping():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M01"]["status"] == "verified"
    assert ms["M02"]["status"] == "open"      # first pending → the open experiment
    assert ms["M03"]["status"] == "null"      # [~] → honest null
    assert ms["M04"]["status"] == "pending"   # later pending stays pending
    assert ms["M15"]["status"] == "review"    # [?] → measured, not promoted


def test_title_is_first_clause():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M01"]["title"] == "2D Ising verification"
    assert ms["M02"]["title"] == "Finite-size scaling"  # split on the colon


def test_a_bold_wrapped_title_is_taken_whole_and_unbolded():
    """An author who bolds the title has already said where it ends.

    The naive first-``.``-or-``:`` split truncates ``**Daido vs Hong: is the
    exponent asymmetric?**`` to ``**Daido vs Hong`` — a title with a dangling
    ``**`` and the question amputated, which then ships to the public feed and
    onto the live page. K03 hit exactly this on 2026-08-05 (the retarget commit
    changed MILESTONES.md without republishing, so the sync gate went red on main
    and the stale title was what kept the malformed one off the site).
    """
    line = ("- [ ] **K03** — **Daido vs Hong: is the susceptibility exponent "
            "asymmetric across K_c?** chi ~ |K - K_c|^(-gamma) above. More prose.")
    ms = {m["id"]: m for m in parse_milestones(line)}
    assert ms["K03"]["title"] == (
        "Daido vs Hong: is the susceptibility exponent asymmetric across K_c?"
    )
    assert "**" not in ms["K03"]["title"]


def test_a_bold_lead_in_that_is_not_the_whole_title_still_splits_normally():
    """Bold used for emphasis on a first word must not swallow the sentence."""
    line = "- [ ] **M99** — **Emphasis** here, then a clause. And later prose."
    ms = {m["id"]: m for m in parse_milestones(line)}
    assert ms["M99"]["title"] == "Emphasis here, then a clause"


def test_verified_result_lifts_parenthetical():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert "peak at T=2.30" in ms["M01"]["result"]
    assert "done" not in ms["M01"]["result"]   # the "done <date> —" prefix is stripped


@pytest.mark.parametrize("separator", [";", ",", "—", "-"])
def test_promoted_result_strips_the_whole_iso_date(separator):
    line = (
        f"- [x] **M18** — Directed percolation. "
        f"(measured 2026-08-07{separator} machine check passed; reviewed)\n"
    )
    result = parse_milestones(line)[0]["result"]
    assert result == "machine check passed; reviewed"
    assert not result.startswith("07")


def test_balanced_result_keeps_nested_physics_notation():
    text = (
        "- [x] **M14** — Nishimori identity. "
        "(done 2026-07-05 — E/N = -2*tanh(1/T) across p in [0.04,0.16])\n"
    )
    result = parse_milestones(text)[0]["result"]
    assert "tanh(1/T)" in result
    assert result.endswith("[0.04,0.16]")


def test_review_result_is_retained_without_becoming_verified():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}["M15"]
    assert ms["status"] == "review"
    assert "G(r,t)" in ms["result"]


# A grey leaf is a miss the lab kept on purpose, and a miss without its numbers
# is indistinguishable from a milestone nobody ran. Until 2026-08-11 the lift ran
# only for verified/review, so every ``[~]`` line's receipt was dropped on the
# floor: M12 and A03 reached the live page carrying a title and nothing else,
# and the field note fell back to the generic "a calibration that missed".
# These fixtures are shaped like the two real lines that were blank.
NULL_SAMPLE = """
- [~] **M12** — 3D EA spin glass. The literature benchmark is T_SG ≈ 1.102 (Hasenbusch–Pelissetto–Vicari 1.1019(29); Katzgraber–Körner–Young 1.120(4)). (code merged 2026-07-01, PR #43 — the quick-CPU calibration ships a null: at L=4,6,8 the multi-L crossing resolves to T_SG≈0.56, so the finite-T crossing does not resolve at CPU scale)
- [~] **A03** — Reprocess one open LIGO/Virgo event from GWOSC. (attempted 2026-08-07 — a controlled null: the injection is recovered at 1.19782 in H1 (error 4.0e-5), but the event itself returns SNR 6.6 against a 10.6 background)
"""


def test_null_result_lifts_the_miss_with_its_numbers():
    """A ``[~]`` receipt reaches the feed exactly like a verified one does."""
    ms = {m["id"]: m for m in parse_milestones(NULL_SAMPLE)}["A03"]
    assert ms["status"] == "null"
    assert "SNR 6.6" in ms["result"]
    assert "1.19782" in ms["result"]
    # The "attempted <date> —" prefix is stripped, as it is for review.
    assert not ms["result"].lower().startswith("attempted")


def test_null_result_keeps_nested_notation_and_skips_the_citation_group():
    """M12's shape: the receipt is the LAST balanced group, not the first.

    Its line opens with a citation parenthetical carrying the literature value,
    and its receipt does not begin with ``attempted``/``measured`` (it begins
    "code merged …"). Picking the first group, or requiring the prefix, would
    publish the benchmark the lab missed as though it were the lab's own number.
    """
    ms = {m["id"]: m for m in parse_milestones(NULL_SAMPLE)}["M12"]
    assert "T_SG≈0.56" in ms["result"]
    assert "Hasenbusch" not in ms["result"]


def test_short_null_receipt_lifts_whole():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M03"]["result"] == "binning unstable — failed calibration"


def test_only_first_pending_is_open():
    statuses = [m["status"] for m in parse_milestones(SAMPLE)]
    assert statuses.count("open") == 1


def test_runner_availability_is_feed_visible():
    ms = {m["id"]: m for m in parse_milestones(SAMPLE)}
    assert ms["M01"]["runner_available"] is True
    assert ms["M15"]["runner_available"] is True
    assert parse_milestones("- [ ] **M16** — Aging memory.\n")[0]["runner_available"] is True
    assert parse_milestones("- [ ] **C01** — Number calibration.\n")[0]["runner_available"] is True
    assert parse_milestones("- [ ] **A01** — TESS calibration.\n")[0]["runner_available"] is True
    assert parse_milestones("- [ ] **I01** — CMOS calibration.\n")[0]["runner_available"] is True
    later = parse_milestones("- [ ] **M17** — KPZ growth.\n")[0]
    assert later["status"] == "open"
    assert later["runner_available"] is True
    # The negative case needs an id that is genuinely NOT in RUNNERS. This line
    # used to say "M18", which was true until M18 got a runner on 2026-08-07 —
    # the same rot that silently turned eleven test_next.py assertions into
    # statements about the wrong thing. Assert the precondition instead of
    # trusting it, so registering M99 fails loudly here rather than quietly
    # inverting what this test checks.
    from lab.curriculum import RUNNERS
    assert "M99" not in RUNNERS, "pick another unregistered id for this assertion"
    assert parse_milestones("- [ ] **M99** — Unregistered.\n")[0]["runner_available"] is False


def test_build_snapshot_shape():
    ms = parse_milestones(SAMPLE)
    snap = build_snapshot(ms, "2026-06-08T00:00:00+00:00", 1, 47.0)
    assert snap["source"] == "windowsill-lab"
    assert snap["total"] == 5
    assert snap["runs"] == 1
    assert snap["temp_c"] == 47.0
    assert snap["last_run"].startswith("2026-06-08")
    assert "updated" in snap
    assert snap["schema_version"] >= 1
    prov = snap["provenance"]
    assert "code_sha" in prov and "env" in prov and isinstance(prov["deps"], dict)


def test_handles_empty_text():
    assert parse_milestones("") == []


# ── The Citizen Science book: letter-prefixed tracks + record tags ──────────
CITIZEN = """
- [x] **M01** — 2D Ising verification. (done 2026-06-08 — Onsager check)
- [x] **C03** — Extend OEIS A000123. (done 2026-08-01 — accepted) {venue=OEIS; url=https://oeis.org/A000123; doi=10.5281/zenodo.123456}
- [ ] **A02** — Recover a variable star and submit. {venue=AAVSO}
- [ ] **I02** — Log cosmic-ray muon candidates for a month. {venue=DECO}
"""


def test_track_is_derived_from_prefix():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["M01"]["track"] == "physics"
    assert ms["C03"]["track"] == "compute"
    assert ms["A02"]["track"] == "astronomy"
    assert ms["I02"]["track"] == "instrument"


# ── Growth forms: the feed contract's render-strategy hint (BACKLOG §Growth forms) ─
# Each milestone carries a `growth_form` *derived from its track*, so the kind of
# science is legible at a glance (a physics convergence sweep ≠ a long astronomy
# time-series ≠ an instrument calibration ≠ a distributed-compute contribution)
# while the rest of the contract stays homogeneous. Derived — not a new field a
# milestone has to set — so existing MILESTONES.md lines gain it for free.

from lab.publish import growth_form_for, GROWTH_FORMS, DEFAULT_GROWTH_FORM


def test_growth_form_for_maps_every_known_track():
    assert growth_form_for("physics") == "fern"
    assert growth_form_for("compute") == "vine"
    assert growth_form_for("astronomy") == "creeper"
    assert growth_form_for("instrument") == "succulent"
    assert growth_form_for("boinc") == "moss"
    assert growth_form_for("misc") == "sprout"


def test_growth_form_for_unknown_or_absent_falls_back_to_default():
    # An unknown track, and an absent (None) one, both degrade to the homogeneous
    # default seedling — the page never has to special-case a form it doesn't know.
    assert growth_form_for("chemistry") == DEFAULT_GROWTH_FORM
    assert growth_form_for(None) == DEFAULT_GROWTH_FORM
    assert DEFAULT_GROWTH_FORM == "sprout"


def test_growth_form_is_derived_from_track_in_parse():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    # The track→form derivation flows straight through parse_milestones.
    assert ms["M01"]["growth_form"] == "fern"        # physics
    assert ms["C03"]["growth_form"] == "vine"        # compute
    assert ms["A02"]["growth_form"] == "creeper"     # astronomy
    assert ms["I02"]["growth_form"] == "succulent"   # instrument


def test_growth_form_present_on_every_milestone():
    # Every parsed milestone gets a growth_form — none is left without one, so the
    # consumer can rely on the field always being present.
    ms = parse_milestones(CITIZEN)
    assert all("growth_form" in m for m in ms)
    # And it agrees with the single source-of-truth derivation rule.
    assert all(m["growth_form"] == growth_form_for(m["track"]) for m in ms)


def test_growth_forms_cover_every_track_value():
    """Homogeneity guard: every track the producer can emit (the TRACKS values
    plus the 'misc' fallback) has a growth form, so no milestone ever falls
    through to a bare default by accident."""
    from lab.publish import TRACKS
    for track in set(TRACKS.values()) | {"misc"}:
        assert track in GROWTH_FORMS, f"track {track!r} has no growth form"


def test_record_tags_are_parsed():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["C03"]["venue"] == "OEIS"
    assert ms["C03"]["url"] == "https://oeis.org/A000123"
    assert ms["C03"]["doi"] == "10.5281/zenodo.123456"


def test_tag_block_stripped_from_title_and_result():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert "{" not in ms["C03"]["title"]
    assert "venue" not in ms["C03"].get("result", "")


def test_tags_flow_on_pending_too():
    ms = {m["id"]: m for m in parse_milestones(CITIZEN)}
    assert ms["A02"]["venue"] == "AAVSO"
    # A02 is the first pending across the sample → promoted to the open experiment
    assert ms["A02"]["status"] == "open"


# ── Explicit open marker + progress: the lab can pick any track as its front ──
EXPLICIT = """
- [x] **M01** — 2D Ising. (done — ok)
- [ ] **M02** — next physics rung.
- [>] **A02** — Recover a variable star and submit. {venue=AAVSO; progress=0.4}
"""


def test_explicit_open_marker_overrides_auto_promotion():
    ms = {m["id"]: m for m in parse_milestones(EXPLICIT)}
    assert ms["A02"]["status"] == "open"      # explicitly marked [>]
    assert ms["M02"]["status"] == "pending"   # NOT auto-promoted while [>] exists


def test_progress_tag_is_parsed_and_clamped():
    ms = {m["id"]: m for m in parse_milestones(EXPLICIT)}
    assert ms["A02"]["progress"] == 0.4
    over = parse_milestones("- [>] **C01** — calibrate. {progress=9}")[0]
    assert over["progress"] == 1.0
    bad = parse_milestones("- [>] **C01** — calibrate. {progress=soon}")[0]
    assert "progress" not in bad


# ── Report dates are LOCAL, and "newest" is by mtime, not date-string ────────
# A report run in the evening should carry the operator's local day, not the
# UTC day (which can already be "tomorrow"). And the *newest* report is the one
# most recently written — never the one whose filename sorts highest. Those two
# facts are coupled: once dates are local, a stale future-dated file (e.g. a
# UTC-dated 06-16 left over from an evening run) must not shadow a fresh 06-15.

def test_today_local_is_the_wall_clock_date():
    assert today_local() == date.today().isoformat()


def _write_report(directory, stem, mtime, **extra):
    """Drop a minimal valid report JSON dated `stem`, stamped at `mtime`.

    Defaults to an M01-shaped Ising χ-sweep; ``extra`` overrides/adds fields
    (e.g. ``experiment=``, ``status=``) so one helper covers every report kind.
    """
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{stem}.json"
    payload = {
        "T": [2.2, 2.3, 2.4],
        "chi": [1.0, 9.0, 1.0],          # peaks at T=2.3
        "wall_seconds": 35.0,
        "headline": f"run {stem}",
    }
    payload.update(extra)
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_newest_report_is_by_mtime_not_lexicographic_date(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # A stale future-dated file written EARLIER, and the real latest run written
    # LATER but with an earlier date string. mtime must win.
    _write_report(lab_home, "2026-06-16", mtime=1000)   # higher date, older write
    _write_report(lab_home, "2026-06-15", mtime=2000)   # lower date, newer write
    rep = _newest_report()
    assert rep["_date"] == "2026-06-15"                  # the truly-newest run


def test_newest_report_breaks_mtime_tie_by_date_stem(tmp_path, monkeypatch):
    """FIX 4: a fresh git clone resets every file mtime to the SAME value, so
    mtime alone leaves "newest" arbitrary. The higher leading date stem must win
    the tie — stable ordering after a clone (mirrors archive.scan_runs)."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # Equal mtimes (the post-clone reality): the higher date stem is the latest.
    _write_report(lab_home, "2026-06-14", mtime=1000)
    _write_report(lab_home, "2026-06-15", mtime=1000)
    rep = _newest_report()
    assert rep["_date"] == "2026-06-15"


def test_latest_report_reconciles_degraded_m01_raw_headline(monkeypatch):
    monkeypatch.setattr(publish, "_newest_report", lambda: {
        "_date": "2026-07-25",
        "experiment": "M01-ising-verification",
        "T": [1.5, 1.6, 2.3],
        "chi": [1900.0, 2.0, 81.0],
        "abs_mag": [0.62, 0.98, 0.65],
        "abs_mag_err": [0.02, 0.001, 0.005],
        "headline": "χ peaked at T≈1.500",
    })
    latest = publish.latest_report()
    assert latest["peak_t"] == 2.3
    assert "T≈2.300" in latest["headline"]
    assert "quality warning" in latest["headline"]


# ── run cadence: derived from the committed receipts, not box-local files ───
# The defect being fixed: run_cadence() counted box-local dated report JSONs
# (gitignored in reports/, private in ~/.lab), so each box published its own
# cadence — this box computed ('2026-07-23', 28) while the committed pot.json
# (from the campaign box) said ('2026-07-30', 24), and the shared receipts
# ledger showed 39 distinct days. Receipts (reports/receipts/run-*.json) are
# committed on every pass, so every clone derives the same numbers.

def _write_receipt(receipts_dir, date, slug="m01", generated_at=None, mtime=None):
    """Drop a minimal receipt named ``run-<date>-<slug>.json``."""
    receipts_dir.mkdir(parents=True, exist_ok=True)
    p = receipts_dir / f"run-{date}-{slug}.json"
    payload = {"experiment": f"{slug.upper()}-test", "T": [2.2], "chi": [1.0]}
    if generated_at is not None:
        payload["generated_at"] = generated_at
    p.write_text(json.dumps(payload), encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def _cadence_dirs(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    receipts = reports / "receipts"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    return reports, receipts, lab_home


def test_run_cadence_ignores_box_local_reports(tmp_path, monkeypatch):
    """The two-box divergence repro: local dated reports (different dates, any
    mtimes) must not move the published cadence — only committed receipts count.
    Negative control for the box-local scan: this test fails against it."""
    reports, receipts, lab_home = _cadence_dirs(tmp_path, monkeypatch)
    _write_receipt(receipts, "2026-07-29", generated_at="2026-07-29T22:31:00+00:00")
    _write_receipt(receipts, "2026-07-30", generated_at="2026-07-30T22:34:12+00:00")
    baseline = run_cadence()
    # Now add box-local dated reports the OTHER box doesn't have — extra days,
    # newer mtimes, a fresher-looking date. Cadence must not change.
    _write_report(lab_home, "2026-07-23", mtime=9_999_999_999)
    _write_report(reports, "2026-07-31", mtime=9_999_999_999)
    assert run_cadence() == baseline
    last_iso, total = baseline
    assert total == 2
    assert last_iso == "2026-07-30T22:34:12+00:00"


def test_run_cadence_last_run_is_newest_receipt_generated_at(tmp_path, monkeypatch):
    """last_run comes from committed content (generated_at), not file mtime —
    a fresh clone resets every mtime, committed stamps survive it."""
    _, receipts, _ = _cadence_dirs(tmp_path, monkeypatch)
    # The higher DATE wins even when an older receipt has a newer mtime (clone).
    _write_receipt(receipts, "2026-07-29", generated_at="2026-07-29T22:31:00+00:00",
                   mtime=9_999_999_999)
    _write_receipt(receipts, "2026-07-30", slug="m01",
                   generated_at="2026-07-30T18:34:00+00:00", mtime=1000)
    _write_receipt(receipts, "2026-07-30", slug="m12",
                   generated_at="2026-07-30T22:34:12+00:00", mtime=500)
    last_iso, total = run_cadence()
    assert total == 2
    assert last_iso == "2026-07-30T22:34:12+00:00"   # max stamp on the max date


def test_run_cadence_counts_distinct_receipt_dates_once(tmp_path, monkeypatch):
    """A day with two milestones (m01 + m12) is one run day, matching the old
    distinct-days contract."""
    _, receipts, _ = _cadence_dirs(tmp_path, monkeypatch)
    _write_receipt(receipts, "2026-07-04", slug="m01")
    _write_receipt(receipts, "2026-07-04", slug="m12")
    _write_receipt(receipts, "2026-07-05", slug="m01")
    _, total = run_cadence()
    assert total == 2


def test_run_cadence_pre_stamp_receipts_fall_back_to_bare_date(tmp_path, monkeypatch):
    """Receipts predating generated_at yield the receipt's date — still committed
    content, so still identical on every clone (mtime would be clone time)."""
    _, receipts, _ = _cadence_dirs(tmp_path, monkeypatch)
    _write_receipt(receipts, "2026-06-14", mtime=9_999_999_999)
    _write_receipt(receipts, "2026-06-15", mtime=1000)
    last_iso, total = run_cadence()
    assert total == 2
    assert last_iso == "2026-06-15"


def test_run_cadence_unreadable_receipt_still_counts_its_date(tmp_path, monkeypatch):
    """A truncated receipt degrades to its filename date — a named, dated entry,
    never a silently skipped day."""
    _, receipts, _ = _cadence_dirs(tmp_path, monkeypatch)
    _write_receipt(receipts, "2026-07-29", generated_at="2026-07-29T22:31:00+00:00")
    receipts.joinpath("run-2026-07-30-m01.json").write_text("{trunc", encoding="utf-8")
    last_iso, total = run_cadence()
    assert total == 2
    assert last_iso == "2026-07-30"


def test_run_cadence_no_receipts_is_none_zero(tmp_path, monkeypatch):
    reports, receipts, lab_home = _cadence_dirs(tmp_path, monkeypatch)
    # Even with local dated reports present: no committed receipts, no cadence.
    _write_report(lab_home, "2026-06-15", mtime=1000)
    assert run_cadence() == (None, 0)


# ── Permanence refactor: slug, run records, discovery, snapshot, backfill ────
# The bug being fixed: render() clobbered a single reports/latest.html every
# run, so milestone reports were buried; latest_report was a single object so
# the page couldn't deep-link history. The fix adds permanent per-run report
# files, a reports[] array in pot.json, and an idempotent backfill().

from lab.publish import (
    _slug_for, _run_record, discover_runs, backfill, SCHEMA_VERSION,
)
from pathlib import Path


def test_schema_version_bumped_to_5():
    # v5: consecutive same-milestone same-verdict runs collapse to the newest
    # row + group_count/group_first_date; the archive index keeps every run.
    assert SCHEMA_VERSION == 5


def test_slug_for_rules():
    assert _slug_for({"experiment": "M02-finite-size-scaling"}) == "m02"
    assert _slug_for({"experiment": "M03-data-collapse"}) == "m03"
    assert _slug_for({"experiment": "M01-ising-verification"}) == "m01"
    # legacy M01 dump: no experiment, but has T + chi
    assert _slug_for({"T": [2.2, 2.3], "chi": [1.0, 9.0]}) == "m01"
    # nothing recognizable
    assert _slug_for({}) == "run"


def test_run_record_shape_for_m01(tmp_path):
    p = _write_report(tmp_path, "2026-06-15", mtime=1000)
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    # The compact record the page consumes.
    assert set(rec) == {
        "date", "milestone", "experiment", "headline",
        "peak_t", "wall_s", "url", "code_sha", "status",
    }
    assert rec["date"] == "2026-06-15"
    assert rec["milestone"] == "M01"
    assert rec["peak_t"] == 2.3            # derived from T/chi peak
    assert rec["wall_s"] == 35.0
    # Honest default: no verdict info → "unscored", never "verified" (FIX 1).
    assert rec["status"] == "unscored"
    assert rec["url"].startswith("http")


def test_run_record_status_null_for_failed_calibration(tmp_path):
    p = _write_report(tmp_path, "2026-06-15", mtime=1000, status="null")
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["status"] == "null"         # a folded grey leaf — honest null


def test_run_record_status_unscored_when_no_verdict_info(tmp_path):
    """The honesty invariant: a run with NO verdict info is "unscored", never
    "verified". ``_run_record`` is the fallback path when the verdict-graded
    archive ledger raises — claim no verification you didn't perform.

    The legacy default labelled any non-null run "verified", so a failed run
    could ride out as a green leaf. It must default to "unscored" instead.
    """
    # A report carrying neither an explicit "null" marker nor any check-derived
    # verdict — the bare structural record can't know it passed.
    p = _write_report(tmp_path, "2026-06-15", mtime=1000)
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["status"] == "unscored"     # NOT "verified" — no verification performed
    # The explicit honest-null marker is still honored.
    p2 = _write_report(tmp_path, "2026-06-14", mtime=900, status="null")
    rec2 = _run_record(p2, json.loads(p2.read_text(encoding="utf-8")))
    assert rec2["status"] == "null"


def test_discover_runs_never_defaults_to_verified(tmp_path, monkeypatch):
    """Through the full discover_runs path: a plain run JSON surfaces as
    "unscored", never "verified" — the fallback can't manufacture a green leaf."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(reports, "2026-06-15-m01", mtime=1000,
                  experiment="M01-ising-verification")
    runs = discover_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "unscored"


def test_run_record_milestone_for_m02(tmp_path):
    p = _write_report(
        tmp_path, "2026-06-16", mtime=1000,
        experiment="M02-finite-size-scaling",
    )
    rec = _run_record(p, json.loads(p.read_text(encoding="utf-8")))
    assert rec["milestone"] == "M02"
    assert rec["experiment"] == "M02-finite-size-scaling"


def test_discover_runs_newest_first_and_deduped(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)

    # Same (date, slug) in BOTH places — repo must win.
    _write_report(lab_home, "2026-06-15-m02", mtime=1000,
                  experiment="M02-finite-size-scaling", headline="lab copy")
    _write_report(reports, "2026-06-15-m02", mtime=900,
                  experiment="M02-finite-size-scaling", headline="repo copy")
    # An older, distinct M01 run only in the repo.
    _write_report(reports, "2026-06-08-m01", mtime=500,
                  experiment="M01-ising-verification", headline="old m01")

    runs = discover_runs()
    # Deduped to two distinct (date, slug) runs.
    assert len(runs) == 2
    # Newest-first by mtime: the m02 run (mtime 1000 in lab) comes first.
    assert runs[0]["date"] == "2026-06-15"
    assert runs[1]["date"] == "2026-06-08"
    # Repo wins the dedupe even though the lab copy had the newer mtime: the
    # record is built from the repo file's content.
    assert runs[0]["headline"] == "repo copy"


def test_discover_runs_matches_legacy_bare_date_names(tmp_path, monkeypatch):
    """A legacy <date>.json (no slug) is still discovered and inferred as M01."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(reports, "2026-06-08", mtime=500)   # legacy bare-date M01 dump
    runs = discover_runs()
    assert len(runs) == 1
    assert runs[0]["date"] == "2026-06-08"
    assert runs[0]["milestone"] == "M01"


def test_build_snapshot_emits_reports_array_and_back_compat_latest():
    r1 = {"date": "2026-06-15", "milestone": "M02", "status": "verified"}
    r2 = {"date": "2026-06-08", "milestone": "M01", "status": "verified"}
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 2, 47.0, reports=[r1, r2])
    assert snap["reports"] == [r1, r2]
    assert snap["latest_report"] == r1     # newest run is the headline


def test_build_snapshot_latest_report_carries_group_fields():
    """v5 grouping rides along harmlessly: latest_report stays the first ledger
    row (its href swapped for the live full report), and the group fields are
    NOT stripped — while the reports[] row itself keeps its archive href."""
    r1 = {"date": "2026-07-24", "milestone": "M01", "verdict": "verified",
          "headline": "peak", "href": "https://example.test/archive#run",
          "receipt_url": None,
          "group_count": 5, "group_first_date": "2026-07-20"}
    r2 = {"date": "2026-07-19", "milestone": "M02", "verdict": "verified",
          "headline": "scaling", "href": "https://example.test/archive#run2",
          "receipt_url": None}
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 2, 47.0,
                          reports_ledger=[r1, r2])
    # Pin the value, not just identity: an in-place mutation of r1 would leave
    # ``snap["reports"][0] == r1`` trivially true, so assert the href itself.
    assert snap["reports"][0]["href"] == "https://example.test/archive#run"
    assert snap["reports"][0] == r1        # ledger row untouched by the override
    latest = snap["latest_report"]
    assert latest["group_count"] == 5
    assert latest["group_first_date"] == "2026-07-20"
    assert latest["href"] == publish.REPORT_URL


def test_build_snapshot_back_compat_without_reports():
    rep = {"date": "2026-06-08", "headline": "legacy single report"}
    snap = build_snapshot(parse_milestones(SAMPLE), "x", 1, 47.0, report=rep)
    # No reports kwarg → legacy single-report behavior preserved.
    assert snap["latest_report"] == rep
    assert snap.get("reports", []) == []


def test_ensure_public_receipts_publishes_compact_evidence(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    receipts = reports / "receipts"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    monkeypatch.setattr(publish, "RECEIPTS_DIR", receipts)
    _write_report(
        lab_home, "2026-06-15-m01", mtime=1000,
        experiment="M01-ising-verification",
        snapshots={"cold": [[1, -1], [-1, 1]]},
    )

    paths = publish.ensure_public_receipts()
    assert paths == [receipts / "run-2026-06-15-m01.json"]
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert data["T"] and data["chi"]
    assert "snapshots" not in data
    assert data["public_receipt"]["omitted"][0]["path"] == "snapshots"

    # Re-running is byte-idempotent.
    before = paths[0].read_bytes()
    assert publish.ensure_public_receipts() == paths
    assert paths[0].read_bytes() == before


def test_lab_cache_is_slug_keyed_no_same_day_collision(tmp_path, monkeypatch):
    """FIX 3: two different milestones run on the SAME day must both survive in
    the ~/.lab dated cache. The old bare ``<date>.json``/``.html`` names let the
    second run clobber the first locally; slug-keyed ``<date>-<slug>.json/.html``
    keeps both, and discovery still finds them."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # Simulate what the renderers now write to ~/.lab on the same day: two
    # distinct milestones, each under its own slug-keyed cache name.
    _write_report(lab_home, "2026-06-15-m02", mtime=1000,
                  experiment="M02-finite-size-scaling", headline="m02 same day")
    _write_report(lab_home, "2026-06-15-m03", mtime=1001,
                  experiment="M03-data-collapse", headline="m03 same day")
    # Both slug-keyed cache files coexist (no clobber).
    assert (lab_home / "2026-06-15-m02.json").exists()
    assert (lab_home / "2026-06-15-m03.json").exists()
    # Discovery finds BOTH same-day runs distinctly.
    runs = discover_runs()
    headlines = {r["headline"] for r in runs}
    assert headlines == {"m02 same day", "m03 same day"}
    assert {r["milestone"] for r in runs} == {"M02", "M03"}


def test_backfill_dry_run_writes_nothing(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    _write_report(lab_home, "2026-06-15", mtime=2000)   # M01-shaped
    _write_report(lab_home, "2026-06-16", mtime=2100,
                  experiment="M02-finite-size-scaling")
    reports.mkdir(parents=True, exist_ok=True)

    planned = backfill(dry_run=True)
    assert len(planned) == 2                            # two reports to create
    # Nothing actually written under reports/.
    assert not list(reports.glob("*.json"))


def test_backfill_is_idempotent(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    # discover_runs uses render dirs too for the URL; keep render writing to tmp.
    pytest.importorskip("matplotlib")  # render (HTML) needs it; CI's lean job skips
    from lab import render
    monkeypatch.setattr(render, "REPO_REPORTS", reports)
    monkeypatch.setattr(render, "LAB_HOME", lab_home)

    src1 = _write_report(lab_home, "2026-06-15", mtime=2000)  # M01
    src2 = _write_report(lab_home, "2026-06-16", mtime=2100,
                         experiment="M02-finite-size-scaling")

    written = backfill()
    # The permanent JSON sidecars now exist in repo reports/.
    assert (reports / "2026-06-15-m01.json").exists()
    assert (reports / "2026-06-16-m02.json").exists()
    assert len(written) >= 2
    # Source ~/.lab files are COPIED, not moved/destroyed — history is preserved.
    assert src1.exists() and src2.exists()

    # A SECOND backfill is a no-op (skip-if-exists).
    again = backfill()
    assert again == []


def test_backfill_renders_m03_reports(tmp_path, monkeypatch):
    """FIX 2c: backfill re-renders M03 reports too, not just M02 — so a
    data-collapse run in ~/.lab lands a permanent reports/<date>-m03.html/.json."""
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)
    pytest.importorskip("matplotlib")  # render (HTML) needs it; CI's lean job skips
    from lab import render
    monkeypatch.setattr(render, "REPO_REPORTS", reports)
    monkeypatch.setattr(render, "LAB_HOME", lab_home)

    # An M03 report cached in ~/.lab with NO sibling HTML — backfill must render it.
    np = pytest.importorskip("numpy")
    from lab.m03 import to_report as m03_to_report, M03Result, M03Curve, T_C, BETA_OVER_NU, INV_NU, NU
    Ls = (16, 24, 32, 48)
    xs = np.linspace(-2.0, 2.0, 24)
    cs = []
    for L in Ls:
        T = T_C + xs * L ** (-INV_NU)
        M = L ** (-BETA_OVER_NU) / (1.0 + np.exp(3.0 * xs))
        cs.append(M03Curve(L=L, T=T.tolist(), M=M.tolist(),
                           M_err=[0.0] * len(T), wall_seconds=1.0))
    rep = m03_to_report(M03Result(
        curves=cs, beta_over_nu_fit=BETA_OVER_NU, inv_nu_fit=1.0,
        collapse_quality=1e-15, tc=float(T_C), beta_over_nu_theory=BETA_OVER_NU,
        nu=NU, wall_seconds=120.0, config={"seed": 42}))
    lab_home.mkdir(parents=True, exist_ok=True)
    (lab_home / "2026-06-16.json").write_text(json.dumps(rep), encoding="utf-8")

    written = backfill()
    assert (reports / "2026-06-16-m03.json").exists()
    assert (reports / "2026-06-16-m03.html").exists()   # re-rendered, not skipped


def test_backfill_preserves_source_mtime(tmp_path, monkeypatch):
    """A backfilled old run must not masquerade as the newest (2026-07-19).

    scan_runs orders newest-first by mtime; backfill used to stamp copies
    with 'now', which pushed weeks-old runs to the top of the public feed.
    """
    import os as _os
    reports = tmp_path / "reports"
    lab_home = tmp_path / "lab"
    lab_home.mkdir(parents=True)
    monkeypatch.setattr(publish, "REPORTS_DIR", reports)
    monkeypatch.setattr(publish, "LAB_HOME", lab_home)

    src = lab_home / "2026-06-14.json"
    src.write_text(
        json.dumps({"experiment": "M01-ising-verification",
                    "T": [2.2, 2.3, 2.4], "chi": [1.0, 9.0, 1.0]}),
        encoding="utf-8",
    )
    old = 1_718_000_000  # 2024-era stamp, clearly not 'now'
    _os.utime(src, (old, old))

    written = publish.backfill()
    dest = next(p for p in written if p.suffix == ".json")
    assert abs(dest.stat().st_mtime - old) < 2
