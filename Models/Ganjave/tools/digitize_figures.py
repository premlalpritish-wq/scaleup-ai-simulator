"""Digitise the raster figures of Ganjave et al. (2022) into reference data.

    python tools/digitize_figures.py --pdf ../papers/"Ganjave et al 2022.pdf" \
        --out data/figure_reference_data.json

The paper's time courses are figures, not numerical data, so any quantitative
comparison needs them read off the page.  This script does that reading, and it
is deliberately mechanical about it, because a digitisation that depends on
someone's eye is not evidence.

**How a panel is calibrated.**  The axis frame is found from the long black
spine rules, never from hand-entered pixel coordinates.  The axis *tick labels*
are then located as text blocks just outside the frame, and matplotlib centres
a label on its tick, so a label's bounding-box centre along the axis is the
tick position and is measurable to a fraction of a pixel.  The scale is fitted
over all labels -- so one mis-measured glyph cannot dominate -- and the offset
is anchored on the axis minimum at the frame edge, where no glyph sits to bias
the reading.  The disagreement between the label-derived scale and the
frame-edge-anchored scale is reported as the calibration uncertainty, in data
units, over the whole axis span.

**How a series is identified.**  By hue, never by position.  A channel
*difference* is tested, because an axis-aligned box in RGB also accepts grey:
a grey of (96,96,96) satisfies 70<=r<=200, 0<=g<=130, 70<=b<=215 and would
otherwise be read as purple.  Experimental marks are saturated blobs; model
predictions are the purple line.  Legend boxes are detected as rectangles with
all four borders drawn, so a legend's sample marker cannot be read as a datum.

**What is not done.**  Nothing is read off a curve by eye, and no value is
invented where a curve is unreadable.  Where a rasterised column holds several
branches of a trace (a steep segment, or two segments crossing) the point is
marked `ambiguous` rather than averaged.  Where a curve coincides with an axis
spine it is not separately resolved, and that is recorded as a span limit.

Figures 2, 3 and 5 are digitised.  Figure 2 is the *fitting* experiment -- the
parameters were tuned against it -- so it is extracted for completeness and
recorded as non-independent.  Only Figures 3 and 5 carry evidence that could
support or contradict the implementation.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import pymupdf
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pymupdf is required to extract the figure rasters") from exc

#: How far left of the left spine tick labels are read from, and how close to the
#: spine.  The rotated axis *title* sits further left than this band, so it
#: cannot be mistaken for a tick label.
Y_BAND_INSET = 40
Y_BAND_END = 5

PDF_XREFS = {
    # printed page index -> (xref, width, height)
    4: (63, 1750, 1195),
    5: (89, 1800, 1230),
    6: (101, 1800, 1230),
}


# --------------------------------------------------------------------------- #
# low-level pixel machinery
# --------------------------------------------------------------------------- #


def runs(flags: np.ndarray, merge_gap: int):
    """Index runs of True, bridging gaps up to `merge_gap`."""
    idx = np.flatnonzero(flags)
    if idx.size == 0:
        return []
    out, start = [], idx[0]
    for i in range(1, idx.size):
        if idx[i] - idx[i - 1] > merge_gap:
            out.append((int(start), int(idx[i - 1])))
            start = idx[i]
    out.append((int(start), int(idx[-1])))
    return out


def find_labels(mask: np.ndarray, axis: str, band, merge_gap: int, min_ink: int = 12):
    """Tick-label blocks in `band`; returns [(centre, extent, ink)] along the axis."""
    strip = mask[band] if isinstance(band, tuple) else mask[band]
    present = strip.any(axis=0) if axis == "x" else strip.any(axis=1)
    out = []
    for a, b in runs(present, merge_gap):
        block = strip[:, a:b + 1] if axis == "x" else strip[a:b + 1, :]
        ink = float(block.sum())
        if ink < min_ink:
            continue
        out.append(((a + b) / 2.0, b - a + 1, ink))
    return out


def linfit(values, positions):
    """Least-squares `position = a*value + b`; returns (a, b, max_residual)."""
    v = np.asarray(values, dtype=float)
    p = np.asarray(positions, dtype=float)
    if v.size < 2:
        return None, None, None
    a, b = np.polyfit(v, p, 1)
    resid = p - (a * v + b)
    return float(a), float(b), float(np.max(np.abs(resid)))


def calibrate_panel(dark, height, frame, x_values, y_values):
    """Calibrate one panel from its tick labels.

    `frame` is ``(x0, x1, y0, y1)`` in pixels; `x_values` are the labelled
    major ticks left to right and `y_values` top to bottom (pixel rows grow
    downward while axis values grow upward).

    Returns ``(record, None)``, or ``(None, reason)`` when the labels found do not
    match the number expected -- which is a calibration failure, not a reason to
    guess at the missing labels.
    """
    x0, x1, y0, y1 = frame
    xmin, xmax = float(x_values[0]), float(x_values[-1])
    ymin, ymax = float(y_values[-1]), float(y_values[0])

    x_labels = find_labels(
        dark, "x", (slice(y1 + 8, min(height, y1 + 46)), slice(x0 - 4, x1 + 4)),
        merge_gap=40,
    )
    y_labels = find_labels(
        dark, "y", (slice(y0, y1 + 1), slice(max(0, x0 - Y_BAND_INSET), x0 - Y_BAND_END)),
        merge_gap=6,
    )
    if len(x_labels) != len(x_values):
        return None, (
            f"found {len(x_labels)} x labels, expected {len(x_values)}: "
            f"{[round(c + x0 - 4, 1) for c, _w, _n in x_labels]}"
        )
    if len(y_labels) != len(y_values):
        return None, (
            f"found {len(y_labels)} y labels, expected {len(y_values)}: "
            f"{[round(c + y0, 1) for c, _w, _n in y_labels]}"
        )

    x_centres = [c + x0 - 4 for c, _w, _n in x_labels]
    y_centres = [c + y0 for c, _w, _n in y_labels]

    ax, bx, rx = linfit(x_values, x_centres)
    ay, by, ry = linfit(y_values, y_centres)

    ax_edge = (x1 - x0) / (xmax - xmin)
    ay_edge = (y1 - y0) / (ymax - ymin)
    x_disc = abs(abs(ax) - ax_edge) * (xmax - xmin)
    y_disc = abs(abs(ay) - ay_edge) * (ymax - ymin)

    return {
        "frame_px": {"x": [x0, x1], "y": [y0, y1]},
        "xlim": [xmin, xmax], "ylim": [ymin, ymax],
        "x_label_centres_px": [round(c, 2) for c in x_centres],
        "y_label_centres_px": [round(c, 2) for c in y_centres],
        "px_per_x_unit": abs(ax),
        "px_per_y_unit": abs(ay),
        "x_pixel_at_min": bx,
        "y_pixel_at_min": by,
        "x_label_fit_residual_px": rx,
        "y_label_fit_residual_px": ry,
        "px_per_x_unit_edge_anchored": ax_edge,
        "px_per_y_unit_edge_anchored": ay_edge,
        "x_span_discrepancy_px": x_disc,
        "y_span_discrepancy_px": y_disc,
        "x_calibration_uncertainty": x_disc / abs(ax),
        "y_calibration_uncertainty": y_disc / abs(ay),
    }, None


# --------------------------------------------------------------------------- #
# colour classification
# --------------------------------------------------------------------------- #
#
# A channel *difference* is what separates a hue from a grey, so that is what is
# tested.  An RGB box also accepts grey, which would let a black axis spine be
# read as a series.


def _blue(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (b >= 170) & (b - np.maximum(r, g) >= 100) & (r <= 130) & (g <= 130)


def _green(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (g >= 140) & (g - r >= 30) & (g - b >= 80) & (r >= 80)


def _red(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (r >= 180) & (r - g >= 150) & (r - b >= 180) & (g <= 60)


def _dark_orange(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (r >= 150) & (r - g >= 100) & (r - b >= 160) & (g >= 60) & (g <= 120)


def _orange(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (r >= 150) & (np.abs(r - g) <= 45) & (b <= 100)


def _purple(image):
    r, g, b = (image[:, :, i].astype(int) for i in range(3))
    return (
        (b - g >= 60)
        & (r - g >= 40)
        & (np.abs(r - b) <= 70)
        & (b >= 110)
        & (g <= 110)
    )


EXPERIMENTAL_MASKS = {
    "PDGF": _blue,
    "FDH": _green,
    "G_Can_ADH": _red,
    "L_Kefir_ADH": _dark_orange,
    "EYFP": _orange,
}
MODEL_MASKS = {"Model_predicted": _purple}


def find_legend_boxes(mask, min_w=150, min_h=25, max_h=240):
    """Rectangular legend boxes, found by testing for all four borders.

    A legend's sample marker is the most likely way a digitisation goes wrong,
    so its box is excluded.  Boxes are detected as rectangles with all four
    sides drawn, rather than by guessing a corner region, which would fail on a
    panel whose legend sits elsewhere.
    """
    h, w = mask.shape
    candidates = []
    for r in range(h):
        for a, b in runs(mask[r], merge_gap=4):
            if b - a >= min_w:
                candidates.append((r, a, b))
    boxes = []
    for i, (r1, a1, b1) in enumerate(candidates):
        for (r2, a2, b2) in candidates[i + 1:]:
            if not (min_h <= r2 - r1 <= max_h):
                continue
            if abs(a1 - a2) > 6 or abs(b1 - b2) > 6:
                continue
            left = mask[r1:r2 + 1, (a1 + a2) // 2]
            right = mask[r1:r2 + 1, (b1 + b2) // 2]
            if left.all() and right.all():
                boxes.append((r1, r2, min(a1, a2), min(b1, b2)))
    boxes = sorted(set(boxes), key=lambda t: -(t[1] - t[0]) * (t[3] - t[2]))
    kept = []
    for box in boxes:
        if not any(box[0] >= k[0] and box[1] <= k[1] and box[2] >= k[2]
                   and box[3] <= k[3] for k in kept):
            kept.append(box)
    return kept[:4]


def mask_components(mask, min_ink):
    """Connected components of a boolean mask (4-connected flood fill)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            stack, pix = [(sy, sx)], []
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                pix.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(pix) >= min_ink:
                out.append(pix)
    return out


