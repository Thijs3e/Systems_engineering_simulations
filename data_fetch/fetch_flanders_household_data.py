"""
Download the Fluvius household smart-meter dataset (15-min values, full year),
"Zonder zonnepanelen" (without solar panels) group.

This dataset has no queryable table (Fields: []); the data is published as
attached files. This script lists the attachments and downloads the right one.

Run:   python fluvius_download.py            -> lists files, downloads the no-solar one
       python fluvius_download.py 3          -> download attachment number 3 instead
       python fluvius_download.py all        -> download every attachment
Then:  python load_fluvius.py
"""
import os
import sys
import zipfile
from urllib.parse import unquote, urlparse

import requests

DATASET = "1_50-verbruiksprofielen-dm-elek-kwartierwaarden-voor-een-volledig-jaar"
DOMAIN = "https://opendata.fluvius.be"
API = f"{DOMAIN}/api/explore/v2.1/catalog/datasets/{DATASET}"
OUT_DIR = "fluvius_raw"
EXCLUDE = ("warmtepomp", "wp", "voertuig", "ev", "wagen", "laad", "laden", "oplad")


def list_attachments():
    meta = requests.get(API, timeout=30).json()
    print("has_records:", meta.get("has_records"))
    atts = meta.get("attachments") or []
    if not atts:
        r = requests.get(f"{API}/attachments", timeout=30)
        if r.ok:
            atts = r.json().get("attachments", [])
    return meta, atts


def att_title(a):
    m = a.get("metas", a)
    return m.get("title") or m.get("id") or a.get("href", "")


def att_url(a):
    m = a.get("metas", a)
    href = a.get("href") or m.get("url") or ""
    if href and not href.startswith("http"):
        href = DOMAIN + href
    return href


def is_no_solar(title):
    """True for the plain 'zonder zonnepanelen' file, not the heat-pump / EV variants."""
    t = " " + title.lower().replace("_", " ").replace("-", " ").replace(".", " ") + " "
    words = t.split()
    return ("zonder zon" in t or "zonder pv" in t) and not any(
        w in t if len(w) > 3 else w in words for w in EXCLUDE)


def download(url, title):
    os.makedirs(OUT_DIR, exist_ok=True)
    name = os.path.basename(unquote(urlparse(url).path)) or title
    if "." not in name:
        name = title.replace(" ", "_")
    path = os.path.join(OUT_DIR, name)
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        cd = r.headers.get("content-disposition", "")
        if "filename=" in cd:
            path = os.path.join(OUT_DIR, cd.split("filename=")[-1].strip('"; '))
        done = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {done / 1e6:,.0f} MB", end="", flush=True)
    print(f"\n  saved {path}")
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            z.extractall(OUT_DIR)
            print("  unzipped:", z.namelist())
    return path


def main():
    meta, atts = list_attachments()
    if not atts:
        print("\nNo attachments found. Dataset metadata keys:", list(meta.keys()))
        print("Open the dataset page and look for a download link under the 'Information' "
              "or 'Attachments' section:\n"
              f"  {DOMAIN}/explore/dataset/{DATASET}/information/")
        sys.exit(1)

    print("\nAttachments:")
    for i, a in enumerate(atts):
        print(f"  [{i}] {att_title(a)}")

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "all":
        chosen = list(range(len(atts)))
    elif arg is not None:
        chosen = [int(arg)]
    else:
        chosen = [i for i, a in enumerate(atts) if is_no_solar(att_title(a))]
        if len(chosen) != 1:
            print("\nCould not pick the 'Zonder zonnepanelen' file automatically. "
                  "Re-run with its number, e.g.:  python fluvius_download.py 1")
            sys.exit(1)

    for i in chosen:
        print(f"\nDownloading [{i}] {att_title(atts[i])}")
        download(att_url(atts[i]), att_title(atts[i]))
    print(f"\nDone. Point CSV_PATH in load_fluvius.py at the CSV inside '{OUT_DIR}'.")


if __name__ == "__main__":
    main()