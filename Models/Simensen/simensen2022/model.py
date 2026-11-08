"""The measured biomass composition of Table 1, and nothing else.

Simensen et al. (2022) grew *E. coli* K-12 MG1655 in a defined glucose minimal
medium in a batch fermentor and quantified the macromolecular composition of the
biomass. Table 1 (printed p. 9) reports every measured component as a mass
fraction ``g gCDW-1``, with a standard deviation and, beside each row, the two
previously published compositions the paper compares against (Neidhardt and Beck
et al.).

That table is a dataset, not an equation, and it is what this module encodes. It
is the paper's own measurement, in the paper's own condition (balanced
exponential growth in that fermentor), at the paper's own unit (mass fraction of
cell dry weight), so it can be implemented faithfully standalone.

**Nothing is coerced.** A cell the paper prints as ``n.d.`` (not detected), ``-``
(not measured) or with ``NA`` for a standard deviation keeps that printed marker
instead of becoming 0.0. Only cells with a printed number hold a number.

**Two totals are printed and they are not the same.** The table's own ``Sum`` row
prints ``0.835`` for this work, ``1.000`` for Neidhardt and ``0.643`` for Beck et
al.; the abstract (printed p. 1) prints an overall coverage of ``91.6%``. Both
are recorded as printed, and the package does not reconcile them, because the
paper does not: the table's sum covers the rows it lists and the abstract's
coverage is its own stated figure.

**What is not here.** The flux-variability comparison (Eq 1 and Table 2) needs
the constraint-based model iML1515 and its flux ranges, which are not part of
this paper; it is declared in `MISSING_MODELS` and not implemented. This module
declares no ports and registers nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .provenance import EvidenceRef, Quantity, reported

#: Printed page carrying Table 1.
TABLE_I_PAGE = 9
#: Printed page carrying the abstract's coverage figure.
ABSTRACT_PAGE = 1
#: Printed page carrying the ribose statement quoted here.
DISCUSSION_PAGE = 12

#: Table 1's three numeric columns, in printed order.
COLUMNS = ("this_work", "neidhardt", "beck_et_al")

COLUMN_LABELS = {
    "this_work": "This work",
    "neidhardt": "Neidhardt",
    "beck_et_al": "Beck et al.",
}

#: Printed markers for a cell that is not a number.
NOT_DETECTED = "n.d."
NOT_MEASURED = "-"
NO_SD = "NA"


class DatasetError(ValueError):
    """Raised when the dataset is asked for something it does not hold."""


@dataclass(frozen=True)
class Cell:
    """One cell of Table 1: a mass fraction, its SD, and any printed markers.

    The paper can decline to print the *value* (``n.d.``, ``-``) or decline to
    print the *standard deviation* (``NA``). Those are different statements, so
    they are held in different fields and neither is coerced.
    """

    value: float | None
    sd: float | None
    note: str = ""
    sd_note: str = ""

    @property
    def is_number(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "sd": self.sd,
            "note": self.note,
            "sd_note": self.sd_note,
        }


@dataclass(frozen=True)
class Row:
    """One row of Table 1 across its three printed columns."""

    name: str
    group: str
    cells: dict[str, Cell]
    printed_page: int = TABLE_I_PAGE

    def cell(self, column: str) -> Cell:
        try:
            return self.cells[column]
        except KeyError:
            raise DatasetError(
                f"{self.name!r} has no cell for column {column!r}; "
                f"known columns: {sorted(self.cells)}"
            ) from None

    def value(self, column: str) -> float:
        cell = self.cell(column)
        if cell.value is None:
            raise DatasetError(
                f"{self.name!r}/{column} is printed as {cell.note or 'nothing'}, "
                f"not as a number"
            )
        return cell.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "cells": {c: self.cells[c].to_dict() for c in sorted(self.cells)},
            "printed_page": self.printed_page,
        }



#: Table 1, in printed order, as (name, group, this_work, neidhardt, beck_et_al),
#: where each cell is (value, sd, note) and `None`/"" means the paper prints the
#: row's value or SD as absent.
_RAW: tuple[tuple[str, str, tuple, tuple, tuple], ...] = (
    ("Protein", "macromolecule", (0.54, 0.02, ""), (0.550, None, ""), (0.35, 0.01, "")),
    ("Alanine", "amino_acid", (0.046, 0.004, ""), (0.039, None, ""), (0.025, 0.001, "")),
    ("Arginine", "amino_acid", (0.052, 0.006, ""), (0.044, None, ""), (0.024, 0.001, "")),
    ("Asparagine/Aspartate", "amino_acid", (0.052, 0.009, ""), (0.052, None, ""), (0.035, 0.001, "")),
    ("Cysteine", "amino_acid", (0.010, None, "NA"), (0.009, None, ""), (0.004, None, "NA")),
    ("Glutamine/Glutamate", "amino_acid", (0.049, 0.007, ""), (0.068, None, ""), (0.049, 0.002, "")),
    ("Glycine", "amino_acid", (0.025, 0.003, ""), (0.033, None, ""), (0.023, 0.001, "")),
    ("Histidine", "amino_acid", (0.012, 0.003, ""), (0.012, None, ""), (0.0070, 0.0003, "")),
    ("Isoleucine", "amino_acid", (0.026, 0.002, ""), (0.031, None, ""), (0.017, 0.001, "")),
    ("Leucine", "amino_acid", (0.050, 0.007, ""), (0.048, None, ""), (0.026, 0.001, "")),
    ("Lysine", "amino_acid", (0.036, 0.002, ""), (0.042, None, ""), (0.024, 0.001, "")),
    ("Methionine", "amino_acid", (0.018, None, "NA"), (0.019, None, ""), (0.011, None, "NA")),
    ("Phenylalanine", "amino_acid", (0.028, 0.002, ""), (0.026, None, ""), (0.018, 0.002, "")),
    ("Proline", "amino_acid", (0.022, None, "NA"), (0.020, None, ""), (0.013, 0.001, "")),
    ("Serine", "amino_acid", (0.021, 0.004, ""), (0.018, None, ""), (0.014, 0.002, "")),
    ("Threonine", "amino_acid", (0.028, 0.001, ""), (0.024, None, ""), (0.0172, 0.0004, "")),
    ("Tryptophan", "amino_acid", (0.012, None, "NA"), (0.010, None, ""), (0.008, None, "NA")),
    ("Tyrosine", "amino_acid", (0.016, 0.003, ""), (0.021, None, ""), (0.014, 0.003, "")),
    ("Valine", "amino_acid", (0.033, 0.003, ""), (0.040, None, ""), (0.022, 0.001, "")),
    ("RNA", "macromolecule", (0.190, 0.004, ""), (0.205, None, ""), (0.172, 0.005, "")),
    ("AMP", "nucleotide", (0.050, None, "NA"), (0.054, None, ""), (0.045, None, "NA")),
    ("GMP", "nucleotide", (0.064, None, "NA"), (0.070, None, ""), (0.058, None, "NA")),
    ("CMP", "nucleotide", (0.040, None, "NA"), (0.038, None, ""), (0.036, None, "NA")),
    ("UMP", "nucleotide", (0.037, None, "NA"), (0.042, None, ""), (0.033, None, "NA")),
    ("DNA", "macromolecule", (0.013, 0.003, ""), (0.031, None, ""), (0.010, 0.001, "")),
    ("dAMP", "nucleotide", (0.003, None, "NA"), (0.008, None, ""), (0.002, None, "NA")),
    ("dGMP", "nucleotide", (0.004, None, "NA"), (0.008, None, ""), (0.003, None, "NA")),
    ("dCMP", "nucleotide", (0.003, None, "NA"), (0.007, None, ""), (0.002, None, "NA")),
    ("dTMP", "nucleotide", (0.003, None, "NA"), (0.007, None, ""), (0.002, None, "NA")),
    ("Carbohydrate", "macromolecule", (0.0312, 0.0005, ""), (0.057, None, ""), (0.042, 0.002, "")),
    ("Glucose", "carbohydrate", (0.0224, 0.0002, ""), (0.028, None, ""), (None, None, "-")),
    ("Glucosamine", "carbohydrate", (0.0053, 0.0002, ""), (0.003, None, ""), (None, None, "-")),
    ("Galactose", "carbohydrate", (0.0036, 0.0004, ""), (None, None, "-"), (None, None, "-")),
    ("Rhamnose", "carbohydrate", (None, None, "n.d."), (0.001, None, ""), (None, None, "-")),
    ("Heptose", "carbohydrate", (None, None, "-"), (0.005, None, ""), (None, None, "-")),
    ("KDO", "carbohydrate", (None, None, "-"), (0.006, None, ""), (None, None, "-")),
    ("N-acetylglucosamine", "carbohydrate", (None, None, "n.d."), (0.006, None, ""), (None, None, "-")),
    ("N-acetylmuramic acid", "carbohydrate", (None, None, "-"), (0.008, None, ""), (None, None, "-")),
    ("Lipid", "macromolecule", (0.061, 0.002, ""), (0.091, None, ""), (0.067, 0.006, "")),
    ("Others", "macromolecule", (None, None, "-"), (0.066, None, ""), (None, None, "-")),
    ("Sum", "total", (0.835, None, ""), (1.000, None, ""), (0.643, None, "")),
)


def _cell(spec: tuple) -> Cell:
    """Build a cell from ``(value, sd, marker)``.

    A marker on a cell that has no number is a statement about the *value*
    (``n.d.``, ``-``); a marker on a cell that has a number is a statement about
    its *standard deviation* (``NA``).
    """
    value, sd, marker = spec
    if value is None:
        return Cell(value=None, sd=None, note=marker or NOT_MEASURED, sd_note="")
    return Cell(value=value, sd=sd, note="", sd_note=marker)


TABLE_1: tuple[Row, ...] = tuple(
    Row(
        name=name,
        group=group,
        cells={
            "this_work": _cell(tw),
            "neidhardt": _cell(ne),
            "beck_et_al": _cell(be),
        },
    )
    for name, group, tw, ne, be in _RAW
)

#: The macromolecular groups whose fractions the table's own Sum row totals.
MACROMOLECULE_GROUPS = ("macromolecule",)


# --------------------------------------------------------------------------- #
# accessors
# --------------------------------------------------------------------------- #


def row(name: str) -> Row:
    for r in TABLE_1:
        if r.name == name:
            return r
    raise DatasetError(f"Table 1 has no row {name!r}")


def rows_in_group(group: str) -> tuple[Row, ...]:
    return tuple(r for r in TABLE_1 if r.group == group)


def mass_fraction(name: str, column: str = "this_work") -> float:
    """The printed mass fraction of `name` in `column`, in ``g gCDW-1``."""
    return row(name).value(column)


def amino_acid_rows() -> tuple[Row, ...]:
    return rows_in_group("amino_acid")


def amino_acid_sum(column: str = "this_work") -> float:
    """The amino-acid fractions of that column, added up.

    The paper reports them as fractions of cell dry weight and also reports a
    separate ``Protein`` row, so this sum is *not* expected to equal ``Protein``:
    it is the resolved part of the protein pool. The package reports both and
    reconciles neither.
    """
    total = 0.0
    for r in amino_acid_rows():
        cell = r.cell(column)
        if cell.value is not None:
            total += cell.value
    return total


def printed_sum(column: str = "this_work") -> float:
    """The table's own ``Sum`` row for that column."""
    return row("Sum").value(column)


