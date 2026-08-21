"""Is PDCSAP already crowding-corrected?  A direct, falsifiable measurement.

If SPOC's PDC applies the CROWDSAP correction, then for the SAME eclipse
measured through the SAME cadences:

    depth_PDCSAP / depth_SAP  ==  1 / CROWDSAP

because SAP dims by (d_true * CROWDSAP) while PDCSAP, with the constant
contaminating flux removed, dims by d_true.

If PDC does NOT apply it, the ratio is 1.0 and dividing a PDCSAP depth by
CROWDSAP (as a05_physical.companion_radius and a05_vetting.contamination do)
is legitimate.

Controls are the point: run it across a spread of CROWDSAP values and the
predicted ratio must track 1/CROWDSAP over the whole range, not just on the
target of interest.
"""
import math
import sys
import numpy as np

sys.path.insert(0, r"C:\Users\beschipp\projects\windowsill-lab")
from src.lab.a01 import _header, _WIDTH, _DTYPE          # noqa: E402
from src.lab.labhome import CACHE                        # noqa: E402
import re
from pathlib import Path

WANT_COLS = ("TIME", "SAP_FLUX", "PDCSAP_FLUX", "QUALITY")
WANT_HDR = ("CROWDSAP", "FLFRCSAP")
WANT_PRI = ("RADIUS", "TEFF", "LOGG", "TESSMAG")


