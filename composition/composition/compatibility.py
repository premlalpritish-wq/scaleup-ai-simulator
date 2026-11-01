"""Which of the seven papers may contribute to the Zielinski insulin simulation.

This module answers one question, for every model the project now holds:

    can this model take part in ``zielinski2019.rhi_process`` -- and if not, why not?

It is *assessment data*, not a rule engine. Where a pair of registered models
already has a declared position, the verdict is **read from**
:mod:`composition.cross_model` rather than restated, so the two cannot drift; for
the standalone and dataset models, which have no ports and therefore no boundary,
the position is recorded here for the first time, with the same vocabulary and
the same standard of evidence.

## The five classifications

The vocabulary is the brief's, and each value is a claim of a different strength:

``dynamically_composable``
    A validated port-to-port connection exists, or the model *is* the simulation.
    Only Zielinski itself is in this class, because it is the baseline.
``evidence_compatible``
    No dynamic connection, but the model supplies evidence that could validate or
    constrain a quantity the target process actually reports.
``contextually_relevant_not_composable``
    The same scientific phenomenon in a different experiment. Adding its numbers
    would transfer parameters across experiments, which this project refuses.
``incompatible``
    A source, or the engine's mechanical rules, states why the two cannot be
    connected at all.
``insufficient_information``
    Not enough is known about the model to judge.

**No model is in ``evidence_compatible``, and that is a finding rather than an
omission.** Each candidate measures a different strain, medium, mode or scale
from the target, and the project's own evidence rules
(:data:`composition.evidence.sourcing.IDENTITY_DIMENSIONS`) refuse a finding that
fails identity. The step is recorded in ``evidence_check`` so a reader can see
what *would* have to match.

## What this module does not do

It does not connect anything. It emits no diagnostics and changes no verdict the
engine makes. ``python -m composition.compatibility --check`` fails when the
assessment and the tree disagree -- a missing package, a paper folder the corpus
does not have, a registered model whose verdict was restated instead of read, or
a claim of participation that no permitted boundary supports.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import cross_model

if True:  # keep imports local to this package's runtime shape, as the sibling modules do
    from .evidence import papers as paper_index

#: The process every candidate is assessed against.
TARGET_MODEL = "zielinski2019.rhi_process"
TARGET_MODEL_VERSION = "1.0.0"
TARGET_PAPER = "Zielinski et al. (2019)"
TARGET_PROCESS = (
    "E. coli 20 IBA 1 (CSH50R derivative), plasmid pIBAINS, GMS medium, 4 L in a "
    "7.5 L Bioflo Celligen 310, batch with pH-stat glucose feeding, 30 degC"
)


class Classification(str, Enum):
    """The brief's five classes, strongest to weakest claim."""

    DYNAMICALLY_COMPOSABLE = "dynamically_composable"
    EVIDENCE_COMPATIBLE = "evidence_compatible"
    CONTEXTUALLY_RELEVANT = "contextually_relevant_not_composable"
    INCOMPATIBLE = "incompatible"
    INSUFFICIENT_INFORMATION = "insufficient_information"


#: The number the brief gives each class, and the phrase a panel should show.
CLASSIFICATION_LABELS: dict[str, tuple[int, str]] = {
    Classification.DYNAMICALLY_COMPOSABLE.value: (
        1, "dynamically composable"),
    Classification.EVIDENCE_COMPATIBLE.value: (
        2, "evidence / validation compatible"),
    Classification.CONTEXTUALLY_RELEVANT.value: (
        3, "contextually relevant, not composable"),
    Classification.INCOMPATIBLE.value: (
        4, "incompatible"),
    Classification.INSUFFICIENT_INFORMATION.value: (
        5, "insufficient information"),
}


@dataclass(frozen=True)
class Inspection:
    """What was inspected, on the brief's nine axes.

    Kept as fields rather than prose so a panel can render the same nine rows for
    every model and a reader can compare two models column by column.
    """

    organism: str
    context: str
    inputs: str
    outputs: str
    units: str
    equations: str
    parameters: str
    time_scale: str
    assumptions: str

    def to_dict(self) -> dict[str, str]:
        return {
            "organism": self.organism,
            "context": self.context,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "units": self.units,
            "equations": self.equations,
            "parameters": self.parameters,
            "time_scale": self.time_scale,
            "assumptions": self.assumptions,
        }