# --------------------------------------------------------------------------- #
# series extraction
# --------------------------------------------------------------------------- #


def extract_trace(mask, sub, to_x, to_y, px_y, min_pixels=3):
    """One reading per pixel column: the median row of the series' pixels.

    A dissolved-oxygen trace is single-valued in time, so a column holds one
    reading plus the line's own thickness.  The median is robust to another
    series crossing underneath it.
    """
    out = []
    for col in range(mask.shape[1]):
        rows = np.flatnonzero(mask[:, col])
        if rows.size < min_pixels:
            continue
        out.append({
            "t_h": round(to_x(col + sub[1].start), 4),
            "value": round(to_y(float(np.median(rows)) + sub[0].start), 4),
            "spread": round(float(rows.max() - rows.min()) / px_y, 4),
        })
    return out


def interpolate(trace, times):
    """Read a trace at requested times by linear interpolation.

    A rasterised curve has columns only where the line happened to land, so
    requiring a column within a time window leaves gaps that are artefacts of the
    raster and not of the data.  Interpolating between the bracketing readings
    removes them; the reading's own spread is still reported.
    """
    usable = [p for p in trace if p.get("value") is not None]
    if not usable:
        return [{"t_h": t, "value": None, "reason": "no trace pixels"} for t in times]
    spans = np.array([p["spread"] for p in usable])
    typical = float(np.median(spans))
    tv = np.array([p["t_h"] for p in usable])
    vv = np.array([p["value"] for p in usable])
    out = []
    for t in times:
        if t < tv[0] - 1e-9 or t > tv[-1] + 1e-9:
            out.append({
                "t_h": t, "value": None,
                "reason": f"outside readable span {tv[0]:.2f}..{tv[-1]:.2f} h",
            })
            continue
        i = int(np.clip(np.searchsorted(tv, t), 0, len(tv) - 1))
        entry = {
            "t_h": t,
            "value": round(float(np.interp(t, tv, vv)), 4),
            "spread": round(float(spans[min(i, len(spans) - 1)]), 4),
        }
        if entry["spread"] > 3.0 * typical:
            entry["ambiguous"] = (
                f"a column here spans {entry['spread']:.3f} units against a typical "
                f"trace thickness of {typical:.3f}; the figure cannot resolve a "
                f"single reading at this time"
            )
        out.append(entry)
    return out


