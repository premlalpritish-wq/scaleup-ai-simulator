"""Independent pixel check of the digitised marks, straight from the source PDF.

    python composition/tools/verify_digitisation.py

The digitisation in ``Models/Ganjave/data/figure_reference_data.json`` classified the
paper's raster figures by colour. This re-extracts the figure image from the PDF and
asks a narrower question the digitisation cannot answer about itself:

    for each digitised mark, what colour is actually at that pixel, and does it match
    the colour of the series the mark was assigned to?

A mark assigned to PDGF whose pixel is a different series' colour is a misassignment.
A mark whose pixel matches PDGF everywhere, including on a physically impossible
decline, means the figure really does show that and the discrepancy is in the model,
not in the reading.

It also reports the colour immediately above and below each mark, so a mark sitting on
the edge of a band can be distinguished from one sitting in the middle of it.

This reads the PDF. It is a manual diagnostic, not a test: the reference PDFs are not
distributed, so nothing in ``tests/`` may depend on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "papers" / "Ganjave et al 2022.pdf"
REFERENCE = ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"
OUT = ROOT / "data" / "ganjave2022" / "investigation" / "digitisation_pixel_check.json"

#: PDF page index that carries printed page 6, where Fig. 3 and its caption are.
FIG3_PAGE = 5


def rgb_at(image, x: float, y: float) -> tuple[int, int, int]:
    xi, yi = int(round(x)), int(round(y))
    xi = max(0, min(image.size[0] - 1, xi))
    yi = max(0, min(image.size[1] - 1, yi))
    return tuple(image.getpixel((xi, yi))[:3])


def brightness_band(image, cx: float, cy: float, width: int = 3) -> tuple[tuple[int, int, int], ...]:
    """Colours in a small vertical window through the curve, top to bottom.

    A mark on a curve sits in a band of its own colour; an artefact or an
    annotation usually does not.
    """
    out: list[tuple[int, int, int]] = []
    for dy in range(-width, width + 1):
        out.append(rgb_at(image, cx, cy + dy))
    return tuple(out)


def dominant(colours: tuple[tuple[int, int, int], ...]) -> tuple[int, int, int]:
    counts: dict[tuple[int, int, int], int] = {}
    for colour in colours:
        counts[colour] = counts.get(colour, 0) + 1
    return max(counts, key=lambda c: counts[c])


def classify_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def main() -> int:
    if not PDF.exists():
        print(f"{PDF} is absent (reference PDFs are not distributed). "
              f"Nothing to check.")
        return 0

    from PIL import Image
    import pypdf

    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    panel = reference["figures"]["5"]["panels"]["b"]
    calibration = panel["calibration"]
    frame = calibration["frame_px"]

    reader = pypdf.PdfReader(str(PDF))
    images = list(reader.pages[FIG3_PAGE].images)
    if not images:
        print(f"no image on PDF page {FIG3_PAGE}; cannot check")
        return 0

    def to_pixel(t: float, v: float) -> tuple[float, float]:
        x = calibration["x_pixel_at_min"] + calibration["px_per_x_unit"] * t
        y = calibration["y_pixel_at_min"] - calibration["px_per_y_unit"] * v
        return x, y

    report: dict = {
        "check_id": "ganjave2022.digitisation_pixel_check",
        "version": "1.0.0",
        "pdf": str(PDF.relative_to(ROOT)),
        "pdf_page_index": FIG3_PAGE,
        "panel": "figure_reference_data.json figures['5'] panel 'b' (paper Fig. 3b)",
        "images_on_page": [
            {"name": im.name, "size": list(im.image.size)} for im in images
        ],
        "frame_px": frame,
        "series": {},
        "marks": [],
        "note": (
            "Manual diagnostic. The reference PDF is not distributed, so no test "
            "may depend on this file."
        ),
    }

    # Which image does the calibration describe?
    target = None
    for im in images:
        w, h = im.image.size
        if frame["x"][1] < w and frame["y"][1] < h:
            target = im
            break
    if target is None:
        report["error"] = (
            f"no image on the page contains the calibrated frame {frame}"
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"no image matches the frame {frame}")
        return 1

    image = target.image.convert("RGB")
    report["image_used"] = {"name": target.name, "size": list(image.size)}

    # Establish each series' colour from the samples we are confident about: the
    # leftmost, least ambiguous part of the run, where every culture is rising.
    series_colours: dict[str, tuple[int, int, int]] = {}
    for name, series in panel["series"].items():
        samples = [
            s for s in series.get("samples", [])
            if 4.0 <= s["t_h"] <= 6.0 and s.get("value") is not None
            and isinstance(s.get("value"), (int, float))
        ]
        if not samples:
            continue
        colours = []
        for sample in samples:
            x, y = to_pixel(sample["t_h"], sample["value"])
            colours.extend(brightness_band(image, x, y, width=1))
        if colours:
            series_colours[name] = dominant(tuple(colours))
    report["series"] = {
        name: {"rgb": list(colour)} for name, colour in series_colours.items()
    }
    print("series colours sampled from the rising phase (t = 4-6 h):")
    for name, colour in sorted(series_colours.items(), key=lambda kv: kv[1]):
        print(f"  {name:<16} rgb{colour}")

    # Now check every digitised mark of the PDGF biomass series.
    pdgf = panel["series"]["PDGF"]
    pdgf_colour = series_colours.get("PDGF")
    for mark in pdgf.get("marks", []):
        x, y = to_pixel(mark["t_h"], mark["value"])
        band = brightness_band(image, x, y, width=2)
        found = dominant(band)
        nearest, distance = None, None
        for name, colour in series_colours.items():
            d = classify_distance(found, colour)
            if distance is None or d < distance:
                nearest, distance = name, d
        report["marks"].append({
            "observation_id": f"fig3b:PDGF:{len(report['marks'])}",
            "t_h": mark["t_h"],
            "digitised_value_g_per_L": mark["value"],
            "ink_px": mark["ink_px"],
            "pixel_xy": [round(x, 2), round(y, 2)],
            "dominant_colour_at_pixel": list(found),
            "nearest_series": nearest,
            "colour_distance_to_nearest": round(distance, 2) if distance else None,
            "colour_distance_to_PDGF": (
                round(classify_distance(found, pdgf_colour), 2) if pdgf_colour else None
            ),
            "matches_assigned_series": (
                nearest == "PDGF" if nearest is not None else None
            ),
        })

    # The curve around the disputed region, to see whether the figure itself declines.
    report["curve_near_dispute"] = [
        {
            "t_h": round(s["t_h"], 3),
            "digitised_value_g_per_L": s["value"],
            "rgb": list(dominant(brightness_band(
                image, *to_pixel(s["t_h"], s["value"]), width=1))),
        }
        for s in pdgf.get("samples", [])
        if 22.0 <= s["t_h"] <= 26.5
        and s.get("value") is not None and isinstance(s.get("value"), (int, float))
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\nper-mark colour check (PDGF biomass series):")
    for mark in report["marks"]:
        flag = "" if mark["matches_assigned_series"] else "   <-- NOT PDGF"
        print(f"  t={mark['t_h']:7.3f}  v={mark['digitised_value_g_per_L']:8.4f}  "
              f"rgb{tuple(mark['dominant_colour_at_pixel'])}  "
              f"nearest={mark['nearest_series']:<14} "
              f"d(PDGF)={mark['colour_distance_to_PDGF']}{flag}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
