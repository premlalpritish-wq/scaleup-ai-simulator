"""Normalise the numerical data actually recovered from the supplementary document.

    python composition/tools/normalise_recovered_data.py

Produces a machine-readable record of everything in ``mmc1.docx`` that carries a real
number, and states plainly what is **not** there.

The recovered numerical content is one table: Table S4, the kLa measurements. It is
author-reported values, not a digitisation, so it carries no reading uncertainty. It
is **not** a time course and does not serve the Figure 3a/3b target; it is recorded
because it is genuine recovered data and because it independently confirms a model
input (kLa = 133 h^-1 at the configuration the evaluation assumes).

Two transformations are applied to Table S4, and both are recorded on every row so a
reader can see what was measured and what was carried forward:

* **merged cells.** The Word table uses vertical merges for the volume and the shaking
  speed; a blank cell means "same as above", not "missing". Those are forward-filled and
  marked ``volume_forward_filled`` / ``rpm_forward_filled``.
* **column grouping.** The left block is the 2.5 cm pitch series and the right block the
  5 cm pitch series, as the caption states.

Nothing is smoothed, averaged, converted or inferred beyond those two.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "data" / "ganjave2022" / "source_data"
INVENTORY = SOURCE_DIR / "supplementary_inventory.json"
PACKAGE = SOURCE_DIR / "PMC8718739_supplementary.zip"
DOCX = SOURCE_DIR / "mmc1_supplementary.docx"
OUT = SOURCE_DIR / "recovered_numerical_data.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def as_number(text: str) -> float | None:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def normalise_kla_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    """Table S4, two pitch blocks, with merged cells forward-filled and marked."""
    rows = [r for r in table["rows"] if any(str(c).strip() for c in r)]
    if not rows:
        return []

    # Column layout: volume | rpm | kLa | spacer | volume | rpm | kLa
    blocks = [
        {"pitch_cm": 2.5, "volume_col": 0, "rpm_col": 1, "kla_col": 2},
        {"pitch_cm": 5.0, "volume_col": 4, "rpm_col": 5, "kla_col": 6},
    ]

    recovered: list[dict[str, Any]] = []
    for block in blocks:
        volume = None
        rpm = None
        for index, row in enumerate(rows[1:], start=1):
            kla = as_number(row[block["kla_col"]] if len(row) > block["kla_col"] else "")
            if kla is None:
                continue
            raw_volume = str(row[block["volume_col"]]).strip() if len(row) > block["volume_col"] else ""
            raw_rpm = str(row[block["rpm_col"]]).strip() if len(row) > block["rpm_col"] else ""
            volume_filled = not raw_volume
            rpm_filled = not raw_rpm
            if raw_volume:
                volume = as_number(raw_volume)
            if raw_rpm:
                rpm = as_number(raw_rpm)
            recovered.append({
                "table": "S4",
                "quantity": "volumetric_mass_transfer_coefficient",
                "symbol": "kLa",
                "unit": "h^-1",
                "medium_volume_ml": volume,
                "shaking_speed_rpm": rpm,
                "kla_h_per_h": kla,
                "pitch_cm": block["pitch_cm"],
                "volume_forward_filled": volume_filled,
                "rpm_forward_filled": rpm_filled,
                "source_row_in_table": index,
                "data_class": "author_reported_measurement",
                "digitized": False,
                "reading_uncertainty": None,
            })
    return recovered


def main() -> int:
    if not INVENTORY.exists() or not DOCX.exists():
        print("Run inspect_supplementary.py first; the inventory is absent.")
        return 1

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    tables = inventory["tables"]

    kla = normalise_kla_table(tables[2]) if len(tables) > 2 else []

    payload = {
        "record_id": "ganjave2022.recovered_numerical_data",
        "version": "1.0.0",
        "summary": (
            "Every numerical value recovered from the publisher's supplementary "
            "document for Ganjave et al. (2022). It is one table of kLa "
            "measurements. It is NOT a time course."
        ),
        "target_not_recovered": {
            "goal": (
                "numerical time courses underlying Figure 3a (dissolved oxygen) and "
                "Figure 3b (biomass) of the held-out validation experiment "
                "(PDGF, 20 % glycerol, 30 % yeast extract, 0.78 mL/h)"
            ),
            "status": "NOT PUBLISHED",
            "evidence": [
                "The article carries no Data Availability statement and names no "
                "repository (checked in the PDF text layer and the PMC full text).",
                "The publisher lists exactly one supplementary file, mmc1.docx.",
                "mmc1.docx contains no spreadsheet, CSV, or embedded data part; its "
                "only tables are S1 (protein identities), S3 (optimisation bounds) "
                "and S4 (kLa).",
                "The two native charts in mmc1.docx are kLa determination plots with "
                "no cached numeric values.",
                "PMC and Europe PMC expose no dataset links for the article.",
                "No repository deposit (Zenodo, figshare, GitHub, Mendeley Data, "
                "Dryad) was found for the DOI or the authors.",
            ],
        },
        "provenance": {
            "article_doi": "10.1016/j.btre.2021.e00694",
            "article_title": (
                "High cell density cultivation of E. coli in shake flasks for the "
                "production of recombinant proteins"
            ),
            "pmcid": "PMC8718739",
            "publisher_supplementary_file": "mmc1.docx",
            "obtained_from": (
                "https://www.ebi.ac.uk/europepmc/webservices/rest/"
                "PMC8718739/supplementaryFiles"
            ),
            "package_file": PACKAGE.name,
            "package_sha256": digest(PACKAGE),
            "docx_sha256": digest(DOCX),
            "inventory_sha256": digest(INVENTORY),
            "licence": (
                "CC BY-NC-ND 4.0. The publisher's file is stored unmodified; this "
                "record restates numbers from it and redistributes no part of it."
            ),
        },
        "transformations": [
            {
                "id": "merged_cell_forward_fill",
                "applies_to": "Table S4",
                "description": (
                    "Word vertical merges leave the volume and shaking-speed cells "
                    "blank on continuation rows. Blanks are carried forward from the "
                    "row above and flagged on each record."
                ),
                "affects": ["medium_volume_ml", "shaking_speed_rpm"],
                "marked_by": ["volume_forward_filled", "rpm_forward_filled"],
            },
            {
                "id": "column_group_assignment",
                "applies_to": "Table S4",
                "description": (
                    "The left block is the 2.5 cm pitch series and the right block "
                    "the 5 cm pitch series, per the table caption."
                ),
                "affects": ["pitch_cm"],
            },
        ],
        "transformations_not_applied": [
            "no smoothing, fitting or interpolation",
            "no unit conversion",
            "no averaging of replicates (the paper reports single measurements here)",
            "no imputation of any value",
        ],
        "recovered_tables": [
            {
                "table_id": "S4",
                "caption": (
                    "Measurement of volumetric mass transfer coefficient (kLa) at "
                    "different shaking speed, culture volume and (a) 2.5 cm pitch and "
                    "(b) 5 cm pitch."
                ),
                "n_records": len(kla),
                "is_time_course": False,
                "relevance": (
                    "Independent confirmation of kLa = 133 h^-1 at 100 mL, 200 rpm, "
                    "5 cm pitch -- the value the frozen evaluation uses as a model "
                    "input. It says nothing about biomass or dissolved oxygen."
                ),
                "records": kla,
            }
        ],
        "other_tables_present_but_not_time_courses": [
            {"table_id": "S1", "caption": "Details of the model proteins used in the study",
             "content": "UniProt identifiers and plasmid backbones"},
            {"table_id": "S3", "caption": "Constraints applied on the multi-objective optimization algorithm",
             "content": "bound ranges for feed glycerol, complex substrate and flow rate"},
        ],
        "figures_present": (
            "Figures S1-S10 as embedded images. S3-S7 are the model-fitting "
            "experiments and S8 the second validation experiment. None carries "
            "numeric data, and Figure 3 is main-text only."
        ),
    }

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  Table S4: {len(kla)} kLa measurements recovered")
    five_cm = [r for r in kla if r["pitch_cm"] == 5.0
               and r["medium_volume_ml"] == 100 and r["shaking_speed_rpm"] == 200]
    for record in five_cm:
        print(f"    100 mL, 200 rpm, 5 cm pitch -> kLa = {record['kla_h_per_h']} h^-1 "
              f"(the value the frozen configuration uses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