def digitize_panel(image, dark, frame, x_values, y_values, series_masks,
                   grid, xlabel, ylabel):
    """Calibrate one panel and extract every series in it."""
    x0, x1, y0, y1 = frame
    calib, error = calibrate_panel(dark, image.shape[0], frame, x_values, y_values)
    if calib is None:
        return {"skipped": error}

    conv = {
        "to_x": lambda px: calib["xlim"][0] + (px - calib["x_pixel_at_min"]) / calib["px_per_x_unit"],
        "to_y": lambda py: calib["ylim"][0] + (calib["y_pixel_at_min"] - py) / calib["px_per_y_unit"],
        "px_y": calib["px_per_y_unit"],
    }
    sub = (slice(y0 - 6, y1 + 7), slice(x0 - 6, x1 + 7))
    masks = {label: fn(image[sub]) for label, fn in series_masks.items()}
    boxes = find_legend_boxes(dark[sub])
    for (bt, bb, bl, br) in boxes:
        for m in masks.values():
            m[bt:bb + 1, bl:br + 1] = False

    panel = {
        "axes": {"x": xlabel, "y": ylabel,
                 "xlim": calib["xlim"], "ylim": calib["ylim"]},
        "calibration": calib,
        "legend_boxes_px": boxes,
        "series": {},
    }

    mark_times = []
    for label, mask in masks.items():
        marks = []
        for pix in mask_components(mask, min_ink=40):
            ys = np.array([p[0] for p in pix]) + sub[0].start
            xs = np.array([p[1] for p in pix]) + sub[1].start
            cx, cy = float(xs.mean()), float(ys.mean())
            half = max(1.0, (ys.max() - ys.min() + 1) / 2.0,
                       (xs.max() - xs.min() + 1) / 2.0)
            marks.append({
                "t_h": round(conv["to_x"](cx), 3),
                "value": round(conv["to_y"](cy), 4),
                "reading_uncertainty": round(half / conv["px_y"], 4),
                "calibration_uncertainty": round(calib["y_calibration_uncertainty"], 4),
                "ink_px": len(pix),
            })
        marks.sort(key=lambda m: m["t_h"])
        panel["series"][label] = {"marks": marks}
        mark_times.extend(m["t_h"] for m in marks)

    times = sorted(set([round(t, 3) for t in np.arange(
        calib["xlim"][0], calib["xlim"][1] + 1e-9, 0.5)] + list(grid) + mark_times))
    for label, mask in masks.items():
        trace = extract_trace(mask, sub, conv["to_x"], conv["to_y"], conv["px_y"])
        panel["series"][label]["samples"] = interpolate(trace, times)
        if trace:
            panel["series"][label]["trace_span"] = [trace[0]["t_h"], trace[-1]["t_h"]]
    panel["sample_times"] = times
    return panel


