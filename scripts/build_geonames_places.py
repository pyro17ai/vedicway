from __future__ import annotations

import argparse
import json
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CITIES_URL = "https://download.geonames.org/export/dump/cities500.zip"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_URL = "https://www.geonames.org/"


def _aliases(name: str, ascii_name: str, raw_aliases: str) -> list[str]:
    result: list[str] = []
    seen = {name.casefold()}
    for candidate in (ascii_name, *raw_aliases.split(",")):
        value = candidate.strip()
        folded = value.casefold()
        if value and folded not in seen:
            seen.add(folded)
            result.append(value)
        if len(result) == 24:
            break
    return result


def _read_rows(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as source:
        return source.read("cities500.txt").decode("utf-8").splitlines()


def build(output: Path, archive: Path | None = None) -> int:
    if archive is not None:
        rows = _read_rows(archive)
    else:
        with tempfile.TemporaryDirectory(prefix="vedicway-geonames-") as temp_dir:
            downloaded = Path(temp_dir) / "cities500.zip"
            urllib.request.urlretrieve(CITIES_URL, downloaded)
            rows = _read_rows(downloaded)

    places: list[dict[str, object]] = []
    for raw in rows:
        fields = raw.split("\t")
        if len(fields) < 19:
            continue
        geoname_id, name, ascii_name, raw_aliases = fields[:4]
        latitude, longitude = fields[4:6]
        country_code = fields[8]
        tzid = fields[17]
        if not geoname_id or not name or not country_code or not tzid:
            continue
        places.append(
            {
                "place_id": f"geonames-{geoname_id}",
                "display_name": f"{name}, {country_code}",
                "country_code": country_code,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "tzid": tzid,
                "alternate_names": _aliases(name, ascii_name, raw_aliases),
            }
        )

    payload = {
        "source": SOURCE_URL,
        "license": "Creative Commons Attribution 4.0",
        "license_url": LICENSE_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "places": places,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return len(places)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the VedicWay local GeoNames registry")
    parser.add_argument("output", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    count = build(
        args.output.resolve(),
        args.archive.resolve() if args.archive is not None else None,
    )
    print(f"Wrote {count} places to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
