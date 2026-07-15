#!/usr/bin/env python3
"""
geocode.py — Offline city geocoder for the vedic-astrology skill.

Resolves a city name (e.g. "Mumbai", "New Delhi", "London") to latitude,
longitude, and IANA timezone so callers do not have to supply coordinates by
hand. Fully offline: it reads a bundled CSV (data/cities.csv) derived from the
GeoNames cities15000 dataset (CC-BY 4.0). No runtime network, no API keys.

Usage:
    python geocode.py "Mumbai" [--country IN] [--limit 5] [--json]

The dataset keeps every Indian city with population > 15,000 plus all world
cities with population > 100,000, sorted by population so the most prominent
match wins ties. See ../data/cities.csv and the repository NOTICE file.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional

# Path to the bundled dataset, resolved relative to THIS file so the script
# works regardless of the caller's current working directory.
_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "cities.csv"
)


def _load_cities(path: str = _DATA_PATH) -> List[dict]:
    """Load the bundled city dataset into a list of dicts (pop-sorted desc).

    Raises FileNotFoundError if the dataset is missing.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"city dataset not found at {path}")
    cities: List[dict] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cities.append({
                "name": row["name"],
                "asciiname": row["asciiname"],
                "country": row["country"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "timezone": row["timezone"],
                "population": int(row["population"]),
            })
    return cities


def geocode(
    query: str,
    country: Optional[str] = None,
    limit: int = 5,
) -> List[dict]:
    """Look up cities matching ``query``, best match first.

    Matching is case-insensitive against both the localized name and the
    ASCII name. Ranking, best first:
      0 — exact name match
      1 — name starts with the query
      2 — query appears anywhere in the name
    Within each rank, higher population wins (the dataset is already sorted by
    population descending, so we keep that order). If ``country`` (an ISO-2
    code such as "IN") is given, results are filtered to that country.

    Returns up to ``limit`` dicts with keys: name, country, lat, lon,
    timezone, population. An empty list means no match.
    """
    q = query.strip().lower()
    if not q:
        return []
    cc = country.strip().upper() if country else None

    cities = _load_cities()
    scored: List[tuple] = []
    for c in cities:
        if cc and c["country"] != cc:
            continue
        name_l = c["name"].lower()
        ascii_l = c["asciiname"].lower()
        if name_l == q or ascii_l == q:
            rank = 0
        elif name_l.startswith(q) or ascii_l.startswith(q):
            rank = 1
        elif q in name_l or q in ascii_l:
            rank = 2
        else:
            continue
        scored.append((rank, c))

    # Stable sort by rank only; equal-rank ties preserve the pop-desc order
    # already present in the dataset.
    scored.sort(key=lambda t: t[0])

    out: List[dict] = []
    for _, c in scored[: max(0, limit)]:
        out.append({
            "name": c["name"],
            "country": c["country"],
            "lat": c["lat"],
            "lon": c["lon"],
            "timezone": c["timezone"],
            "population": c["population"],
        })
    return out


def render_text(matches: List[dict]) -> str:
    """Format matches as a numbered, human-readable list."""
    lines = []
    for i, m in enumerate(matches, start=1):
        lines.append(
            f"  {i}. {m['name']}, {m['country']} — "
            f"lat {m['lat']:.4f}, lon {m['lon']:.4f}, "
            f"tz {m['timezone']} (pop {m['population']:,})"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Offline city geocoder (lat/lon/timezone).")
    ap.add_argument("query", help="City name to look up, e.g. \"Mumbai\"")
    ap.add_argument("--country", default=None, help="Filter to an ISO-2 country code, e.g. IN")
    ap.add_argument("--limit", type=int, default=5, help="Max matches to return (default 5)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        matches = geocode(args.query, country=args.country, limit=args.limit)
    except Exception as e:  # noqa: BLE001 — surface a clean message to the agent
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not matches:
        print(f"ERROR: no city matching '{args.query}' found", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        print(render_text(matches))


if __name__ == "__main__":
    main()