def computed_macromolecule_sum(column: str = "this_work") -> float:
    """Protein + RNA + DNA + carbohydrate + lipid (+ Others where printed).

    This is the arithmetic the table's ``Sum`` row implies, recomputed from the
    encoded rows, so the transcription can be checked against the printed total.
    """
    names = ("Protein", "RNA", "DNA", "Carbohydrate", "Lipid", "Others")
    total = 0.0
    for name in names:
        cell = row(name).cell(column)
        if cell.value is not None:
            total += cell.value
    return total


def composition(column: str = "this_work") -> dict[str, float]:
    """The top-level macromolecule fractions of a column, in ``g gCDW-1``.

    These are the numbers a biomass objective function uses: the fraction of each
    macromolecular class the cell must synthesise.
    """
    out: dict[str, float] = {}
    for name in ("Protein", "RNA", "DNA", "Carbohydrate", "Lipid", "Others"):
        cell = row(name).cell(column)
        if cell.value is not None:
            out[name] = cell.value
    return out


def stated_markers() -> dict[str, tuple[str, ...]]:
    """Every printed non-numeric marker in the table, by row name."""
    out: dict[str, tuple[str, ...]] = {}
    for r in TABLE_1:
        notes = sorted(
            {c.note for c in r.cells.values() if c.note}
            | {c.sd_note for c in r.cells.values() if c.sd_note}
        )
        if notes:
            out[r.name] = tuple(notes)
    return out



