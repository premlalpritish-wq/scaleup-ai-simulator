"""Lin et al. (2001): the complete simulation model printed in the Appendix.

    H. Y. Lin, B. Mathiszik, B. Xu, S.-O. Enfors, P. Neubauer, 'Determination
    of the Maximum Specific Uptake Capacities for Glucose and Oxygen in
    Glucose-Limited Fed-Batch Cultivations of Escherichia coli', Biotechnology
    and Bioengineering 73(5):347-357, 2001. doi:10.1002/bit.1078

What is here, and nothing more:

  * `context`   -- the strain, the (uninduced) plasmid, the medium, the reactor,
                   the scale and the operating conditions, each with its page;
  * `parameters`-- Table I (printed p. 348) transcribed in full, including the
                   four rows the paper prints twice, and the capacities the
                   abstract states in a different dimension;
  * `model`     -- the Appendix's seven printed differential equations, the
                   subsidiary-variable chain, the two correction branches, the
                   ivp initial values, the pulse method of equation (1), and an
                   RK4 integration of the printed system;
  * `manifest`  -- what this package declares about itself, including the four
                   models it deliberately does not implement;
  * `validate`  -- the structural fidelity checks the test suite and the
                   composition layer both run.

What is not here: any coupling to the composition layer or to another model, a
digitised trajectory, a value for cS, cO, kLa, DOT* or a fitted H, and any claim
that this model describes the composition layer's target process.

No third-party dependency. Standard library only.
"""

from __future__ import annotations

from . import context, manifest, model, parameters, provenance, source, units
from .manifest import ARTEFACT_ID, VERSION, build_manifest
from .model import (
    DIFFERENTIAL_SYSTEM_PAGE,
    MissingRunInput,
    ModelError,
    REQUIRED_RUN_INPUTS,
    SimulationParameters,
    SimulationResult,
    State,
    Subsidiary,
    derivatives,
    feed_constant,
    feed_exponential,
    qScap_from_pulse,
    simulate,
    subsidiary,
)
from .validate import validate

__all__ = [
    "ARTEFACT_ID",
    "DIFFERENTIAL_SYSTEM_PAGE",
    "MissingRunInput",
    "ModelError",
    "REQUIRED_RUN_INPUTS",
    "SimulationParameters",
    "SimulationResult",
    "State",
    "Subsidiary",
    "VERSION",
    "build_manifest",
    "context",
    "derivatives",
    "feed_constant",
    "feed_exponential",
    "manifest",
    "model",
    "parameters",
    "provenance",
    "qScap_from_pulse",
    "simulate",
    "source",
    "subsidiary",
    "units",
    "validate",
]
