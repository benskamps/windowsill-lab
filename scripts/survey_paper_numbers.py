"""Re-derive every number the survey paper prints, from the committed receipts.

The paper in ``docs/papers/2026-09-18-survey-methods-draft.md`` states a census
(how many stars were searched, how many crossed threshold, how many leads the
survey's own gates took away). A paper is a static document; the receipts in
``reports/hunts/`` are the record. This script is the seam between them: it
reads the receipts and prints the census, so a reader — or a referee, or a
future session about to edit a sentence — can check the prose against the
bytes without re-reading the aggregator.

It is a READER. It re-executes no search, fits nothing, and writes nothing
outside its own stdout. Every figure is derived here from the receipt rows;
none is copied from a receipt's own ``counts`` block, and none is copied from
``pot.json``. Where this script and ``lab.publish.hunt_block`` compute the same
quantity they are asserted equal at the bottom of the output, because two
readers of one record that can silently disagree are worse than one.

Three numbers here are deliberately NOT the ones the earlier outline carried,
and the differences are the point:

* ``targets_searched`` (12,898) is a count of target-SEARCHES, not of stars.
  The aggregator sums it per receipt on purpose — re-searching a star in a
  later slice really is more work — but a survey's denominator is stars. The
  distinct-identity count is printed beside it.
* The disposition vocabulary has 19 terms. 14 of them were used. A paper that
  says "a closed 14-term vocabulary" has described the sample, not the
  contract.
* Seven refutation rulings are on the record; five of them count against a
  currently-minted lead. The other two are not missing, and the reason each
  one dropped out is printed.

Usage::

    python scripts/survey_paper_numbers.py            # the census
    python scripts/survey_paper_numbers.py --json     # the same, machine-readable
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from lab import publish                       # noqa: E402
from lab.a05_vocab import MACHINE_DISPOSITIONS  # noqa: E402

#: The ladder's own "this host is blind" bar: a host that cannot recover a 1.0 %
#: injection at any ladder period is barred from aggregate sensitivity claims.
#: Mirrors lab.a05_sensitivity's predeclared top rung; stated here so the
#: census says which bar it counted against.
INSENSITIVE_DEPTH = 0.01


def census(hunts_dir: Path | None = None) -> dict:
    """The paper's numbers, every one re-derived from receipt rows."""
    directory = hunts_dir if hunts_dir is not None else publish.HUNTS_DIR
    accepted, refused, superseded = publish._accepted_hunt_receipts(directory)

    searches = 0             # per-receipt counter SUM: work done
    row_identities: set[str] = set()
    floor_only = 0           # pilot stars counted by a floor, identities unrecorded
    attempted = skipped = errored = 0
    stage2 = 0
    injections = recovered = 0
    d_min_hosts: set[str] = set()
    blind_hosts: set[str] = set()
    placebo_scrambles = placebo_candidates = 0
    control_members = 0
    ks_stats: list[float] = []
    graded_faps: list[float] = []
    pooled_nulls: list[dict] = []
    sectors: dict[str, int] = {}

    # Star-level ledger, newest verdict winning — the same walk hunt_block does.
    star_disposition: dict[str, str] = {}
    star_known: dict[str, str] = {}
    lead_sde: dict[str, float] = {}

    for _, _, receipt in sorted(accepted, key=lambda item: (item[0], item[1].name)):
        counters = publish._hunt_receipt_counters(receipt)
        searches += counters["targets_searched"]
        searched_rows, above = publish._receipt_target_rows(receipt)
        if receipt.get("schema", 0) == 0:
            floor_only += (receipt.get("floor") or {}).get("n", 0)
        sector = str(receipt.get("sector"))
        sectors[sector] = sectors.get(sector, 0) + counters["targets_searched"]

        all_rows = [r for r in receipt.get("targets", []) if isinstance(r, dict)]
        attempted += len(all_rows)
        skipped += sum(1 for r in all_rows if r.get("outcome") == "skipped-no-product")
        errored += sum(1 for r in all_rows
                       if str(r.get("outcome", "")).startswith("error"))

        extras = [r for r in (receipt.get("recoveries") or []) if isinstance(r, dict)]
        for row in all_rows + extras:
            if row.get("stage2"):
                stage2 += 1
            for shot in (row.get("injections") or []):
                injections += 1
                recovered += bool(shot.get("recovered"))
            limits = row.get("d_min") or {}
            if limits:
                tic = str(row.get("tic"))
                d_min_hosts.add(tic)
                floors = [v for v in limits.values() if v is not None]
                if not floors or min(floors) >= INSENSITIVE_DEPTH:
                    blind_hosts.add(tic)
            graded = (row.get("fap") or {}).get("fap_graded")
            if graded is not None:
                graded_faps.append(float(graded))

        placebo = receipt.get("placebo") or {}
        placebo_scrambles += placebo.get("n_scrambled") or 0
        placebo_candidates += placebo.get("planet_candidates") or 0
        uniformity = receipt.get("uniformity") or {}
        if uniformity.get("ks_stat") is not None:
            ks_stats.append(float(uniformity["ks_stat"]))
            control_members += uniformity.get("n_control") or 0
        pooled = receipt.get("pooled_null")
        if pooled:
            pooled_nulls.append(pooled)

        for row in searched_rows:
            row_identities.add(str(row.get("tic")))
        above_tics = {str(r.get("tic")) for r in above}
        for row in searched_rows:
            tic = str(row.get("tic"))
            if tic not in above_tics:
                star_disposition.pop(tic, None)
        for row in above:
            tic = str(row.get("tic"))
            star_disposition[tic] = row["disposition"]
            if row["disposition"] == publish.HUNT_KNOWN_FP:
                star_known.pop(tic, None)
            if row["disposition"] in publish.HUNT_LEAD_STATES:
                lead_sde[tic] = row.get("sde")
        for row in above + extras:
            if row.get("known_planet") and row.get("disposition") != publish.HUNT_KNOWN_FP:
                star_known[str(row.get("tic"))] = str(row.get("known_planet"))

    dispositions: dict[str, int] = {}
    for verdict in star_disposition.values():
        dispositions[verdict] = dispositions.get(verdict, 0) + 1

    leads = {tic for tic, v in star_disposition.items()
             if v in publish.HUNT_LEAD_STATES}
    rulings = publish._shelf_states(hunts_dir)
    counted = sorted(t for t, v in rulings.items() if v == "refuted" and str(t) in leads)
    uncounted = sorted(t for t, v in rulings.items()
                       if v == "refuted" and str(t) not in leads)
    parked = sorted(t for t, v in rulings.items() if v == "parked" and str(t) in leads)

    pooled = pooled_nulls[0] if pooled_nulls else None
    expected_false = None
    if pooled and pooled.get("fap_at_threshold_upper") is not None:
        expected_false = searches * float(pooled["fap_at_threshold_upper"])

    return {
        "receipts": {
            "accepted": len(accepted),
            "refused": refused,
            "superseded": superseded,
        },
        "sample": {
            "target_searches": searches,
            "distinct_identities_in_rows": len(row_identities),
            "pilot_floor_stars_without_identities": floor_only,
            "rows_attempted": attempted,
            "rows_skipped_no_product": skipped,
            "rows_errored": errored,
            "searches_by_sector": dict(sorted(sectors.items(),
                                              key=lambda kv: -kv[1])),
        },
        "detections": {
            "above_threshold_stars": len(star_disposition),
            "sde_threshold": publish.HUNT_SDE_THRESHOLD,
            "dispositions": dict(sorted(dispositions.items(), key=lambda kv: -kv[1])),
            "vocabulary_terms_defined": len(MACHINE_DISPOSITIONS),
            "vocabulary_terms_used": len(dispositions),
            "undispositioned": sum(1 for v in star_disposition.values() if not v),
        },
        "statistics": {
            "stage2_rows": stage2,
            "graded_faps": len(graded_faps),
            "graded_fap_floor": min(graded_faps) if graded_faps else None,
            "graded_fap_median": statistics.median(graded_faps) if graded_faps else None,
            "pooled_null": pooled,
            "expected_false_crossings_over_sample": expected_false,
        },
        "controls": {
            "injections_run": injections,
            "injections_recovered": recovered,
            "ladder_hosts": len(d_min_hosts),
            "hosts_barred_as_insensitive": len(blind_hosts),
            "placebo_scrambles": placebo_scrambles,
            "placebo_planet_candidates": placebo_candidates,
            "uniformity_control_members": control_members,
            "uniformity_receipts": len(ks_stats),
            "uniformity_ks_max": max(ks_stats) if ks_stats else None,
        },
        "outcomes": {
            "known_planets_recovered": len(star_known),
            "recoveries": dict(sorted(star_known.items(), key=lambda kv: kv[1])),
            "leads_minted": len(leads),
            "leads_refuted_and_counted": counted,
            "refutations_not_counted": uncounted,
            "leads_parked": parked,
            "leads_awaiting_human_review": sorted(
                leads - set(map(str, counted)) - set(map(str, parked))),
            "lead_sde": {k: lead_sde[k] for k in sorted(lead_sde)},
            "planets_claimed": 0,
        },
    }