@dataclass(frozen=True)
class Assessment:
    """One model's standing against the Zielinski insulin simulation."""

    key: str
    display_name: str
    #: ``baseline`` for the target process itself, ``candidate`` for the rest.
    role: str
    classification: Classification
    #: True only when the model takes part in the executable simulation.
    contributes: bool
    summary: str
    paper: str
    paper_folder: str
    package: str
    model_id: str = ""
    model_version: str = ""
    inspection: Inspection | None = None
    #: Why it cannot contribute. Empty for the baseline.
    blockers: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    #: What would have to be true to move it up a class.
    remediation: str = ""
    #: The ``cross_model`` stance for registered pairs; read, never restated.
    cross_model_stance: str = ""
    cross_model_evidence_basis: str = ""
    #: Why no candidate reaches ``evidence_compatible``, stated per model.
    evidence_check: str = ""

    @property
    def is_baseline(self) -> bool:
        return self.role == "baseline"

    @property
    def registered(self) -> bool:
        return bool(self.model_id)

    @property
    def classification_number(self) -> int:
        return CLASSIFICATION_LABELS[self.classification.value][0]

    @property
    def classification_label(self) -> str:
        return CLASSIFICATION_LABELS[self.classification.value][1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "role": self.role,
            "is_baseline": self.is_baseline,
            "registered": self.registered,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "package": self.package,
            "paper": self.paper,
            "paper_folder": self.paper_folder,
            "classification": self.classification.value,
            "classification_number": self.classification_number,
            "classification_label": self.classification_label,
            "contributes": self.contributes,
            "summary": self.summary,
            "inspection": self.inspection.to_dict() if self.inspection else {},
            "blockers": list(self.blockers),
            "evidence": list(self.evidence),
            "remediation": self.remediation,
            "cross_model_stance": self.cross_model_stance,
            "cross_model_evidence_basis": self.cross_model_evidence_basis,
            "evidence_check": self.evidence_check,
        }


def _boundary_between(candidate: str) -> cross_model.Boundary | None:
    """The declared ``cross_model`` boundary between `candidate` and the target.

    Read, not restated: if the verdict changes there, this module's copy of it
    changes with it. Either direction is accepted because a candidate that
    consumes a Zielinski output is as interesting as one that publishes into it.
    """
    for source, target in ((candidate, TARGET_MODEL), (TARGET_MODEL, candidate)):
        boundary = cross_model.boundary_for(source, target)
        if boundary is not None:
            return boundary
    return None


def _stance(candidate: str) -> tuple[str, str]:
    """``(stance, evidence_basis)`` for a registered candidate, or ``("", "")``."""
    boundary = _boundary_between(candidate)
    if boundary is None:
        return "", ""
    return boundary.stance, boundary.evidence_basis


_ZIELINSKI_INSPECTION = Inspection(
    organism="E. coli 20 IBA 1, a CSH50R derivative, carrying plasmid pIBAINS",
    context=(
        "GMS medium; 4 L in a 7.5 L Bioflo Celligen 310; batch with pH-stat "
        "glucose feeding; 30 degC; 15 operations from inoculum to RP-HPLC"
    ),
    inputs=(
        "196 published ports. The ~120 input ports are the operating conditions "
        "of one reported experiment: volumes, durations, temperatures, pH "
        "windows, concentrations and centrifugation forces"
    ),
    outputs=(
        "reported and computed process quantities: the OD600 time course, wet "
        "biomass g/L, inclusion bodies g/L, absorbance, activities, fraction "
        "volumes and an inclusion-body fraction of biomass"
    ),
    units="L, mL, uL, h, min, degC, g/L, mg/dL, mM, M, AU, %, xg, Da, IU",
    equations=(
        "accounting identities and unit conversions only. The paper reports no "
        "growth kinetics, no oxygen transfer and no spatial fields, so there is "
        "no rate equation to compose with"
    ),
    parameters="23 declared targets; predictive mode resolves 0 of 23 and fails closed",
    time_scale="hours, across a 15-operation process",
    assumptions=(
        "evidence_replay restates the paper's reported numbers; it does not "
        "predict a new batch"
    ),
)

_GANJAVE_STANCE = _stance("ganjave")
_GANJAVE_INSPECTION = Inspection(
    organism="E. coli, K-12 lineage, grown on glycerol plus a lumped complex substrate",
    context=(
        "fed-batch in a 3 L vessel; feed begins at 6 h at the dissolved-oxygen "
        "minimum; cybernetic enzyme synthesis; the model integrates 24 h"
    ),
    inputs=(
        "initial biomass, glycerol, complex substrate and dissolved oxygen, plus "
        "feed glycerol/complex-substrate concentrations, volumetric feed rate and "
        "feed start time"
    ),
    outputs=(
        "biomass, glycerol, complex substrate, dissolved oxygen percentage and "
        "culture volume over time"
    ),
    units="g/L, % of saturation, mL/h, h, L",
    equations="cybernetic fed-batch growth model, equations (8)-(16)",
    parameters="the paper's Table 2, loaded as fitted",
    time_scale="24 h fed-batch integration",
    assumptions=(
        "three initial conditions the paper does not state are declared by the "
        "graph and labelled as assumptions; reproduction_status is "
        "not_yet_validated"
    ),
)


