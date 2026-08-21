"""Is this 'candidate' actually a known planet on a star bleeding into the aperture?

The gate the pipeline is missing. `disposition_evidence.catalog` queries the
TARGET TIC only, and a blended planet is by construction filed under a different
TIC. Run this for any lead whose CROWDSAP says foreign flux dominates.
"""
import csv, io, math, sys, warnings
import requests
from astroquery.mast import Catalogs
warnings.filterwarnings("ignore")

TOI_URL = "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv"


def neighbours(tic, radius_arcsec=60.0):
    t = Catalogs.query_criteria(catalog="Tic", ID=int(tic))[0]
    n = Catalogs.query_region("%s %s" % (t["ra"], t["dec"]),
                              radius=radius_arcsec / 3600.0, catalog="Tic")
    n.sort("dstArcSec")
    t0 = float(t["Tmag"])
    out = []
    for row in n:
        try:
            rel = 10 ** (-0.4 * (float(row["Tmag"]) - t0))
        except (TypeError, ValueError):
            continue
        out.append({"tic": str(row["ID"]), "sep_as": float(row["dstArcSec"]),
                    "tmag": float(row["Tmag"]), "flux_rel": rel,
                    "sep_px": float(row["dstArcSec"]) / 21.0})
    return t, out


def toi_table():
    text = requests.get(TOI_URL, timeout=180).text
    rows = list(csv.DictReader(io.StringIO(text)))
    return {str(r["TIC ID"]).strip(): r for r in rows if r.get("TIC ID")}


def crosscheck(tic, period_days, tol_frac=0.01, harmonics=(1, 2, 3, 4)):
    target, near = neighbours(tic)
    tois = toi_table()
    print(f"TIC {tic}  T={float(target['Tmag']):.3f}  detection P={period_days:.9f} d")
    print(f"{'TIC':>12} {'sep_as':>7} {'sep_px':>7} {'Tmag':>7} {'flux_rel':>9}  TOI / disposition")
    for nb in near:
        row = tois.get(nb["tic"])
        note = "-"
        if row:
            try:
                p = float(row["Period (days)"])
                hit = next((f"n={h}" for h in harmonics
                            for cand in (p * h, p / h)
                            if abs(cand - period_days) / period_days < tol_frac), None)
            except (TypeError, ValueError):
                p, hit = float("nan"), None
            note = (f"TOI {row['TOI']}  {row['TFOPWG Disposition']}  P={p:.7f}"
                    f"  {'** PERIOD MATCH ' + hit + ' **' if hit else ''}"
                    f"  {row.get('Comments','').strip()}")
        print(f"{nb['tic']:>12} {nb['sep_as']:>7.2f} {nb['sep_px']:>7.2f} "
              f"{nb['tmag']:>7.3f} {nb['flux_rel']:>9.3f}  {note}")


if __name__ == "__main__":
    tic = sys.argv[1] if len(sys.argv) > 1 else "77044472"
    per = float(sys.argv[2]) if len(sys.argv) > 2 else 2.685728750580555
    crosscheck(tic, per)