@dataclass(frozen=True)
class ReportedStatement:
    """A figure the paper states in prose, with its printed page."""

    statement_id: str
    label: str
    value: float
    unit: str
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "evidence": self.evidence.to_dict(),
        }


#: Figures the paper states in prose beside the table.
REPORTED_STATEMENTS: tuple[ReportedStatement, ...] = (
    ReportedStatement(
        "coverage.overall", "overall biomass mass coverage quantified", 91.6, "%",
        EvidenceRef(printed_page=ABSTRACT_PAGE, section="Abstract",
                    quote="quantifying 91.6% of the biomass"),
    ),
    ReportedStatement(
        "sum.this_work", "Table 1 Sum row, This work", 0.835, "g/g",
        EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1, Sum row",
                    quote="0.835"),
    ),
    ReportedStatement(
        "sum.neidhardt", "Table 1 Sum row, Neidhardt", 1.000, "g/g",
        EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1, Sum row",
                    quote="1.000"),
    ),
    ReportedStatement(
        "sum.beck", "Table 1 Sum row, Beck et al.", 0.643, "g/g",
        EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1, Sum row",
                    quote="0.643"),
    ),
    ReportedStatement(
        "ribose", "ribose measured in addition to the listed carbohydrates",
        5.1, "%",
        EvidenceRef(printed_page=DISCUSSION_PAGE, section="Discussion",
                    quote="we measured 5.1% ribose"),
    ),
)


