#!/usr/bin/env python3
"""Pull a whole topic's indexed record to local JSONL — politely, resumably.

Built after being rate-limited (HTTP 429) by hammering the OpenAlex API all
afternoon. Three rules follow from that, and they are the whole design:

* **Cursor paging, 200 at a time.** One request per 200 works, not per work.
* **A real delay and a mailto.** The polite pool is free and generous; the
  anonymous pool is not, and 429 is the API telling you which one you are in.
* **Resumable.** A pull that must complete in one run gets killed by a blip and
  starts from nothing — the same rule the scramble campaign learned.

Abstracts arrive INLINE as an inverted index, so a whole literature's abstracts
cost no PDF fetching at all. That is what makes a 14,000-paper corpus a
two-minute job instead of a two-day one.

For anything past ~10^6 works this is still the wrong tool: OpenAlex publishes
the entire 649M-record database as a free S3 snapshot (330 GB gzipped). This
script is for a topic; the snapshot is for the field.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

MAIL = "benjamin.schippers@outlook.com"
UA = {"User-Agent": f"windowsill-lab/0.1 (mailto:{MAIL})"}
OUT_DIR = Path(__file__).resolve().parents[1] / "corpus"
PER_PAGE = 200
DELAY = 1.1          # polite-pool friendly; 429 is what impatience buys
FIELDS = ("id,doi,title,publication_year,abstract_inverted_index,cited_by_count,"
          "referenced_works,open_access,best_oa_location,type,authorships")


def deinvert(idx) -> str:
    """OpenAlex stores abstracts as {word: [positions]}. Put them back in order."""
    if not idx:
        return ""
    return " ".join(w for _, w in sorted(
        (p, w) for w, ps in idx.items() for p in ps))


def get(url: str, tries: int = 5):
    for n in range(tries):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:                                  # noqa: BLE001
            code = getattr(e, "code", None)
            wait = (2 ** n) * 3
            print(f"    [{code or type(e).__name__}] backing off {wait}s "
                  f"({n+1}/{tries})", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url[:90]}")


def pull(slug: str, query: str, cap: int = 100_000) -> dict:
    out = OUT_DIR / f"{slug}.jsonl"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()
    if out.exists():                       # resume
        with out.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line)["id"])
                except Exception:                               # noqa: BLE001
                    pass
    cursor, wrote, t0 = "*", 0, time.time()
    with out.open("a", encoding="utf-8") as fh:
        while cursor and len(seen) + wrote < cap:
            u = (f"https://api.openalex.org/works?"
                 f"search={urllib.parse.quote(query)}&per-page={PER_PAGE}"
                 f"&cursor={cursor}&select={FIELDS}&mailto={MAIL}")
            d = get(u)
            total = d["meta"]["count"]
            for w in d["results"]:
                if w["id"] in seen:
                    continue
                w["abstract"] = deinvert(w.pop("abstract_inverted_index", None))
                fh.write(json.dumps(w) + "\n")
                seen.add(w["id"])
                wrote += 1
            cursor = d["meta"].get("next_cursor")
            fh.flush()
            print(f"  {slug}: {len(seen):>6,}/{total:,}  ({time.time()-t0:.0f}s)",
                  flush=True)
            if not d["results"]:
                break
            time.sleep(DELAY)
    return {"slug": slug, "query": query, "works": len(seen), "path": str(out)}


TOPICS = {
    "lenr":            "low energy nuclear reaction cold fusion excess heat electrolysis",
    "ball-lightning":  "ball lightning observation model formation",
    "biophotons":      "ultraweak photon emission biophoton biological",
    "psi":             "psi parapsychology ganzfeld precognition meta-analysis",
    "uap":             "unidentified aerial phenomena scientific instrumentation analysis",
}

if __name__ == "__main__":
    want = sys.argv[1:] or list(TOPICS)
    got = []
    for slug in want:
        print(f"\n=== {slug} ===", flush=True)
        got.append(pull(slug, TOPICS[slug]))
    print("\n" + json.dumps(got, indent=1))
