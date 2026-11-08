"""Executable model of Ganjave et al. (2022), eq. (1)-(16).

Module map:

``kinetics``     eq. (1)-(7): stoichiometries, response functions, growth rates,
                 enzyme dynamics, and the transcription notes
``batch``        eq. (8)-(11): the batch balances
``fed_batch``    eq. (12)-(16): the fed-batch balances and the feed program
``solver``       RK4(3) step-doubling integration with structured failures
``simulation``   orchestration, run provenance and the input digest
``reference``    the paper's reported conditions and outcomes
``composition``  the typed interface and the connections it refuses
``dimensions``   unit algebra for the dissolved-oxygen balance
``paper_equations``  reading the article's printed equations and their glyphs
``diagnostics``  structured diagnostics

Non-goals, restated because they bound everything else: this package does not
estimate parameters, does not perform the paper's multi-objective
optimisation, does not model protein expression or inclusion bodies, does not
scale the process up to a 3 L bioreactor, does not predict kLa for other
geometries, and contains no digitised figure data.
"""

from __future__ import annotations

from .batch import (
    batch_derivative,
    dDO_dt,
    dS1_dt,
    dS2_dt,
    dX_dt,
    oxygen_consumption_term,
    oxygen_transfer_term,
)
from .composition import (
    ALL_PORTS,
    CONTRACT_VERSION_COMPATIBLE,
    REFUSED_MAPPINGS,
    CompositionMismatch,
    Port,
    check_connection,
    manifest,
)
from .diagnostics import Diagnostic, DiagnosticCode, DiagnosticList, Severity
from .dimensions import Dimension, oxygen_balance_dimensions, oxygen_balance_report
from .fed_batch import FeedError, FeedProgram, dilution_rate, fed_batch_derivative
from .kinetics import (
    TRANSCRIPTION_NOTES,
    enzyme_fraction_derivative,
    growth_terms,
    response_r1,
    response_r2,
    specific_growth_1,
    specific_growth_2,
    specific_growth_rates,
    stoichiometric_residual_1,
    stoichiometric_residual_2,
)
from .simulation import (
    MODEL_ID,
    MODEL_VERSION,
    MODE_BATCH,
    MODE_FED_BATCH,
    MODES,
    SimulationResult,
    expected_final_volume,
    simulate,
)
from .solver import SOLVER_NAME, SOLVER_VERSION, IntegrationResult, SolverConfig, integrate

__all__ = [
    "ALL_PORTS",
    "CONTRACT_VERSION_COMPATIBLE",
    "CompositionMismatch",
    "Diagnostic",
    "DiagnosticCode",
    "DiagnosticList",
    "Dimension",
    "FeedError",
    "FeedProgram",
    "IntegrationResult",
    "MODE_BATCH",
    "MODE_FED_BATCH",
    "MODES",
    "MODEL_ID",
    "MODEL_VERSION",
    "Port",
    "REFUSED_MAPPINGS",
    "SOLVER_NAME",
    "SOLVER_VERSION",
    "Severity",
    "SimulationResult",
    "SolverConfig",
    "TRANSCRIPTION_NOTES",
    "batch_derivative",
    "check_connection",
    "dDO_dt",
    "dS1_dt",
    "dS2_dt",
    "dX_dt",
    "dilution_rate",
    "enzyme_fraction_derivative",
    "expected_final_volume",
    "fed_batch_derivative",
    "growth_terms",
    "integrate",
    "manifest",
    "oxygen_balance_dimensions",
    "oxygen_balance_report",
    "oxygen_consumption_term",
    "oxygen_transfer_term",
    "response_r1",
    "response_r2",
    "simulate",
    "specific_growth_1",
    "specific_growth_2",
    "specific_growth_rates",
    "stoichiometric_residual_1",
    "stoichiometric_residual_2",
]