def reported_quantities() -> dict[str, Quantity]:
    """The ``This work`` column as reported Quantities, keyed by row name."""
    out: dict[str, Quantity] = {}
    for r in TABLE_1:
        cell = r.cell("this_work")
        if cell.value is None:
            continue
        out[r.name] = reported(
            f"table1.this_work.{r.name}", r.name, cell.value, "g/g",
            EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1",
                        quote=f"{cell.value:g}"),
            original_unit="g gCDW-1",
            notes=(
                f"standard deviation as printed: {cell.sd}"
                if cell.sd is not None
                else "no standard deviation printed"
            ),
        )
    return out


#: Models the paper needs in order to be predictive and does not supply.
MISSING_MODELS: tuple[dict[str, str], ...] = (
    {
        "model_id": "fva.iML1515a_comparison",
        "label": "The flux-variability comparison (Eq 1 and Table 2)",
        "why_not_implemented": (
            "Eq 1's fractional flux-range overlap xi is a function of two "
            "constraint-based solutions of the genome-scale model iML1515a. The "
            "model file and the computed flux ranges are not part of this paper, "
            "and neither is supplied here, so implementing xi would mean "
            "inventing the flux distribution."
        ),
    },
    {
        "model_id": "dataset.table_2_flux_shifts",
        "label": "Table 2's reaction flux shifts",
        "why_not_implemented": (
            "Table 2 lists examples of reactions whose feasible flux range shifts "
            "between the two biomass objective functions. It is a selection, not "
            "a complete table, and it is computed from the model above; the "
            "package does not invent the missing rows."
        ),
    },
    {
        "model_id": "coupling.other_models",
        "label": "Coupling to the composition layer",
        "why_not_implemented": (
            "This is a standalone dataset of Simensen et al.'s own measurement. "
            "It declares no ports, transfers no value into another model, adds no "
            "adapter registration and makes no compatibility claim."
        ),
    },
)