_BAEZ_INSPECTION = Inspection(
    organism="E. coli W3110",
    context=(
        "5 L bioreactor, 37 degC, mineral medium; exponential glucose feed; the "
        "protein is induced by raising dissolved oxygen from 30% to 300% air "
        "saturation rather than by an inducer"
    ),
    inputs=(
        "mu_set, Y_XS, m and S_F as reported parameters; X_F, V_F, t_F and t as "
        "required run inputs with no printed value and no default"
    ),
    outputs=(
        "the feed rate F(t) in L/h, the two reported batch growth rates and the "
        "four reported fed-batch endpoint readings"
    ),
    units="L/h, L, g/L, g/g, g/(g h), 1/h, FU (fluorescence, a dimension of its own)",
    equations="one printed equation, the exponential feed rate; no growth law, no oxygen balance",
    parameters="four reported parameters; four unvalued run inputs",
    time_scale="fed-batch hours; the readings are endpoints, not a trajectory",
    assumptions=(
        "standalone and deliberately unregistered; it does not model growth, "
        "oxygen transfer or GFP expression, and offers no fluorescence-to-mass factor"
    ),
)

_LIN_INSPECTION = Inspection(
    organism=(
        "E. coli K12 W3110 and its lacIq derivative RB791; plasmids pDSCrimi or "
        "pKK177GlucC/pUBS520 were present but not induced"
    ),
    context=(
        "phosphate-buffered mineral salt medium (Teich et al. 1998), 15 L or 6 L "
        "Biostat ED, 7 L or 4 L working volume, 35 degC, pH 7.0, DOT above 20%, "
        "exponential then constant glucose feed"
    ),
    inputs=(
        "Table I's two culture columns plus five constants the paper does not "
        "value: cS, cO, kLa, DOT* and H"
    ),
    outputs=(
        "V, X, S, DOT, acetate and the enzyme ratios rS/rO, with subsidiary "
        "qS, qSox, qO, qScap, qOcap and mu"
    ),
    units="L, g/L, %, g/(g h), 1/h, mmol/(g h), mol C/g",
    equations=(
        "the Appendix's seven differential equations, the initial-value equations, "
        "the subsidiary chain with both correction branches, and the pulse method"
    ),
    parameters="Table I, 19 rows across two cultures, plus four protocol-dependent rows",
    time_scale="fed-batch hours; RK4 integration of the printed system",
    assumptions=(
        "standalone and unregistered; it reproduces no figure and no trajectory was "
        "digitised"
    ),
)

_NANCHEN_INSPECTION = Inspection(
    organism="E. coli MG1655 (F- rph-1), a non-recombinant K-12 strain",
    context=(
        "M9 minimal medium with 1 g/L glucose at pH 7.0; a 17 mL Hungate tube run "
        "at a 10 mL working volume in a water bath; 37 degC; steady-state "
        "continuous culture; dissolved oxygen above 70%"
    ),
    inputs="a specific growth rate mu, in 1/h",
    outputs=(
        "the specific glucose consumption rate q_glc in mmol gdw-1 h-1 and the "
        "biomass yield it implies in gdw/mol"
    ),
    units="1/h, mmol/(gdw h), gdw/mol",
    equations=(
        "Pirt's chemostat relation, printed as equation (3), and its inverse. The "
        "13C flux-ratio equations (1) and (2) are declared absent"
    ),
    parameters=(
        "mglc = 0.37 +/- 0.09 mmol gdw-1 h-1 and Yglc_max = 76 +/- 3 gdw mol-1, "
        "MG1655, this study"
    ),
    time_scale="steady state; there is nothing to integrate",
    assumptions="standalone and unregistered; the printed equation mixes mol and mmol, stated explicitly",
)

_SIMENSEN_INSPECTION = Inspection(
    organism="E. coli K-12 MG1655 (ATCC 700926), a non-recombinant K-12 strain",
    context=(
        "modified M9 minimal medium with 2% (w/v) glucose; 1 L in a 3 L Eppendorf "
        "New Brunswick BioFlo 115; batch; 37 degC; dissolved oxygen at or above "
        "40%; sampled during balanced exponential growth"
    ),
    inputs="none: it is a measured dataset, not a model with inputs",
    outputs=(
        "mass fractions in g gCDW-1 for 42 components across three printed columns, "
        "with standard deviations and printed non-numeric markers"
    ),
    units="g/g (g gCDW-1), and per cent for the prose coverage figure",
    equations="none: it is a table. The flux-variability comparison is declared absent",
    parameters="the measured values and their printed standard deviations",
    time_scale="one sampling instant during exponential growth; no dynamics",
    assumptions=(
        "standalone dataset, unregistered; the paper states that biomass "
        "composition is condition-dependent"
    ),
)


_MORRIS_STANCE = _stance("morris2011.material_balance")
_MORRIS_INSPECTION = Inspection(
    organism="none: Morris is a non-reacting control-volume engine, not an organism model",
    context=(
        "fully mixed, non-reacting control volumes. The only shipped example is a "
        "brass charge -> alloying chain of two instances"
    ),
    inputs="component masses, mass fractions and amounts on each control volume",
    outputs="conserved totals and component amounts, mass_flow with a declared time basis",
    units="kg, kmol, dimensionless fractions; a mass flow's unit carries its time basis",
    equations="accumulation = sum(inflow) - sum(outflow), with no reaction term",
    parameters="the per-instance component set and its declared modes",
    time_scale="no time dimension in the balance itself; a batch inventory",
    assumptions="non-reacting, and every entering unit attributable to a declared component",
)