# --------------------------------------------------------------------------- #
# figure specifications
# --------------------------------------------------------------------------- #

#: Figure 3: the held-out validation experiment.  Panel (a) is full width across
#: the top; panels (b) and (c) sit side by side below it.
FIG3_PANELS = {
    "a": {"frame": (99, 1785, 32, 511),
          "x_values": [0, 5, 10, 15, 20, 25, 30],
          "y_values": [100, 80, 60, 40, 20, 0],
          "xlabel": "time (h)", "ylabel": "dissolved oxygen (%)"},
    "b": {"frame": (99, 878, 660, 1139),
          "x_values": [0, 5, 10, 15, 20, 25, 30],
          "y_values": [20, 15, 10, 5, 0],
          "xlabel": "time (h)", "ylabel": "biomass (g/L DCW)"},
    "c": {"frame": (1006, 1785, 660, 1139),
          "x_values": [0, 5, 10, 15, 20, 25, 30],
          "y_values": [3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0],
          "xlabel": "time (h)", "ylabel": "glycerol concentration (g/L)"},
}

FIG3_META = {
    "figure": "Fig. 3, printed p. 6: model validation",
    "caption": (
        "Goodness of fit of the model with the experimental data that was not "
        "used for estimation of model parameters. Feeding composition of 20 % "
        "glycerol and 30 % yeast extract fed at 0.78 mL/h flow rate for "
        "a) dissolved oxygen b) Biomass c) glycerol concentration."
    ),
    "role": "validation",
    "independent_of_fitting": True,
    "feed": {"glycerol_percent_wv": 20.0, "yeast_extract_percent_wv": 30.0,
             "flow_mL_per_h": 0.78,
             "source": "printed p. 6, Fig. 3 caption"},
}

