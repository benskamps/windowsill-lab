#!/usr/bin/env python3
"""Pull a topic corpus from Crossref — titles + abstracts, polite and resumable.

Written because OpenAlex rate-limited us (429) after an afternoon of PDF
fetching. Crossref's polite pool is generous, keyed on a mailto, and returns
abstracts inline for a large fraction of records. Same three rules: cursor
paging, a real delay, resumable to JSONL.
"""
from __future__ import annotations
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

MAIL="benjamin.schippers@outlook.com"
UA={"User-Agent": f"windowsill-lab/0.1 (mailto:{MAIL})"}
OUT=Path(__file__).resolve().parents[1]/"corpus"
ROWS=200
DELAY=0.8

def get(url, tries=5):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r:
                return json.load(r)
        except Exception as e:
            w=(2**n)*3
            print(f"    [{getattr(e,'code',type(e).__name__)}] wait {w}s", file=sys.stderr, flush=True)
            time.sleep(w)
    raise RuntimeError("gave up")

def clean(s):
    if not s: return ""
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def pull(slug, query, cap=20000):
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f"{slug}.jsonl"
    seen=set()
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try: seen.add(json.loads(line)["doi"])
            except Exception: pass
    cursor="*"; t0=time.time()
    with path.open("a",encoding="utf-8") as fh:
        while cursor and len(seen)<cap:
            u=(f"https://api.crossref.org/works?query={urllib.parse.quote(query)}"
               f"&rows={ROWS}&cursor={urllib.parse.quote(cursor)}"
               f"&select=DOI,title,abstract,published,type,container-title,is-referenced-by-count"
               f"&mailto={MAIL}")
            d=get(u)["message"]
            items=d.get("items",[])
            if not items: break
            for it in items:
                doi=it.get("DOI")
                if not doi or doi in seen: continue
                yr=None
                p=(it.get("published") or {}).get("date-parts") or [[None]]
                if p and p[0]: yr=p[0][0]
                fh.write(json.dumps({
                    "doi":doi,
                    "title":clean((it.get("title") or [""])[0]),
                    "abstract":clean(it.get("abstract")),
                    "year":yr,"type":it.get("type"),
                    "venue":clean((it.get("container-title") or [""])[0]),
                    "cited":it.get("is-referenced-by-count",0)})+"\n")
                seen.add(doi)
            cursor=d.get("next-cursor"); fh.flush()
            print(f"  {slug}: {len(seen):>6,}/{d.get('total-results',0):,}  ({time.time()-t0:.0f}s)", flush=True)
            time.sleep(DELAY)
    return len(seen)

TOPICS={
 # the fringe five
 "lenr":           "cold fusion low energy nuclear reaction excess heat",
 "ball-lightning": "ball lightning",
 "biophotons":     "ultraweak photon emission biophoton",
 "psi":            "parapsychology ganzfeld precognition psi",
 "uap":            "unidentified aerial phenomena",
 # matched mainstream controls — same measurement culture, no controversy
 "electrochem":    "electrochemistry electrode calorimetry electrolysis",
 "supercon":       "superconductivity critical temperature measurement",
}
if __name__=="__main__":
    for slug in (sys.argv[1:] or list(TOPICS)):
        print(f"\n=== {slug} ===",flush=True)
        n=pull(slug,TOPICS[slug], cap=int(__import__("os").environ.get("CAP",6000)))
        print(f"  -> {n:,} records",flush=True)
