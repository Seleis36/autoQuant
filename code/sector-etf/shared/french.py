"""Ken French 49-industry portfolios, mapped onto the 11 SPDR (GICS) sectors.

Source: mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/49_Industry_Portfolios_CSV.zip
(CRSP-based, monthly, 1926-07 onward). Cached as
  data/FF49_industries_vw_m.parquet   value-weighted monthly returns (decimal)
  data/FF49_industries_cap_m.parquet  number of firms x average firm size ($M) at t
Sector proxy return = cap-weighted mean of its mapped industries, weights lagged one
month. The mapping is approximate (French uses SIC, SPDRs use GICS) -- it is used only as a
*signal* source estimated over decades, never as a traded return.

Point-in-time: the file is published with a ~2 month lag; any signal built from it must
only read months that ended >= 2 months before the decision date (`lag_months`).
"""
import io
import os
import sys
import zipfile
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
DATA = os.path.join(_ROOT, "data")
URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/49_Industry_Portfolios_CSV.zip"

MAP = {
    "XLP": ["Agric", "Food", "Soda", "Beer", "Smoke", "Hshld"],
    "XLY": ["Toys", "Clths", "Txtls", "Autos", "Rtail", "Meals", "PerSv"],
    "XLV": ["Hlth", "MedEq", "Drugs"],
    "XLB": ["Chems", "Rubbr", "BldMt", "Steel", "Gold", "Mines", "Paper", "Boxes"],
    "XLI": ["Cnstr", "FabPr", "Mach", "ElcEq", "Aero", "Ships", "Guns", "Trans", "Whlsl", "BusSv"],
    "XLE": ["Coal", "Oil"],
    "XLU": ["Util"],
    "XLC": ["Telcm", "Fun", "Books"],
    "XLK": ["Hardw", "Softw", "Chips", "LabEq"],
    "XLF": ["Banks", "Insur", "Fin"],
    "XLRE": ["RlEst"],
}


def _block(lines, title):
    i = next(k for k, l in enumerate(lines) if l.strip().startswith(title))
    hdr = [h.strip() for h in lines[i + 1].split(",")[1:]]
    rows = []
    for l in lines[i + 2:]:
        p = l.split(",")
        if len(p) < 2 or not p[0].strip().isdigit():
            break
        rows.append([p[0].strip()] + [float(x) for x in p[1:]])
    df = pd.DataFrame(rows, columns=["ym"] + hdr).set_index("ym")
    df.index = pd.to_datetime(df.index, format="%Y%m") + pd.offsets.MonthEnd(0)
    return df.replace([-99.99, -999.0], np.nan)


def fetch(force=False):
    pr = os.path.join(DATA, "FF49_industries_vw_m.parquet")
    pc = os.path.join(DATA, "FF49_industries_cap_m.parquet")
    if os.path.exists(pr) and not force:
        return
    import urllib.request
    raw = urllib.request.urlopen(URL, timeout=60).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    txt = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    ret = _block(txt, "Average Value Weighted Returns -- Monthly") / 100.0
    nf = _block(txt, "Number of Firms in Portfolios")
    sz = _block(txt, "Average Firm Size")
    ret.to_parquet(pr)
    (nf * sz).to_parquet(pc)


def sector_returns():
    fetch()
    ret = pd.read_parquet(os.path.join(DATA, "FF49_industries_vw_m.parquet"))
    cap = pd.read_parquet(os.path.join(DATA, "FF49_industries_cap_m.parquet")).shift(1)
    out = {}
    for s, inds in MAP.items():
        r = ret[inds]; w = cap[inds].where(r.notna())
        out[s] = (r * w).sum(axis=1) / w.sum(axis=1)
    return pd.DataFrame(out)
