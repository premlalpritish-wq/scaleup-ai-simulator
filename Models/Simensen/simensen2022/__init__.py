"""Simensen et al. (2022): the measured biomass composition, standalone.

    V. Simensen, C. Schulz, E. Karlsen, S. Bratelund, I. Burgos, L. B.
    Thorfinnsdottir, L. Garcia-Calvo, P. Bruheim, E. Almaas, 'Experimental
    determination of Escherichia coli biomass composition for constraint-based
    metabolic modeling', PLOS ONE 17(1):e0262450, 2022.
    doi:10.1371/journal.pone.0262450

What is here, and nothing more:

  * `context`  -- the strain, the absence of a construct, the M9 glucose medium,
                  the 3 L BioFlo 115 batch fermentor, the 1 L scale and the
                  sampling condition, each with its printed page;
  * `model`    -- Table 1 (printed p. 9) transcribed in full, all three columns,
                  with every printed standard deviation and every printed
                  non-numeric marker; the derived macromolecule sums; the prose
                  figures beside the table; and the models the paper does not
                  supply;
  * `manifest` -- what this package declares about itself;
  * `validate` -- the structural fidelity checks the test suite and the
                  composition layer both run.

What is not here: the flux-variability analysis of iML1515a (Eq 1, Table 2) --
its inputs are not part of this paper -- and any coupling to the composition
layer or another model. This is a dataset, not a simulator.

No third-party dependency. Standard library only.
"""

from __future__ import annotations

from . import context, manifest, model, provenance, source, units
from .manifest import ARTEFACT_ID, VERSION, build_manifest
from .model import (
    COLUMNS,
    DatasetError,
    TABLE_1,
    amino_acid_sum,
    composition,
    computed_macromolecule_sum,
    mass_fraction,
    printed_sum,
    row,
    rows_in_group,
)
from .validate import validate

__all__ = [
    "ARTEFACT_ID",
    "COLUMNS",
    "DatasetError",
    "TABLE_1",
    "VERSION",
    "amino_acid_sum",
    "build_manifest",
    "composition",
    "computed_macromolecule_sum",
    "context",
    "manifest",
    "mass_fraction",
    "model",
    "printed_sum",
    "provenance",
    "row",
    "rows_in_group",
    "source",
    "units",
    "validate",
]
