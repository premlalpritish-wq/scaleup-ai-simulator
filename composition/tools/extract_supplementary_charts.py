"""Extract the authors' own plotted values from the supplementary Word charts.

    python composition/tools/extract_supplementary_charts.py

The supplementary document (``mmc1.docx``) embeds two native OOXML charts
(``word/charts/chart1.xml``, ``chart2.xml``). A Word chart stores the numbers it
plots in ``<c:numCache>`` inside the chart XML. Those are the values the authors
entered into their plotting tool -- not a reading off a rendered raster, and not a
digitisation.

That distinction is the whole point: the existing evaluation dataset was digitised
from the published figures by a program in this repository, and carries a reading
uncertainty that follows from doing so. Anything recovered here carries no such
uncertainty, because no reading step happened.

This tool only extracts and records. It does not transform, resample, re-unit, or
interpret anything, and it never touches the frozen evaluation dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "data" / "ganjave2022" / "source_data"
PACKAGE = SOURCE_DIR / "PMC8718739_supplementary.zip"
DOCX = SOURCE_DIR / "mmc1_supplementary.docx"
OUT = ROOT / "data" / "ganjave2022" / "source_data" / "supplementary_charts.json"

CHART_PARTS = ("word/charts/chart1.xml", "word/charts/chart2.xml")

POINT = re.compile(r'<c:pt\s+idx="(\d+)"[^>]*>\s*<c:v>([^<]*)</c:v>', re.S)


def numeric(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def series_name(series_xml: str) -> str:
    block = re.search(r"<c:tx>.*?</c:tx>", series_xml, re.S)
    if not block:
        return ""
    values = re.findall(r"<c:v>([^<]*)</c:v>", block.group(0))
    return values[-1] if values else ""


def axis_titles(chart_xml: str) -> list[str]:
    """Axis titles, which carry the units the authors plotted against."""
    titles: list[str] = []
    for block in re.findall(r"<c:title>.*?</c:title>", chart_xml, re.S):
        parts = re.findall(r"<a:t>([^<]*)</a:t>", block)
        if parts:
            titles.append("".join(parts))
    return titles


def chart_titles(chart_xml: str) -> list[str]:
    titles = re.findall(r"<c:title>.*?</c:title>", chart_xml, re.S)
    out = []
    for block in titles:
        parts = re.findall(r"<a:t>([^<]*)</a:t>", block)
        if parts:
            out.append("".join(parts))
    return out


def categories(series_xml: str) -> list[float | None]:
    block = re.search(r"<c:cat>.*?</c:cat>", series_xml, re.S)
    if not block:
        return []
    return [numeric(v) for _, v in POINT.findall(block.group(0))]


def values(series_xml: str) -> list[float | None]:
    block = re.search(r"<c:val>.*?</c:val>", series_xml, re.S)
    if not block:
        return []
    return [numeric(v) for _, v in POINT.findall(block.group(0))]


def chart_of(document: zipfile.ZipFile, part: str) -> dict[str, Any]:
    raw = document.read(part)
    text = raw.decode("utf-8", errors="replace")

    chart: dict[str, Any] = {
        "chart_part": part,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "titles": chart_titles(text),
        "axis_titles": axis_titles(text),
        "series": [],
    }

    for index, series_xml in enumerate(re.findall(r"<c:ser>.*?</c:ser>", text, re.S)):
        cats = categories(series_xml)
        vals = values(series_xml)
        points = []
        for position in range(max(len(cats), len(vals))):
            t = cats[position] if position < len(cats) else None
            v = vals[position] if position < len(vals) else None
            if t is None and v is None:
                continue
            points.append({"index": position, "x": t, "y": v})
        chart["series"].append({
            "series_index": index,
            "name": series_name(series_xml),
            "n_points": len(points),
            "points": points,
        })
    return chart


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not DOCX.exists() or not PACKAGE.exists():
        print(
            f"{DOCX.name} and {PACKAGE.name} are absent.\n"
            f"Recover them from Europe PMC:\n"
            f"  https://www.ebi.ac.uk/europepmc/webservices/rest/PMC8718739/supplementaryFiles\n"
            f"See reports/GANJAVE_SOURCE_DATA_RECOVERY.md for the full provenance."
        )
        return 1

    document = zipfile.ZipFile(DOCX)
    available = [p for p in CHART_PARTS if p in document.namelist()]
    if not available:
        print("the supplementary document contains no OOXML chart parts")
        return 1

    charts = [chart_of(document, part) for part in available]

    payload = {
        "record_id": "ganjave2022.supplementary_charts",
        "version": "1.0.0",
        "data_class": (
            "authors' plotted values, as stored in the supplementary document's "
            "native charts. These are the numbers entered into a plotting tool by "
            "the authors. They are NOT a digitisation, and they carry no reading "
            "uncertainty, because no reading step occurred."
        ),
        "provenance": {
            "article_doi": "10.1016/j.btre.2021.e00694",
            "pmcid": "PMC8718739",
            "publisher_supplementary_file": "mmc1.docx",
            "obtained_from": (
                "https://www.ebi.ac.uk/europepmc/webservices/rest/"
                "PMC8718739/supplementaryFiles"
            ),
            "package": PACKAGE.name,
            "package_sha256": hashlib.sha256(PACKAGE.read_bytes()).hexdigest(),
            "docx_sha256": hashlib.sha256(DOCX.read_bytes()).hexdigest(),
            "licence": (
                "CC BY-NC-ND 4.0, as stated for the article. The file is stored "
                "unmodified; no derivative of it is redistributed."
            ),
        },
        "extraction": {
            "method": (
                "OOXML charts store plotted values in <c:numCache> as <c:pt> "
                "elements. Values are read verbatim: no smoothing, interpolation, "
                "unit conversion or resampling is applied."
            ),
            "preserves": "the authors' own units as plotted; no axis relabelling",
        },
        "charts": charts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}")
    for chart in charts:
        print(f"\n  {chart['chart_part']}  ({chart['size_bytes']} bytes)")
        print(f"    titles     : {chart['titles']}")
        print(f"    axis titles: {chart['axis_titles']}")
        for series in chart["series"]:
            print(f"    series {series['series_index']} "
                  f"'{series['name']}'  n={series['n_points']}")
            for point in series["points"][:12]:
                print(f"        x={point['x']!s:<10} y={point['y']}")
            if series["n_points"] > 12:
                print(f"        ... {series['n_points'] - 12} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
