"""
Print every EAN_ID in a Fluvius CSV (stdlib only, streams the file).

Run:   python print_ean_ids.py [csv_path]   (default: datasources/fluvius_household_data.csv)
"""
import os
import sys

DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "datasources",
                           "fluvius_household_data.csv")
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

ids = set()
with open(CSV_PATH, encoding="utf-8") as f:
    f.readline()  # header
    for line in f:
        ids.add(int(line.split(",", 1)[0]))

ids = sorted(ids)
print(*ids, sep="\n")
print(f"\n{len(ids)} unique EAN_IDs (min {ids[0]}, max {ids[-1]})")