#: The seven models, assessed against the insulin replay. Order is the brief's.
ASSESSMENTS: tuple[Assessment, ...] = (
    Assessment(
        key="zielinski",
        display_name="Zielinski 2019 -- recombinant human insulin process",
        role="baseline",
        classification=Classification.DYNAMICALLY_COMPOSABLE,
        contributes=True,
        summary=(
            "The baseline. This is the simulation every other model is assessed "
            "against: a 15-operation process graph from inoculum to RP-HPLC, run "
            "as an evidence replay of the paper's reported numbers."
        ),
        paper=TARGET_PAPER,
        paper_folder="Zielinski",
        package="Models/Zielinski",
        model_id=TARGET_MODEL,
        model_version=TARGET_MODEL_VERSION,
        inspection=_ZIELINSKI_INSPECTION,
        evidence=(
            "Models/Zielinski -- the process graph, its 196 ports and its "
            "evidence-record machinery.",
            "composition/replay/zielinski_replay.json -- the replay graph that "
            "carries the baseline.",
        ),
    ),
    Assessment(
        key="ganjave",
        display_name="Ganjave 2022 -- cybernetic fed-batch growth",
        role="candidate",
        classification=Classification.CONTEXTUALLY_RELEVANT,
        contributes=False,
        summary=(
            "A second E. coli fed-batch model, registered in this composition "
            "layer. It is not connected to the insulin process, and no rule in "
            "the project permits it to be."
        ),
        paper="Ganjave et al. (2022)",
        paper_folder="Ganjave",
        package="Models/Ganjave",
        model_id="ganjave",
        model_version="0.1.0",
        inspection=_GANJAVE_INSPECTION,
        cross_model_stance=_GANJAVE_STANCE[0],
        cross_model_evidence_basis=_GANJAVE_STANCE[1],
        blockers=(
            "Different substrate: glycerol plus a lumped complex substrate, fitted "
            "with one yield. Zielinski's carbon source is glucose in GMS medium.",
            "Different biomass basis: Ganjave's biomass is dry-cell weight; "
            "Zielinski reports wet biomass. No source here prints the factor "
            "between them.",
            "Different scale and mode: a 3 L vessel over 24 h of feeding, against "
            "a 4 L / 7.5 L reactor with pH-stat feeding.",
            "No port pair is permitted: every Zielinski <-> Ganjave pairing is "
            "mechanically legal and scientifically unsupported, so the policy "
            "fails closed.",
        ),
        evidence=(
            "composition/composition/cross_model.py -- the declared Ganjave <-> "
            "Zielinski position.",
            "Ganjave et al. (2022) eqs (8)-(16) and Table 2; Zielinski et al. "
            "(2019) sec. 2-3.",
            "composition/composition/adapters/ganjave_contract.py -- the model's "
            "own input contract.",
        ),
        remediation=(
            "A strain- and substrate-matched model declaring a shared component "
            "set, an explicit dry-to-wet biomass basis and a common medium. No "
            "such model exists here, and none is invented."
        ),
        evidence_check=(
            "Not evidence-compatible either: a Ganjave finding fails the project's "
            "identity rules on substrate, mode and scale before any number is "
            "compared."
        ),
    ),

    Assessment(
        key="morris",
        display_name="Morris 2011 -- non-reacting material balances",
        role="candidate",
        classification=Classification.INCOMPATIBLE,
        contributes=False,
        summary=(
            "A generic control-volume balance engine, not an organism model. It "
            "shares no quantity with the insulin process and cannot represent a "
            "reaction."
        ),
        paper="Morris, Geiger & Fine (2011)",
        paper_folder="Morris",
        package="Models/Morris",
        model_id="morris2011.material_balance",
        model_version="0.1.0",
        inspection=_MORRIS_INSPECTION,
        cross_model_stance=_MORRIS_STANCE[0],
        cross_model_evidence_basis=_MORRIS_STANCE[1],
        blockers=(
            "Zielinski publishes process roles, not conserved chemical entities: "
            "no stream of its own carries a component amount or a mass fraction.",
            "A Morris port must name a component, and the names cannot agree; a "
            "control-volume total would require every entering unit to be "
            "attributable to one, and it is not.",
            "The engine already refuses this boundary (component identity), so the "
            "position is enforced rather than merely declared.",
        ),
        evidence=(
            "Morris, Geiger & Fine (2011) Chapter 4: conservation with no reaction "
            "term.",
            "composition/composition/cross_model.py -- the declared Morris <-> "
            "Zielinski position, enforced by the engine.",
        ),
        remediation=(
            "Declare a component mapping explicitly, with a justification and a "
            "component-resolved reaction model behind it. Neither exists here."
        ),
        evidence_check=(
            "Not evidence-compatible: a balance is a method, not a measurement of "
            "this process, so it has no value to check."
        ),
    ),
    Assessment(
        key="baez",
        display_name="Baez 2014 -- oxygen-induced recombinant protein expression",
        role="candidate",
        classification=Classification.CONTEXTUALLY_RELEVANT,
        contributes=False,
        summary=(
            "Recombinant protein production in E. coli, induced by raising "
            "dissolved oxygen instead of by an inducer. Its expression mechanism "
            "is the opposite of the IPTG-induced pIBAINS process."
        ),
        paper="Baez, Majdalani & Shiloach (2014)",
        paper_folder="Baez",
        package="Models/Baez",
        inspection=_BAEZ_INSPECTION,
        blockers=(
            "Different strain (W3110) and a different construct.",
            "Different induction mechanism: the paper's product is driven by a "
            "dissolved-oxygen step to 300% air saturation; Zielinski induces with "
            "IPTG.",
            "Different operating policy: an exponential feed in a 5 L reactor at "
            "37 degC, against pH-stat feeding in a 4 L / 7.5 L reactor at 30 degC.",
            "No interface: the package is deliberately unregistered, publishes no "
            "ports and declares no supplyable quantity.",
        ),
        evidence=(
            "Models/Baez/README.md and manifest.json -- one printed feed equation, "
            "no growth or oxygen model, no fluorescence-to-mass factor.",
            "Baez et al. (2014) pp. 2-6; Zielinski et al. (2019) sec. 2.",
        ),
        remediation=(
            "Nothing available. Feeding Baez's F(t) into a pH-stat process would "
            "replace Zielinski's control law with another experiment's."
        ),
        evidence_check=(
            "Not evidence-compatible: the strain, construct, induction mode and "
            "scale all fail the project's identity dimensions."
        ),
    ),

    Assessment(
        key="lin",
        display_name="Lin 2001 -- maximum glucose and oxygen uptake capacities",
        role="candidate",
        classification=Classification.CONTEXTUALLY_RELEVANT,
        contributes=False,
        summary=(
            "A complete dynamic model of glucose-limited fed-batch E. coli, and "
            "the closest scientific neighbour of the insulin process: it models "
            "the declining uptake capacity that pH-stat feeding has to manage."
        ),
        paper="Lin et al. (2001)",
        paper_folder="Lin",
        package="Models/Lin",
        inspection=_LIN_INSPECTION,
        blockers=(
            "Different strain: K12 W3110 / RB791, with plasmids present but "
            "uninduced. Zielinski's culture is 20 IBA 1 carrying pIBAINS and "
            "producing insulin.",
            "Different medium, reactor and temperature: mineral salt medium, 15 L "
            "/ 6 L Biostat ED, 35 degC, against GMS, a 7.5 L Celligen 310 and "
            "30 degC.",
            "Its ports carry the state of its own culture (mu, qO, DOT, X, S). "
            "Handing those to Zielinski would transfer one experiment's state into "
            "another's.",
            "No interface: standalone and unregistered, with five constants the "
            "paper never values.",
        ),
        evidence=(
            "Models/Lin/README.md and MODEL_REPORT.md -- the Appendix's seven ODEs "
            "and Table I.",
            "composition/composition/cross_model.py -- the same class of refusal "
            "already declared for Zielinski <-> Ganjave, on the same grounds.",
        ),
        remediation=(
            "A W3110 / 20-IBA-1 matched uptake-capacity model would be a legitimate "
            "contributor. Re-parameterising Lin's numbers for Zielinski's strain "
            "would not be."
        ),
        evidence_check=(
            "Not evidence-compatible: the identity dimensions (strain, construct, "
            "medium, scale, temperature) fail, so even its reported capacities "
            "could not be entered as findings."
        ),
    ),
    Assessment(
        key="nanchen",
        display_name="Nanchen 2006 -- growth-rate-dependent maintenance and yield",
        role="candidate",
        classification=Classification.CONTEXTUALLY_RELEVANT,
        contributes=False,
        summary=(
            "Pirt's chemostat relation fitted to a non-recombinant MG1655 at steady "
            "state. Contextually relevant to fed-batch design, but a chemostat is "
            "not a fed batch and MG1655 is not the production strain."
        ),
        paper="Nanchen, Schicker & Sauer (2006)",
        paper_folder="nanchen",
        package="Models/nanchen",
        inspection=_NANCHEN_INSPECTION,
        blockers=(
            "Different strain: non-recombinant MG1655, not 20 IBA 1 / pIBAINS.",
            "Different mode: steady-state continuous culture, not a fed-batch "
            "trajectory with pH-stat feeding.",
            "Different scale and temperature: a 10 mL mini-scale chemostat at "
            "37 degC.",
            "Its maintenance coefficient and maximal yield are fitted for that "
            "chemostat and that medium. Transferring them would silently "
            "re-parameterise the insulin process.",
            "No interface: standalone and unregistered.",
        ),
        evidence=(
            "Models/nanchen/README.md and MODEL_REPORT.md -- equation (3) and "
            "Table 1, MG1655.",
            "Nanchen et al. (2006) p. 1167; Zielinski et al. (2019) sec. 2.1.",
        ),
        remediation=(
            "A maintenance/yield determination for 20 IBA 1 in GMS under pH-stat "
            "feeding would be a legitimate input. This paper is not that "
            "determination."
        ),
        evidence_check=(
            "Not evidence-compatible: the paper states that maintenance and yield "
            "depend on temperature, medium and strain, and all three differ."
        ),
    ),
    Assessment(
        key="simensen",
        display_name="Simensen 2022 -- measured E. coli biomass composition",
        role="candidate",
        classification=Classification.CONTEXTUALLY_RELEVANT,
        contributes=False,
        summary=(
            "A measured macromolecular composition of E. coli in g gCDW-1. It is a "
            "dataset, not a model: it has no inputs, no time and no dynamics, so "
            "forcing it into the graph would be misuse rather than composition."
        ),
        paper="Simensen et al. (2022)",
        paper_folder="Simensen",
        package="Models/Simensen",
        inspection=_SIMENSEN_INSPECTION,
        blockers=(
            "No shared quantity: Zielinski reports no biomass composition, and the "
            "dataset has no input port to receive one of its outputs.",
            "Different condition: MG1655 in M9 with 2% glucose at 37 degC, and the "
            "paper states that biomass composition is condition-dependent.",
            "It is a static table. A dataset cannot be executed as a dynamic "
            "component.",
        ),
        evidence=(
            "Models/Simensen/README.md and MODEL_REPORT.md -- Table 1 and its "
            "printed markers.",
            "Simensen et al. (2022) p. 9 (Table 1), p. 3 (condition), abstract "
            "(91.6% coverage).",
        ),
        remediation=(
            "It could become evidence-compatible if the target process declared a "
            "biomass-composition quantity and the condition matched. Neither "
            "holds, so no comparison is implemented: a cross-condition comparison "
            "would produce a number with no meaning."
        ),
        evidence_check=(
            "Not evidence-compatible as supplied: the condition differs, and no "
            "Zielinski output is a biomass composition to compare against."
        ),
    ),
)