def _agrees_with_aggregator(numbers: dict, hunts_dir: Path | None = None) -> list[str]:
    """Where this reader and ``lab.publish.hunt_block`` disagree, by name."""
    block = publish.hunt_block(hunts_dir)
    if block is None:
        return ["hunt_block returned None"]
    checks = {
        "targets_searched": numbers["sample"]["target_searches"],
        "above_threshold": numbers["detections"]["above_threshold_stars"],
        "known_recovered": numbers["outcomes"]["known_planets_recovered"],
        "leads_minted": numbers["outcomes"]["leads_minted"],
        "leads_refuted": len(numbers["outcomes"]["leads_refuted_and_counted"]),
        "leads_parked": len(numbers["outcomes"]["leads_parked"]),
        "planets_discovered": numbers["outcomes"]["planets_claimed"],
    }
    return [f"{key}: this reader {mine!r} vs hunt_block {block.get(key)!r}"
            for key, mine in checks.items() if block.get(key) != mine]


def _render(n: dict) -> str:
    out: list[str] = []
    w = out.append
    s, d, st, c, o = (n["sample"], n["detections"], n["statistics"],
                      n["controls"], n["outcomes"])
    w("THE SAMPLE")
    w(f"  target-searches (sum of work)      {s['target_searches']:,}")
    w(f"  distinct identities in rows        {s['distinct_identities_in_rows']:,}")
    w(f"  pilot stars counted by a floor     {s['pilot_floor_stars_without_identities']:,}"
      "   (identities not individually recorded)")
    w(f"  rows attempted                     {s['rows_attempted']:,}")
    w(f"  rows with no usable product        {s['rows_skipped_no_product']:,}")
    w(f"  rows that errored                  {s['rows_errored']:,}")
    w(f"  receipts accepted / refused        {n['receipts']['accepted']} / "
      f"{len(n['receipts']['refused'])}")
    for row in n["receipts"]["refused"]:
        w(f"      refused: {row['file']}  ({row['reason']})")
    w("")
    w("WHAT CROSSED THRESHOLD")
    w(f"  above SDE {d['sde_threshold']}                      {d['above_threshold_stars']} stars")
    w(f"  dispositioned                      "
      f"{d['above_threshold_stars'] - d['undispositioned']}"
      f" / {d['above_threshold_stars']}")
    w(f"  vocabulary                         {d['vocabulary_terms_used']} terms used of "
      f"{d['vocabulary_terms_defined']} defined")
    for term, count in d["dispositions"].items():
        w(f"      {term:<34} {count}")
    w("")
    w("THE STATISTIC")
    w(f"  Stage-2 rows (paid the bootstrap)  {st['stage2_rows']:,}")
    w(f"  graded FAPs recorded               {st['graded_faps']:,}")
    w(f"  graded FAP floor at B=256          {st['graded_fap_floor']:.6g}"
      "   (the bound (1+0)/(B+1); no lead can grade below it)")
    if st["pooled_null"]:
        p = st["pooled_null"]
        w(f"  pooled scramble null               {p.get('draws'):,} draws, "
          f"max SDE {p.get('max_sde'):.3f}")
        w(f"      threshold below that max?      {p.get('threshold_below_null_max')}")
        w(f"      per-target FAP at threshold    <= {p.get('fap_at_threshold_upper'):.3g} "
          f"({p.get('fap_bound_confidence')} confidence)")
        w(f"      implied false crossings        ~{st['expected_false_crossings_over_sample']:.2f}"
          " over the whole sample, if that null describes it")
    w("")
    w("THE CONTROLS")
    w(f"  injections run / recovered         {c['injections_run']:,} / "
      f"{c['injections_recovered']:,}")
    w(f"  hosts with a measured depth limit  {c['ladder_hosts']:,}")
    w(f"  hosts barred as insensitive        {c['hosts_barred_as_insensitive']:,}"
      f"   (cannot see a {INSENSITIVE_DEPTH:.0%} transit at any ladder period)")
    w(f"  placebo scrambles / candidates     {c['placebo_scrambles']:,} / "
      f"{c['placebo_planet_candidates']}")
    w(f"  uniformity control members         {c['uniformity_control_members']:,} over "
      f"{c['uniformity_receipts']} receipts, max KS {c['uniformity_ks_max']:.3f}")
    w("")
    w("WHAT CAME OUT")
    w(f"  known planets recovered            {o['known_planets_recovered']}")
    for tic, name in o["recoveries"].items():
        w(f"      {name:<14} TIC {tic}")
    w(f"  leads minted                       {o['leads_minted']}")
    w(f"  refuted by the survey's own gates  {len(o['leads_refuted_and_counted'])}"
      f"   {', '.join(o['leads_refuted_and_counted'])}")
    w(f"  parked on a named gap              {len(o['leads_parked'])}"
      f"   {', '.join(o['leads_parked'])}")
    w(f"  awaiting human review              {len(o['leads_awaiting_human_review'])}"
      f"   {', '.join(o['leads_awaiting_human_review'])}")
    w(f"  refutation rulings NOT counted     {len(o['refutations_not_counted'])}"
      f"   {', '.join(o['refutations_not_counted'])}")
    w("      (a ruling counts only while its star is a currently-minted lead:")
    w("       one lead left the ledger when its receipt was refused by the controls,")
    w("       one when a later sector re-dispositioned the star.)")
    w(f"  planets claimed                    {o['planets_claimed']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true",
                        help="emit the census as JSON instead of prose")
    parser.add_argument("--hunts", type=Path, default=None,
                        help="a directory of hunt receipts (default: reports/hunts)")
    args = parser.parse_args(argv)

    numbers = census(args.hunts)
    disagreements = _agrees_with_aggregator(numbers, args.hunts)

    if args.json:
        print(json.dumps({"census": numbers, "disagreements": disagreements},
                         indent=2, sort_keys=True))
    else:
        print(_render(numbers))
        print("")
        if disagreements:
            print("DISAGREES WITH lab.publish.hunt_block:")
            for line in disagreements:
                print(f"  {line}")
        else:
            print("Agrees with lab.publish.hunt_block on every shared counter.")
    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