def read_both(path: Path) -> dict:
    """Same dtype walk as lab.a01, but keeps SAP_FLUX alongside PDCSAP_FLUX."""
    blob = path.read_bytes()
    primary, cursor = _header(blob, 0)
    n_axis = int(primary.get("NAXIS", 0))
    size = 0
    if n_axis:
        size = abs(int(primary.get("BITPIX", 8))) // 8
        for i in range(1, n_axis + 1):
            size *= int(primary.get(f"NAXIS{i}", 0))
        size = size * int(primary.get("GCOUNT", 1)) + int(primary.get("PCOUNT", 0))
    cursor += ((size + 2879) // 2880) * 2880
    table, data_offset = _header(blob, cursor)
    row_size = int(table["NAXIS1"])
    n_rows = int(table["NAXIS2"])
    names, formats, offsets = [], [], []
    byte_offset = 0
    for i in range(1, int(table["TFIELDS"]) + 1):
        name = str(table.get(f"TTYPE{i}", f"FIELD{i}"))
        form = str(table[f"TFORM{i}"]).strip()
        m = re.fullmatch(r"(\d*)([A-Z])", form)
        count, code = int(m.group(1) or 1), m.group(2)
        width = math.ceil(count / 8) if code == "X" else count * _WIDTH[code]
        if code in _DTYPE:
            fmt = np.dtype(_DTYPE[code])
            if count > 1:
                fmt = np.dtype((fmt, (count,)))
            names.append(name); formats.append(fmt); offsets.append(byte_offset)
        byte_offset += width
    dtype = np.dtype({"names": names, "formats": formats,
                      "offsets": offsets, "itemsize": row_size})
    rows = np.ndarray((n_rows,), dtype=dtype, buffer=blob, offset=data_offset)
    out = {c: np.asarray(rows[c]).astype(float) for c in WANT_COLS if c in rows.dtype.names}
    for k in WANT_HDR:
        v = table.get(k)
        out[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    for k in WANT_PRI:
        v = primary.get(k)
        out[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return out


def depth_pair(cur: dict, period: float, half_width=0.012):
    """Depth of the same eclipse in SAP and PDCSAP, through identical cadences."""
    t, q = cur["TIME"], cur["QUALITY"]
    sap, pdc = cur["SAP_FLUX"], cur["PDCSAP_FLUX"]
    ok = (q == 0) & np.isfinite(t) & np.isfinite(sap) & np.isfinite(pdc)
    t, sap, pdc = t[ok], sap[ok], pdc[ok]
    if t.size < 200:
        return None
    sap = sap / np.median(sap)
    pdc = pdc / np.median(pdc)

    ph = ((t - t[0]) / period) % 1.0
    # locate the eclipse from PDCSAP (deepest binned minimum)
    nb = 200
    idx = np.clip((ph * nb).astype(int), 0, nb - 1)
    prof = np.array([np.median(pdc[idx == b]) if np.any(idx == b) else np.nan
                     for b in range(nb)])
    centre = (np.nanargmin(prof) + 0.5) / nb

    d = np.abs(((ph - centre + 0.5) % 1.0) - 0.5)
    intr = d < half_width
    outr = (d > 0.15) & (d < 0.45)
    if intr.sum() < 12 or outr.sum() < 100:
        return None
    res = {"n_in": int(intr.sum()), "n_out": int(outr.sum()), "phase": centre}
    for label, f in (("sap", sap), ("pdc", pdc)):
        base = np.median(f[outr])
        res[f"depth_{label}"] = float(1.0 - np.median(f[intr]) / base)
        res[f"scatter_{label}"] = float(np.std(f[outr]) / math.sqrt(intr.sum()))
    return res


def run(tic, sector_file, period, label=""):
    cur = read_both(sector_file)
    r = depth_pair(cur, period)
    if r is None:
        print(f"  {tic}  — insufficient cadences"); return None
    c = cur["CROWDSAP"]
    ratio = r["depth_pdc"] / r["depth_sap"] if r["depth_sap"] else float("nan")
    pred = 1.0 / c if c else float("nan")
    print(f"  TIC {tic:<11} {label:<9} CROWDSAP={c:.4f}  "
          f"δ_SAP={r['depth_sap']*100:7.4f}%  δ_PDC={r['depth_pdc']*100:7.4f}%  "
          f"ratio={ratio:6.3f}  1/CROWDSAP={pred:6.3f}  "
          f"{'MATCH' if abs(ratio-pred)/pred < 0.15 else ('~1' if abs(ratio-1)<0.15 else 'neither')}")
    return {"tic": tic, "crowdsap": c, "ratio": ratio, "pred": pred, **r,
            "radius": cur["RADIUS"], "tessmag": cur["TESSMAG"], "teff": cur["TEFF"]}


A01 = Path(CACHE) / "a01"
print(__doc__)
print("=" * 108)
print("TARGET OF INTEREST — the last lead standing")
run("77044472", A01 / "tess2018234235059-s0002-0000000077044472-0121-s_lc.fits",
    2.685728750580555, "s2")
run("77044472", A01 / "tess2023237165326-s0069-0000000077044472-0264-s_lc.fits",
    2.685728750580555, "s69")

print()
print("CONTROL — WASP-18 b, a confirmed planet, uncrowded aperture")
for f in sorted(A01.glob("*0000000100100827*_lc.fits"))[:2]:
    run("100100827", f, 0.94145299, f.name.split("-")[1])

print()
print("CONTROLS — the five refuted leads (spread of CROWDSAP)")
refuted = {
    "234518605": 5.672497861382893, "272357134": 4.195947298104868,
    "49558810": 3.3547, "287328866": 1.0380, "369603748": 3.0300,
}
for tic, p in refuted.items():
    for f in sorted(A01.glob(f"*{int(tic):016d}*_lc.fits"))[:1]:
        run(tic, f, p, f.name.split("-")[1])

print()
print("STELLAR PARAMETERS for 77044472 (why the radius gate is disabled)")
for nm, fn in (("s2", "tess2018234235059-s0002-0000000077044472-0121-s_lc.fits"),
               ("s69", "tess2023237165326-s0069-0000000077044472-0264-s_lc.fits")):
    c = read_both(A01 / fn)
    print(f"  {nm}: RADIUS={c['RADIUS']}  TEFF={c['TEFF']}  LOGG={c['LOGG']}  "
          f"TESSMAG={c['TESSMAG']}  CROWDSAP={c['CROWDSAP']}  FLFRCSAP={c['FLFRCSAP']}")
