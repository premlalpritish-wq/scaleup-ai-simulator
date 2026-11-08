"""Nanchen, Schicker & Sauer (2006): Pirt's chemostat relation, standalone.

    A. Nanchen, A. Schicker, U. Sauer, 'Nonlinear Dependency of Intracellular
    Fluxes on Growth Rate in Miniaturized Continuous Cultures of Escherichia
    coli', Applied and Environmental Microbiology 72(2):1164-1172, 2006.
    doi:10.1128/AEM.72.2.1164-1172.2006

What is here, and nothing more:

  * `context`  -- the strain, the absence of a construct, the M9 medium, the
                  10-mL mini-scale chemostat, the scale and the conditions, each
                  with its printed page;
  * `model`    -- Pirt's printed equation (3) with this paper's own fitted
                  parameters (Table 1, MG1655, "This study"), the relation
                  inverted, the observed yield it implies, and the four models
                  the paper deliberately does not supply;
  * `manifest` -- what this package declares about itself;
  * `validate` -- the structural fidelity checks the test suite and the
                  composition layer both run.

What is not here: the 13C flux-ratio equations (1) and (2) -- their inputs are
not tabulated -- the eleven determined flux ratios, an oxygen-transfer model, and
any coupling to the composition layer or another model.

No third-party dependency. Standard library only.
"""

from __future__ import annotations

from . import context, manifest, model, provenance, source, units
from .manifest import ARTEFACT_ID, VERSION, build_manifest
from .model import (
    COMPARISON_TABLE_NOTE,
    MOL_PER_MMOL,
    MaintenanceParameters,
    ModelError,
    THIS_STUDY,
    biomass_yield,
    mu_from_q_glc,
    q_glc,
)
from .validate import validate

__all__ = [
    "ARTEFACT_ID",
    "COMPARISON_TABLE_NOTE",
    "MOL_PER_MMOL",
    "MaintenanceParameters",
    "ModelError",
    "THIS_STUDY",
    "VERSION",
    "biomass_yield",
    "build_manifest",
    "context",
    "manifest",
    "model",
    "mu_from_q_glc",
    "provenance",
    "q_glc",
    "source",
    "units",
    "validate",
]