#: Every key this module reports a problem under, in printed order.
PROBLEM_KEYS = (
    "duplicate_keys",
    "missing_baseline",
    "wrong_baseline",
    "unknown_classifications",
    "unexplained",
    "thin_evidence",
    "unsupported_contributions",
    "baseline_with_blockers",
    "registered_without_stance",
    "stance_disagrees_with_cross_model",
    "unregistered_with_stance",
    "unknown_paper_folders",
    "registered_models_not_assessed",
    "candidates_without_evidence_check",
)

CLASSIFICATION_VALUES = tuple(c.value for c in Classification)


def assessments() -> tuple[Assessment, ...]:
    return ASSESSMENTS


def by_key(key: str) -> Assessment:
    for assessment in ASSESSMENTS:
        if assessment.key == key:
            return assessment
    raise KeyError(f"no assessment for {key!r}")


def target() -> Assessment:
    """The baseline assessment."""
    baselines = [a for a in ASSESSMENTS if a.is_baseline]
    if len(baselines) != 1:
        raise LookupError(
            f"expected exactly one baseline assessment, found {len(baselines)}"
        )
    return baselines[0]


def contributors() -> tuple[Assessment, ...]:
    """Models that take part in the executable simulation."""
    return tuple(a for a in ASSESSMENTS if a.contributes)