#: Figure 5: the authors' prediction for the selected optimum, with five proteins
#: cultivated in the same run -- their own measure of run-to-run spread.
FIG5_PANELS = {
    "a": {"frame": (99, 878, 32, 511),
          "x_values": [0, 5, 10, 15, 20, 25],
          "y_values": [100, 80, 60, 40, 20, 0],
          "xlabel": "time (h)", "ylabel": "dissolved oxygen (%)"},
    "b": {"frame": (1006, 1785, 32, 511),
          "x_values": [0, 5, 10, 15, 20, 25],
          "y_values": [6.8, 6.6, 6.4, 6.2],
          "xlabel": "time (h)", "ylabel": "pH"},
    "c": {"frame": (99, 878, 660, 1139),
          "x_values": [0, 5, 10, 15, 20, 25],
          "y_values": [25, 20, 15, 10, 5, 0],
          "xlabel": "time (h)", "ylabel": "biomass (g/L DCW)"},
    "d": {"frame": (1006, 1785, 660, 1139),
          "x_values": [0, 5, 10, 15, 20, 25],
          "y_values": [3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0],
          "xlabel": "time (h)", "ylabel": "glycerol concentration (g/L)"},
}

FIG5_META = {
    "figure": "Fig. 5, printed p. 7: model prediction for the selected optimum",
    "caption": (
        "Model prediction for the optimised feeding strategy, with five proteins "
        "cultivated in the same run: PDGF, FDH, G. Can. ADH, L. Kefir ADH, EYFP."
    ),
    "role": "prediction",
    "independent_of_fitting": True,
    "feed": {"glycerol_percent_wv": 17.5, "yeast_extract_percent_wv": 24.5,
             "flow_mL_per_h": 0.72, "feed_start_h": 6.0,
             "source": "printed p. 7, Fig. 5 caption and section 3.3"},
    "note_on_pH": (
        "Panel (b) plots pH for the five proteins and draws no model curve: the "
        "model has no pH term. It is extracted for completeness and recorded as "
        "unmodelled, not ignored."
    ),
}

