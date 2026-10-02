import csv
import io
import os
import urllib.request
import zipfile
from collections import defaultdict

GEONAMES_ZIP_URL = "https://download.geonames.org/export/zip/US.zip"


def norm_city(name):
    n = (name or "").lower().strip().replace(".", "")
    n = n.replace("saint ", "st ").replace("mount ", "mt ").replace("fort ", "ft ")
    return " ".join(n.split())


def load_city_index(cache_path):
    """
    Returns {(normalized_city, 'ST'): (lat, lon)}.
    Downloads GeoNames US place data once and caches it as a small CSV.
    """
    index = {}
    if not os.path.exists(cache_path):
        print("Downloading US city coordinates (one time only)...")
        try:
            req = urllib.request.Request(GEONAMES_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=120).read()
        except Exception as e:
            print(f"Error downloading city data: {e}")
            return index

        sums = defaultdict(lambda: [0.0, 0.0, 0])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            with z.open("US.txt") as f:
                for line in io.TextIOWrapper(f, encoding="utf-8"):
                    p = line.rstrip("\n").split("\t")
                    if len(p) < 11 or not p[9] or not p[10]:
                        continue
                    key = (norm_city(p[2]), p[4].strip().upper())
                    s = sums[key]
                    s[0] += float(p[9]); s[1] += float(p[10]); s[2] += 1

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for (city, st), (la, lo, n) in sums.items():
                w.writerow([city, st, la / n, lo / n])

    with open(cache_path, newline="", encoding="utf-8") as f:
        for city, st, la, lo in csv.reader(f):
            index[(city, st)] = (float(la), float(lo))
    print(f"City index ready: {len(index)} places.")
    return index


def lookup_city(city_index, city, state):
    return city_index.get((norm_city(city), (state or "").strip().upper()))


def load_stations(csv_path, city_index):
    """
    Reads the fuel CSV (tab or comma separated) and attaches lat/lon to each
    station using the local city index. Stations whose city can't be located are skipped.
    """
    stations, skipped = [], 0
    if not os.path.exists(csv_path):
        print(f"Error: File not found: {os.path.abspath(csv_path)}")
        return stations

    with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
        first = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in first else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        reader.fieldnames = [n.strip() for n in (reader.fieldnames or [])]

        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items() if k}
            try:
                price = float(row.get("Retail Price", ""))
            except ValueError:
                skipped += 1
                continue
            coords = lookup_city(city_index, row.get("City"), row.get("State"))
            if not coords:
                skipped += 1
                continue
            stations.append({
                "id": row.get("OPIS Truckstop ID", ""),
                "name": row.get("Truckstop Name", ""),
                "address": row.get("Address", ""),
                "city": row.get("City", ""),
                "state": row.get("State", ""),
                "price": price,
                "lat": coords[0],
                "lon": coords[1],
            })

    print(f"Loaded {len(stations)} stations ({skipped} skipped: no price or city not found).")
    return stations