def evidence_only() -> tuple[Assessment, ...]:
    """Assessed models that are not executable components of this simulation."""
    return tuple(a for a in ASSESSMENTS if not a.contributes)


def permitted_connections() -> list[dict[str, Any]]:
    """The dynamic connections this repository permits, read from ``cross_model``.

    Deliberately not a curated list: it is every boundary the compatibility
    engine allows. If one were added or withdrawn there, this answer changes.
    """
    out: list[dict[str, Any]] = []
    for boundary in cross_model.BOUNDARIES:
        if not boundary.permitted:
            continue
        out.append(
            {
                "source_model": boundary.source_model,
                "target_model": boundary.target_model,
                "stance": boundary.stance,
                "quantity_pairs": [list(pair) for pair in boundary.rules],
                "assumptions": list(boundary.assumptions),
                "evidence": list(boundary.evidence),
                "unresolved": list(boundary.unresolved),
                "touches_target": TARGET_MODEL in (
                    boundary.source_model, boundary.target_model
                ),
            }
        )
    return out


def summary() -> dict[str, Any]:
    """Counts and the two lists a panel needs first."""
    counts = {value: 0 for value in CLASSIFICATION_VALUES}
    for assessment in ASSESSMENTS:
        counts[assessment.classification.value] += 1
    touching = [c for c in permitted_connections() if c["touches_target"]]
    return {
        "assessed": len(ASSESSMENTS),
        "counts": counts,
        "baseline": [a.key for a in ASSESSMENTS if a.is_baseline],
        "contributors": [a.key for a in contributors()],
        "evidence_only": [a.key for a in evidence_only()],
        "permitted_connections": len(permitted_connections()),
        "connections_touching_target": touching,
    }