#: Figure 2: the fitting experiment.  Extracted for completeness; the parameters
#: were tuned against it, so it cannot contradict or support the implementation.
FIG2_META = {
    "figure": "Fig. 2, printed p. 5: model fitting",
    "caption": (
        "Comparison of the model predicted values with the experimental data set "
        "with feeding composition of 30 % glycerol and 40 % yeast extract fed at "
        "0.52 mL/h flow rate for a) dissolved oxygen b) Biomass c) glycerol "
        "concentration."
    ),
    "role": "fitting",
    "independent_of_fitting": False,
    "feed": {"glycerol_percent_wv": 30.0, "yeast_extract_percent_wv": 40.0,
             "flow_mL_per_h": 0.52,
             "source": "printed p. 5, Fig. 2 caption"},
}


def extract_figure_rasters(pdf_path: Path) -> dict[int, Image.Image]:
    """Pull the figure raster images out of the PDF at native resolution."""
    import logging

    logging.disable(logging.CRITICAL)
    doc = pymupdf.open(pdf_path)
    out = {}
    for page_index, (xref, _w, _h) in PDF_XREFS.items():
        info = doc.extract_image(xref)
        out[page_index] = Image.open(io.BytesIO(info["image"])).convert("RGB")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rasters = extract_figure_rasters(args.pdf)

    document = {
        "dataset_id": "ganjave2022.figures",
        "version": "1.0.0",
        "source": {
            "source_id": "ganjave2022",
            "citation": (
                "S. D. Ganjave, V. A. J. E. S. Waghmare, P. P. Wangikar, 'High "
                "cell density cultivation of E. coli in shake flasks for the "
                "production of recombinant proteins', Biotechnology Reports 33 "
                "(2022) e00694."
            ),
            "doi": "10.1016/j.btre.2021.e00694",
        },
        "pdf": str(args.pdf),
        "method": {
            "calibration": (
                "axis frame found from spine rules; tick-label bounding-box "
                "centres; scale fitted over all labels; offset anchored on the "
                "axis minimum at the frame edge; label-vs-frame discrepancy "
                "reported as the calibration uncertainty"
            ),
            "series": (
                "hue classification by channel difference (experimental marks "
                "and each protein's colour; model prediction purple); legend "
                "boxes excluded; mark centroids and per-column trace medians "
                "read in data units"
            ),
            "limits": (
                "points where a raster column holds several trace branches are "
                "marked ambiguous, not averaged; a curve that coincides with an "
                "axis spine is not separately resolved and the span limit is "
                "recorded"
            ),
        },
        "figures": {},
    }

    jobs = [
        (5, FIG3_META, FIG3_PANELS, {**EXPERIMENTAL_MASKS, **MODEL_MASKS}),
        (6, FIG5_META, FIG5_PANELS, {**EXPERIMENTAL_MASKS, **MODEL_MASKS}),
    ]
    for page_index, meta, panels, series_masks in jobs:
        image = np.asarray(rasters[page_index])
        dark = image.mean(axis=2) < 130
        grid = [0.0, 4.0, 6.0, 12.0, 18.0, 24.0] if page_index == 5 else \
               [0.0, 2.0, 4.0, 6.0, 10.0, 14.0, 18.0, 22.0, 24.0]
        figure = dict(meta)
        figure["panels"] = {}
        for name, spec in panels.items():
            panel = digitize_panel(image, dark, spec["frame"], spec["x_values"],
                                   spec["y_values"], series_masks, grid,
                                   spec["xlabel"], spec["ylabel"])
            figure["panels"][name] = panel
            if "skipped" in panel:
                print(f"  {meta['figure']} panel {name}: SKIPPED ({panel['skipped']})")
            else:
                cal = panel["calibration"]
                counts = {k: len(v["marks"]) for k, v in panel["series"].items()}
                print(
                    f"  {meta['figure']} panel {name}: calibrated "
                    f"(x unc {cal['x_calibration_uncertainty']:.4f} h, "
                    f"y unc {cal['y_calibration_uncertainty']:.4f} units); "
                    f"marks {counts}"
                )
        document["figures"][str(page_index)] = figure

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2)
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