def problems() -> dict[str, list[str]]:
    """Every way the assessment and the tree disagree."""
    from .adapters import REGISTRATIONS

    keys = [a.key for a in ASSESSMENTS]
    duplicate_keys = sorted({k for k in keys if keys.count(k) > 1})
    baselines = [a for a in ASSESSMENTS if a.is_baseline]
    corpus_folders = {paper.folder for paper in paper_index.PAPERS}
    registered_ids = {reg.model_id for reg in REGISTRATIONS}

    missing_baseline = (
        ["no assessment is marked as the baseline"] if not baselines else []
    )
    wrong_baseline = [
        f"the baseline is {b.key!r}, not {TARGET_MODEL!r}"
        for b in baselines
        if b.model_id != TARGET_MODEL
    ]
    unknown_classifications = sorted({
        a.classification.value
        for a in ASSESSMENTS
        if a.classification.value not in CLASSIFICATION_VALUES
    })
    unexplained = [
        a.key for a in ASSESSMENTS if not a.summary.strip() or not a.evidence
    ]
    thin_evidence = [a.key for a in ASSESSMENTS if len(a.evidence) < 2]
    unsupported_contributions = [
        a.key
        for a in ASSESSMENTS
        if a.contributes and not a.is_baseline
        and not any(
            c["touches_target"]
            and a.model_id in (c["source_model"], c["target_model"])
            for c in permitted_connections()
        )
    ]
    baseline_with_blockers = [a.key for a in baselines if a.blockers]

    registered_without_stance: list[str] = []
    stance_disagrees: list[str] = []
    unregistered_with_stance: list[str] = []
    for a in ASSESSMENTS:
        if a.is_baseline:
            # The baseline is the target, not a candidate; the self-boundary
            # cross_model declares for Zielinski says it has no supplyable port,
            # which is a statement about composing Zielinski with itself.
            continue
        if a.registered:
            boundary = _boundary_between(a.model_id)
            if boundary is None:
                registered_without_stance.append(a.key)
                continue
            if a.cross_model_stance != boundary.stance:
                stance_disagrees.append(
                    f"{a.key}: assessment says {a.cross_model_stance!r}, "
                    f"cross_model says {boundary.stance!r}"
                )
        elif a.cross_model_stance:
            unregistered_with_stance.append(a.key)

    not_registered = sorted(
        f"{a.key} claims {a.model_id} but it is not registered"
        for a in ASSESSMENTS
        if a.registered and a.model_id not in registered_ids
    )
    return {
        "duplicate_keys": duplicate_keys,
        "missing_baseline": missing_baseline,
        "wrong_baseline": wrong_baseline,
        "unknown_classifications": unknown_classifications,
        "unexplained": unexplained,
        "thin_evidence": thin_evidence,
        "unsupported_contributions": unsupported_contributions,
        "baseline_with_blockers": baseline_with_blockers,
        "registered_without_stance": registered_without_stance,
        "stance_disagrees_with_cross_model": stance_disagrees,
        "unregistered_with_stance": unregistered_with_stance,
        "unknown_paper_folders": sorted({
            a.paper_folder
            for a in ASSESSMENTS
            if a.paper_folder not in corpus_folders
        }),
        "registered_models_not_assessed": sorted(
            registered_ids - {a.model_id for a in ASSESSMENTS if a.registered}
        ) + not_registered,
        "candidates_without_evidence_check": [
            a.key for a in ASSESSMENTS if not a.is_baseline and not a.evidence_check
        ],
    }


def problem_messages(report: dict[str, list[str]]) -> list[str]:
    return [f"{key}: {item}" for key in PROBLEM_KEYS for item in report[key]]



def describe() -> dict[str, Any]:
    """The whole assessment, as one document the editor renders."""
    touching = [c for c in permitted_connections() if c["touches_target"]]
    return {
        "contract_version": "0.1.0",
        "target": {
            "model_id": TARGET_MODEL,
            "model_version": TARGET_MODEL_VERSION,
            "paper": TARGET_PAPER,
            "process": TARGET_PROCESS,
        },
        "claim_scope": (
            "Each classification is a judgement about whether a model may take "
            "part in this simulation, on its equations, units, parameters and "
            "operating context. A shared variable name or a shared organism is "
            "never sufficient. Composition is not validation: no model here gains "
            "reproduction status by being assessed."
        ),
        "assessments": [a.to_dict() for a in ASSESSMENTS],
        "summary": summary(),
        "connections": {
            "permitted": permitted_connections(),
            "touching_target": touching,
            "note": (
                "A connection is dynamic only when the engine's own rules and the "
                "declared cross-model position both permit it. No connection "
                "touches the insulin process, so the replay composes no upstream "
                "model; the models above are assessed, not attached."
            ),
        },
    }


def compare_runs(
    baseline: Any,
    composed: Any,
    *,
    baseline_instance: str,
    composed_instance: str,
) -> dict[str, Any]:
    """Compare one instance's outputs across two executed graphs, values only.

    Why values and not the whole output document: the instance id is part of
    every output's ``ref`` and of its provenance record, so two runs of the *same*
    model under *different instance names* differ there by construction. Those
    fields are attribution. Everything else -- state, value, unit, quantity -- must
    be identical, and this function reports exactly which ports, if any, are not.
    """

    def outputs(payload: Any, instance_id: str) -> dict[str, dict[str, Any]]:
        for result in (payload or {}).get("results", ()) or ():
            if result.get("instance_id") != instance_id:
                continue
            return {
                out["ref"]["port_id"]: {
                    "state": out.get("state"),
                    "value": out.get("value"),
                    "unit": out.get("unit"),
                    "quantity": out.get("quantity"),
                }
                for out in result.get("outputs", ()) or ()
            }
        return {}

    base = outputs(baseline, baseline_instance)
    comp = outputs(composed, composed_instance)
    differing = sorted(
        port for port in set(base) | set(comp) if base.get(port) != comp.get(port)
    )
    return {
        "baseline_instance": baseline_instance,
        "composed_instance": composed_instance,
        "baseline_ports": len(base),
        "composed_ports": len(comp),
        "fields_compared": ["state", "value", "unit", "quantity"],
        "fields_excluded_as_attribution": ["ref", "provenance_chain"],
        "differing_ports": differing,
        "identical": (not differing) and bool(base) and set(base) == set(comp),
        "note": (
            "Two runs of the same model under different instance names differ in "
            "their ref and provenance records by construction. Compared on values, "
            "they must be identical; a difference here would mean the extra "
            "instance changed the baseline, which is the thing composition must "
            "never do."
        ),
    }


def paper_for_model(model_id: str) -> Assessment | None:
    """The assessment that names `model_id`, or ``None``."""
    if not model_id:
        return None
    for assessment in ASSESSMENTS:
        if assessment.model_id == model_id:
            return assessment
    return None


def compose_block(results: Any) -> dict[str, Any]:
    """Per-instance attribution for one executed graph.

    This is what lets a composed run say *which model produced which output*, and
    what each of them is: the baseline, a contributing model, or a model that is
    co-executed only because it is independently runnable.

    The block never claims that two instances are connected. Whether they are is
    the engine's answer, carried in the run's own results and connection
    assessments; this block states what each instance *is*.
    """
    instances: list[dict[str, Any]] = []
    for result in results or ():
        model_id = str(result.get("model_id", ""))
        assessment = paper_for_model(model_id)
        outputs = result.get("outputs") or ()
        instances.append(
            {
                "instance_id": str(result.get("instance_id", "")),
                "model_id": model_id,
                "model_version": str(result.get("model_version", "")),
                "paper": assessment.paper if assessment else "",
                "paper_folder": assessment.paper_folder if assessment else "",
                "role": assessment.role if assessment else "",
                "classification": (
                    assessment.classification.value if assessment else ""
                ),
                "classification_label": (
                    assessment.classification_label if assessment else ""
                ),
                "contributes": bool(assessment.contributes) if assessment else False,
                "output_count": len(outputs),
                "attributed": assessment is not None,
            }
        )
    return {
        "target": {
            "model_id": TARGET_MODEL,
            "model_version": TARGET_MODEL_VERSION,
            "paper": TARGET_PAPER,
            "process": TARGET_PROCESS,
        },
        "instances": instances,
        "summary": summary(),
        "cross_model_links": permitted_connections(),
        "note": (
            "Each instance is attributed to the paper that encodes it. No "
            "cross-model connection touches the insulin process, so a graph that "
            "runs more than one model is co-executing independently runnable "
            "models, not feeding one into another. Attribution is not "
            "composition, and composition is not validation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m composition.compatibility",
        description=(
            "Assess every model in the project against the Zielinski insulin "
            "simulation: what may contribute, what may not, and why."
        ),
    )
    parser.add_argument("--check", action="store_true",
                        help="fail when the assessment and the tree disagree")
    parser.add_argument("--json", action="store_true",
                        help="print the whole assessment as JSON")
    args = parser.parse_args(argv)

    report = problems()
    failures = problem_messages(report)

    if args.json:
        payload = describe()
        payload["problems"] = failures
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 1 if (args.check and failures) else 0

    counts = summary()
    print(f"target: {TARGET_MODEL}@{TARGET_MODEL_VERSION} ({TARGET_PAPER})")
    print(f"assessed: {counts['assessed']} models")
    for value in CLASSIFICATION_VALUES:
        number, label = CLASSIFICATION_LABELS[value]
        n = counts["counts"][value]
        if n:
            print(f"  {number}. {label:40s} {n}")
    print(f"contributors: {', '.join(counts['contributors'])}")
    print(f"not contributing: {', '.join(counts['evidence_only'])}")
    print(
        "permitted dynamic connections: "
        f"{counts['permitted_connections']} "
        f"(touching the target: {len(counts['connections_touching_target'])})"
    )
    for failure in failures:
        print(("FAIL " if args.check else "NOTE ") + failure)
    if args.check:
        if failures:
            return 1
        print(
            "PASS -- every model is assessed, and no connection is claimed that "
            "the engine does not permit"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

