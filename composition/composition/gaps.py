"""Scientific gaps in the Zielinski insulin simulation, and what would close them.

This module answers one question for the target process:

    what scientific knowledge is missing before this simulation can be more
    accurate, and what does the project's own literature library already
    contribute?

It is a *reader*, not a rule engine. The gaps come from the model's own
declared ``missing_parameters`` and ``assumptions`` in
``Models/Zielinski/out/graph.json``; the papers, their classifications and
their blockers come from :mod:`composition.compatibility`; the corpus records
come from :mod:`composition.evidence.papers`; and the project's existing
literature investigation is reused from :mod:`composition.evidence.catalogue`.

Nothing here invents a parameter, a value, a requirement or a compatibility
verdict. A paper that is relevant to a gap is not upgraded: its classification
is copied from :mod:`composition.compatibility` unchanged. A gap is marked
``addressed`` only when an assessment explicitly supplies the missing evidence
for the target context, and no assessment does that today.

The output is a deterministic JSON document with a digest, so the same model
records always produce the same analysis. ``python -m composition.gaps --check``
fails when a gap loses its evidence, a recommendation disappears, or a paper's
classification stops agreeing with the compatibility assessment.

## The seven gap classes

``model_parameters``          a number the equations need and the model does not have
``experimental_measurements``  an observation or calibration the process lacks
``biological_context``        organism, strain or construct context that does not match
``process_conditions``        temperature, pH, medium, feeding or reactor information
``mathematical_relationships`` a governing equation or rate law that is absent
``independent_validation``    evidence that the process reproduces independently
``composition_blockers``      missing information that prevents a legitimate connection

Every gap names the Zielinski variables or components it affects, the existing
record that makes it visible, the evidence that is missing, literature search
terms, and whether closing it could enable composition or improve validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import compatibility

#: Repository root: this file is <root>/composition/composition/gaps.py
ROOT = Path(__file__).resolve().parents[2]

MODEL_GRAPH = ROOT / "Models/Zielinski/out/graph.json"
MODEL_REPORT = ROOT / "Models/Zielinski/MODEL_REPORT.md"
MODEL_SUMMARY = ROOT / "Models/Zielinski/out/run_summary.md"
MODEL_SOURCE = ROOT / "Models/Zielinski/models/zielinski_2019.py"
COMPATIBILITY_SOURCE = ROOT / "composition/composition/compatibility.py"
PAPERS_SOURCE = ROOT / "composition/composition/evidence/papers.py"
EVIDENCE_SOURCE = ROOT / "composition/composition/evidence/catalogue.py"

CONTRACT_VERSION = "0.1.0"

#: The target this analysis is about. Read from the compatibility assessment so
#: the two modules cannot name different processes.
TARGET_MODEL = compatibility.TARGET_MODEL
TARGET_MODEL_VERSION = compatibility.TARGET_MODEL_VERSION
TARGET_PAPER = compatibility.TARGET_PAPER
TARGET_PROCESS = compatibility.TARGET_PROCESS

#: The seven classes the brief asks for, in its order.
CATEGORIES: tuple[dict[str, str], ...] = (
    {
        "id": "model_parameters",
        "title": "Model parameters",
        "question": "Which numbers do the equations need that the model does not have?",
    },
    {
        "id": "experimental_measurements",
        "title": "Experimental measurements",
        "question": "Which observations or calibrations does the process lack?",
    },
    {
        "id": "biological_context",
        "title": "Biological context",
        "question": "Is the organism, strain and construct the same as the target?",
    },
    {
        "id": "process_conditions",
        "title": "Process conditions",
        "question": "Are temperature, pH, medium, feeding and reactor configuration reported?",
    },
    {
        "id": "mathematical_relationships",
        "title": "Mathematical relationships",
        "question": "Which governing equations or rate laws are absent?",
    },
    {
        "id": "independent_validation",
        "title": "Independent experimental validation",
        "question": "Is there evidence that this process reproduces outside one batch?",
    },
    {
        "id": "composition_blockers",
        "title": "Missing information preventing composition",
        "question": "What prevents a legitimate model connection?",
    },
)

CATEGORY_IDS = tuple(category["id"] for category in CATEGORIES)
CATEGORY_TITLES = {category["id"]: category["title"] for category in CATEGORIES}

#: Stable identifiers for the three gaps that are not a single missing parameter.
GAP_BIOLOGICAL_CONTEXT = "GAP-BIOLOGICAL-CONTEXT"
GAP_INDEPENDENT_VALIDATION = "GAP-INDEPENDENT-VALIDATION"
GAP_COMPOSITION_BOUNDARY = "GAP-COMPOSITION-BOUNDARY"


#: Authored explanation for each declared Zielinski missing parameter.
#:
#: The *facts* (the parameter id, its reason, the node and the blocked targets)
#: are read from the model graph at analysis time. These entries supply the
#: category, the practical consequence, the evidence that would close the gap
#: and the search terms. Keeping them keyed by parameter id means a rename in
#: the model shows up as a missing template rather than silently reusing an
#: explanation for a different parameter.
PARAMETER_TEMPLATES: dict[str, dict[str, Any]] = {
    "MP-GROWTH-KINETICS": {
        "title": "No growth or substrate-uptake parameters for the insulin batch",
        "category": "model_parameters",
        "why_it_matters": (
            "The replay can restate the published OD600 curve, but no equation "
            "can compute OD600 from the operating conditions. Without growth and "
            "uptake parameters the simulation cannot answer a new batch or a "
            "scale question; it can only repeat the single published batch."
        ),
        "missing_evidence": [
            "A specific growth rate measured for E. coli 20 IBA 1 carrying "
            "pIBAINS, with the medium and feeding policy that produced it.",
            "Glucose saturation and maintenance parameters for the same strain, "
            "medium and fed-batch mode, with the fitting procedure stated.",
            "The numerical pH-stat feed law actually used: set point, dead band, "
            "pump rate or a reported feed-volume time course.",
        ],
        "search_terms": [
            '"Escherichia coli 20 IBA 1" growth rate',
            '"pIBAINS" fed-batch growth kinetics',
            '"GMS medium" "Escherichia coli" glucose',
            '"pH-stat" glucose feeding "Escherichia coli" specific growth rate',
            '"Escherichia coli" maintenance coefficient "GMS medium"',
        ],
        "composition_enabling": True,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "Target-context growth and glucose-uptake parameters, or the raw "
                "time series needed to estimate them.",
            ],
            "why_it_is_needed": (
                "The model declares MP-GROWTH-KINETICS as the reason it cannot "
                "compute OD600, wet biomass or glucose consumption from inputs. "
                "A relationship from another strain or medium would transfer "
                "parameters across experiments and is refused by the identity "
                "rules in composition.evidence.sourcing."
            ),
            "suitable_paper_must_report": [
                "The host strain (E. coli 20 IBA 1 or an explicit CSH50R derivative) "
                "and the plasmid pIBAINS.",
                "GMS medium, the glucose/proline feed strategy and the pH-stat "
                "control settings.",
                "Either a fitted growth/uptake model with its parameters and "
                "fitting method, or the raw OD600, glucose and feed-volume series.",
            ],
            "what_scaleup_can_do": (
                "Register the reported relationship as a candidate finding, run "
                "the existing identity comparison against the target passages, "
                "and only then consider declaring a port. No classification is "
                "upgraded by relevance alone."
            ),
        },
        "catalogue_target": "node:N01#specific_growth_rate",
    },
    "MP-OXYGEN-TRANSFER": {
        "title": "No oxygen-transfer or oxygen-uptake relationship for the fermenter",
        "category": "mathematical_relationships",
        "why_it_matters": (
            "The replay cannot say whether growth was oxygen limited. Without a "
            "transfer/uptake relationship, any growth model attached to this "
            "process could fail for an unobserved reason, and no scale-up "
            "extrapolation is defensible."
        ),
        "missing_evidence": [
            "A measured kLa, oxygen-uptake rate (OUR) or oxygen-transfer rate "
            "(OTR) at the target reactor scale and operating point.",
            "Air flow, agitation, sparger configuration and the dissolved-oxygen "
            "set point or trace for the 4 L / 7.5 L Bioflo Celligen 310 run.",
            "Oxygen solubility and the medium properties needed to convert a "
            "measured transfer coefficient into a dissolved-oxygen prediction.",
        ],
        "search_terms": [
            '"Escherichia coli" "kLa" "7.5 L" bioreactor',
            '"oxygen transfer" "pH-stat" "Escherichia coli"',
            '"OUR" "OTR" "Escherichia coli" fed-batch "dissolved oxygen"',
            '"Bioflo Celligen" "kLa" "Escherichia coli"',
            '"dissolved oxygen" "recombinant insulin" "Escherichia coli"',
        ],
        "composition_enabling": True,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A transfer/uptake relationship measured under the target "
                "reactor's hydrodynamics, not a correlation borrowed from a "
                "different vessel.",
            ],
            "why_it_is_needed": (
                "MP-OXYGEN-TRANSFER blocks dissolved_oxygen_profile and "
                "specific_growth_rate_mu_max. The project's existing evidence "
                "catalogue records that no candidate examined supplies a "
                "dissolved-oxygen measurement under matching conditions."
            ),
            "suitable_paper_must_report": [
                "The same strain, medium and fed-batch mode, or a clear statement "
                "that the correlation is geometry-specific and why it transfers.",
                "Air flow, agitation, sparger geometry and dissolved-oxygen "
                "measurements over time.",
                "kLa, OUR or OTR with the measurement method and uncertainty.",
            ],
            "what_scaleup_can_do": (
                "Record the correlation as context-tagged evidence, compare its "
                "conditions against the target passages, and expose the residual "
                "against the dissolved-oxygen target without changing the replay."
            ),
        },
        "catalogue_target": "node:N01#dissolved_oxygen",
    },
    "MP-CULTURE-MEDIUM": {
        "title": "GMS medium composition is cited, not enumerated",
        "category": "process_conditions",
        "why_it_matters": (
            "No growth or substrate balance can be closed without the medium's "
            "initial glucose, nitrogen, phosphate and trace-element "
            "concentrations. The paper points to WO96/20724 A1 instead of "
            "printing the recipe."
        ),
        "missing_evidence": [
            "The full GMS medium composition, including glucose, nitrogen, "
            "phosphate, trace elements and the proline/thiamine/tetracycline "
            "supplements used for the inoculum.",
            "The 40% glucose and 12 mg/mL proline feed-solution composition and "
            "the concentrations actually delivered.",
            "Which medium components were measured, and how the 70-120 mg/dL and "
            "30-50 mg/dL glucose bands were maintained.",
        ],
        "search_terms": [
            '"GMS medium" "Escherichia coli" composition',
            '"GMS medium" glucose proline "Escherichia coli 20"',
            '"WO9620724" GMS medium composition',
            '"pH-stat" "GMS medium" "Escherichia coli"',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "An enumerated GMS recipe or a measurement of the medium's "
                "substrate concentrations in this exact process.",
            ],
            "why_it_is_needed": (
                "MP-CULTURE-MEDIUM blocks glucose_initial_concentration and "
                "nutrient_balance. A medium from a different E. coli process "
                "cannot be substituted without changing the experiment."
            ),
            "suitable_paper_must_report": [
                "The complete GMS recipe, or an explicit citation to an "
                "enumerated formulation plus the supplements used.",
                "Glucose and proline concentrations in the batch and feed.",
                "The strain and process context in which the recipe was used.",
            ],
            "what_scaleup_can_do": (
                "Attach the recipe as a source-qualified evidence record and "
                "check whether every component name and concentration has a "
                "target-context match before any balance is attempted."
            ),
        },
    },
    "MP-INDUCTION-TIME": {
        "title": "The time of induction is not reported and cannot be recovered",
        "category": "process_conditions",
        "why_it_matters": (
            "The growth phase and the insulin-production phase cannot be "
            "separated. The model already records a source discrepancy: the "
            "narrative order cannot be reconciled with Fig. 3, and induction "
            "may have preceded the glucose limitation."
        ),
        "missing_evidence": [
            "The induction time and OD600 at induction, or the rule that "
            "triggered it, for the reported batch.",
            "The IPTG concentration and the post-induction duration actually "
            "used, if induction was chemical rather than DO-triggered.",
            "An independent record that resolves the ordering conflict between "
            "section 2.4 and Fig. 3.",
        ],
        "search_terms": [
            '"Escherichia coli 20" "pIBAINS" IPTG induction OD600',
            '"recombinant insulin" "Escherichia coli" induction time fed-batch',
            '"pH-stat" induction "Escherichia coli" OD600',
            'Zielinski insulin 2019 induction optical density',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A primary record of when induction happened in this process, "
                "or enough time-resolved product data to identify the transition.",
            ],
            "why_it_is_needed": (
                "MP-INDUCTION-TIME blocks induction_time_h and "
                "post_induction_start_h. Guessing it would silently change the "
                "meaning of the growth and production phases."
            ),
            "suitable_paper_must_report": [
                "The same host/vector/medium and the induction trigger.",
                "Induction time or OD600, IPTG concentration and post-induction "
                "duration.",
                "Enough detail to tell whether induction preceded or followed "
                "the pH-stat glucose limitation.",
            ],
            "what_scaleup_can_do": (
                "Store the induction record with its context, re-run the "
                "existing source-discrepancy check, and keep the conflict "
                "visible rather than resolving it by assumption."
            ),
        },
        "catalogue_target": "node:N01#induction_time",
    },
    "MP-HOMOGENIZER": {
        "title": "Homogenizer pressure and pass count are not reported",
        "category": "process_conditions",
        "why_it_matters": (
            "Lysis efficiency cannot be predicted or checked. The model knows "
            "the operation happened but not the mechanical energy that determined "
            "how much inclusion-body protein was released."
        ),
        "missing_evidence": [
            "Homogenizer pressure, valve setting or pass count used for the "
            "E. coli 20 IBA 1 cell suspension.",
            "Lysis efficiency measured by protein release, cell disruption or "
            "inclusion-body recovery in this process.",
        ],
        "search_terms": [
            '"high-pressure homogenizer" "Escherichia coli" inclusion bodies pressure passes',
            '"Escherichia coli 20" lysis inclusion bodies',
            '"inclusion body" recovery "homogenizer" "Escherichia coli"',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A lysis record for this process, or a measured lysis/recovery "
                "efficiency that can be attached to the operation.",
            ],
            "why_it_is_needed": (
                "MP-HOMOGENIZER blocks lysis_efficiency, so the model cannot "
                "connect the harvested biomass to the inclusion bodies actually "
                "released without inventing a recovery."
            ),
            "suitable_paper_must_report": [
                "The same strain and inclusion-body system, or a clearly stated "
                "reason the mechanical treatment transfers.",
                "Pressure, pass count and temperature.",
                "Measured lysis or inclusion-body recovery with its assay.",
            ],
            "what_scaleup_can_do": (
                "Attach the measured recovery to the lysis operation as a "
                "context-tagged value and show its effect separately from the "
                "published replay."
            ),
        },
    },
    "MP-DISSOLUTION-VOLUME": {
        "title": "The dissolution buffer volume is missing",
        "category": "model_parameters",
        "why_it_matters": (
            "The dissolved protein concentration cannot be computed. The paper "
            "reports 5460 AU after dissolving a 17.9 g inclusion-body aliquot, "
            "but without a volume the AU reading cannot become a concentration."
        ),
        "missing_evidence": [
            "The buffer volume used to dissolve the 17.9 g inclusion-body "
            "aliquot, or the final solution volume.",
            "A measured protein concentration or an A280 value with a stated "
            "path length for the dissolved inclusion-body solution.",
            "The mass of buffer salts and the pH adjustment volume, if they "
            "change the final volume.",
        ],
        "search_terms": [
            '"inclusion bodies" dissolution volume "Escherichia coli" insulin',
            '"NaHCO3" "EDTA" inclusion bodies dissolution',
            '"17.9 g" inclusion bodies dissolution insulin',
            '"A280" dissolved inclusion bodies concentration',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "The missing volume, or a concentration measurement that makes "
                "the reported AU interpretable.",
            ],
            "why_it_is_needed": (
                "MP-DISSOLUTION-VOLUME blocks dissolved_protein_concentration. "
                "Supplying a volume from a different protocol would change the "
                "concentration the paper implies."
            ),
            "suitable_paper_must_report": [
                "The same inclusion-body isolation and dissolution protocol.",
                "The buffer composition, its volume and the final solution volume.",
                "A concentration, A280 with path length, or mass balance that "
                "closes the reported AU.",
            ],
            "what_scaleup_can_do": (
                "Record the volume as a protocol parameter, recompute the "
                "concentration transparently, and leave the original AU value "
                "untouched."
            ),
        },
    },
    "MP-AU-CALIBRATION": {
        "title": "Absorbance units cannot be converted to insulin mass or activity",
        "category": "experimental_measurements",
        "why_it_matters": (
            "Every downstream mass, recovery and activity claim depends on an "
            "AU-to-mass conversion that does not exist. The paper calibrated the "
            "spectrophotometer with water and reports no path length or "
            "extinction coefficient, so the AU scale is instrument-relative."
        ),
        "missing_evidence": [
            "The calibration standard, path length and extinction coefficient "
            "used to convert A280 or AU into protein mass.",
            "An AU-to-mass or AU-to-IU conversion measured for this insulin "
            "construct and matrix, with its uncertainty.",
            "The assay that produced the reported IU/L activity and its "
            "relationship, if any, to the AU measurements.",
        ],
        "search_terms": [
            '"A280" insulin extinction coefficient',
            '"absorbance units" insulin calibration "Escherichia coli"',
            '"RP-HPLC" insulin quantification absorbance units',
            '"insulin" "IU" "A280" conversion',
            '"recombinant human insulin" quantification "AU"',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A documented calibration from the absorbance scale used in "
                "this process to protein mass or IU.",
            ],
            "why_it_is_needed": (
                "MP-AU-CALIBRATION blocks insulin_mass_from_au, "
                "stage_recovery_percent and final_activity_from_au. Without it "
                "the model can compare AU values but cannot claim a mass yield."
            ),
            "suitable_paper_must_report": [
                "The same insulin construct and sample matrix, or a standard "
                "that is explicitly applicable.",
                "Path length, wavelength, extinction coefficient and standard "
                "curve.",
                "The link between the AU measurement and the activity assay.",
            ],
            "what_scaleup_can_do": (
                "Store the calibration as a separate evidence record and apply "
                "it only in a labelled calculation; the replay's reported AU "
                "values remain reported, not converted."
            ),
        },
    },
    "MP-A280-SOLUTION": {
        "title": "The A280 values and path length needed by two printed formulas are absent",
        "category": "experimental_measurements",
        "why_it_matters": (
            "The citraconylation and trypsin dosing formulas require A280nm, but "
            "the paper reports neither the A280 of any solution nor the cuvette "
            "path length. Two printed formulas therefore cannot be executed."
        ),
        "missing_evidence": [
            "The A280 of the citraconylated solution and of the trypsin-treated "
            "solution, with the wavelength and path length.",
            "The dilution or concentration step applied before each absorbance "
            "reading.",
            "A measured protein concentration that can replace the ambiguous "
            "absorbance term in the printed formulas.",
        ],
        "search_terms": [
            '"A280" path length citraconylation insulin',
            '"trypsin" "A280" insulin precursor',
            '"citraconic anhydride" insulin A280 volume',
            '"insulin" "trypsin" absorbance units dosing',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A280 readings with their path length, or a concentration "
                "measurement that makes the printed dosing rules executable.",
            ],
            "why_it_is_needed": (
                "MP-A280-SOLUTION blocks citraconic_anhydride_volume_from_formula "
                "and trypsin_volume_from_formula. The model already refuses "
                "these equations rather than guessing the missing term."
            ),
            "suitable_paper_must_report": [
                "The same citraconylation and trypsinization steps.",
                "A280 values, wavelength, path length and any dilution.",
                "Enough detail to reproduce the reagent volume from the printed "
                "formula.",
            ],
            "what_scaleup_can_do": (
                "Record the measurement and re-run the two refused equations "
                "with traceable inputs, keeping the original refusal visible "
                "until the input is actually supplied."
            ),
        },
    },
    "MP-FOLDING-MODEL": {
        "title": "No renaturation rate or yield relationship exists",
        "category": "mathematical_relationships",
        "why_it_matters": (
            "Two yields at two temperatures cannot define a yield function, and "
            "the paper itself says refolding depends on redox potential and pH "
            "but not on temperature. A temperature-driven model would contradict "
            "the source it is built from."
        ),
        "missing_evidence": [
            "Time-resolved renaturation yield and aggregate fraction under the "
            "reported buffer, redox potential and pH.",
            "A rate law or fitted kinetic model with its parameters and fitting "
            "procedure, not two endpoint yields.",
            "The relationship between the 5460 AU after dissolution and the "
            "5450 AU after renaturation, and the basis of the reported 95-96% "
            "and ~99% yields.",
        ],
        "search_terms": [
            '"insulin" renaturation kinetics redox pH',
            '"inclusion bodies" refolding yield time course "Escherichia coli"',
            '"insulin precursor" refolding aggregate fraction',
            '"recombinant insulin" renaturation 18 h yield',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A time-resolved renaturation data set or a printed rate law for "
                "this insulin precursor and buffer system.",
            ],
            "why_it_is_needed": (
                "MP-FOLDING-MODEL blocks refolding_yield_predictive and "
                "refolding_time_predictive. The model keeps the two reported "
                "yields as observations rather than inventing a function."
            ),
            "suitable_paper_must_report": [
                "The same precursor, redox system, pH and temperature range.",
                "Yield and aggregate fraction over time, with replicates.",
                "A rate law or the data needed to fit one, including the "
                "fitting method and uncertainty.",
            ],
            "what_scaleup_can_do": (
                "Register the kinetic model as a candidate, compare its buffer "
                "and redox conditions with the target, and keep the existing "
                "source discrepancy about the reported yields visible."
            ),
        },
    },
}


def gap_id_for_parameter(parameter_id: str) -> str:
    """The stable gap id for a declared missing parameter."""
    return "GAP-" + parameter_id


#: How each assessed paper relates to each gap.
#:
#: ``partially_addresses`` is used only when the paper contributes a value,
#: relationship or measurement to the gap. It never means the gap is resolved:
#: ``remains_missing`` must always say what is still absent. ``relevant_context``
#: marks a paper that shares the phenomenon but cannot supply target-context
#: evidence. The classification itself is never stored here; it is read from
#: :mod:`composition.compatibility`.
PAPER_GAP_LINKS: dict[str, dict[str, dict[str, str]]] = {
    "ganjave": {
        "GAP-MP-GROWTH-KINETICS": {
            "relation": "partially_addresses",
            "contribution": (
                "A cybernetic fed-batch growth model with equations (8)-(16) and "
                "a fitted Table 2, including biomass, glycerol, complex substrate, "
                "dissolved oxygen and volume states."
            ),
            "remains_missing": (
                "It is fitted for glycerol plus a lumped complex substrate in a "
                "3 L vessel over 24 h, not for glucose in GMS under pH-stat "
                "feeding, and it reports no target strain or dry-to-wet biomass "
                "factor."
            ),
            "evidence": "Models/Ganjave/MODEL_REPORT.md; composition.compatibility assessment 'ganjave'",
        },
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": (
                "A second E. coli fed-batch model with a declared K-12 lineage and "
                "a documented substrate context."
            ),
            "remains_missing": (
                "The organism is not E. coli 20 IBA 1 and the construct is not "
                "pIBAINS; the compatibility assessment records the strain and "
                "substrate mismatch as blockers."
            ),
            "evidence": "composition.compatibility assessment 'ganjave'",
        },
        "GAP-COMPOSITION-BOUNDARY": {
            "relation": "relevant_context",
            "contribution": (
                "Demonstrates the registered-model boundary problem: its ports are "
                "mechanically legal but scientifically unsupported, so the policy "
                "fails closed."
            ),
            "remains_missing": (
                "No shared component set, no explicit dry-to-wet biomass basis and "
                "no common medium; the engine permits no connection to the target."
            ),
            "evidence": "composition.cross_model; composition.compatibility assessment 'ganjave'",
        },
        "GAP-INDEPENDENT-VALIDATION": {
            "relation": "relevant_context",
            "contribution": (
                "An independent fed-batch data set and model in a different "
                "experimental context."
            ),
            "remains_missing": (
                "It does not repeat the Zielinski process, so it cannot validate "
                "that process or bound its batch-to-batch variability."
            ),
            "evidence": "Models/Ganjave/MODEL_REPORT.md",
        },
    },
    "morris": {
        "GAP-COMPOSITION-BOUNDARY": {
            "relation": "relevant_context",
            "contribution": (
                "A control-volume material-balance engine with explicit component "
                "identity and a declared time basis."
            ),
            "remains_missing": (
                "It has no reaction term, no organism and no component mapping for "
                "Zielinski's process roles; the engine refuses the boundary on "
                "component identity."
            ),
            "evidence": "Models/Morris/MODEL_REPORT.md; composition.cross_model",
        },
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": "A generic balance method, not an organism model.",
            "remains_missing": (
                "It contributes no biological context for E. coli 20 IBA 1 or "
                "pIBAINS and cannot represent a reaction."
            ),
            "evidence": "composition.compatibility assessment 'morris'",
        },
    },
    "baez": {
        "GAP-MP-GROWTH-KINETICS": {
            "relation": "partially_addresses",
            "contribution": (
                "Prints an exponential feed equation with mu_set, Y_XS, m and S_F, "
                "and reports growth at two dissolved-oxygen levels."
            ),
            "remains_missing": (
                "It is W3110 with a soxS-driven construct at 37 degC, not E. coli "
                "20 IBA 1 / pIBAINS at the target conditions; it prints no growth "
                "law and no target-context maintenance or saturation parameter."
            ),
            "evidence": "Models/Baez/manifest.json; Models/Baez/MODEL_REPORT.md",
        },
        "GAP-MP-OXYGEN-TRANSFER": {
            "relation": "partially_addresses",
            "contribution": (
                "Reports air at 0.075 vvm, 100 rpm, a dissolved-oxygen step from "
                "30% to 300% air saturation, and growth observations at two oxygen "
                "levels."
            ),
            "remains_missing": (
                "The package's own missing_models list states that it prints no "
                "kLa, OUR or OTR and no oxygen balance; the reactor and strain "
                "also differ from the target."
            ),
            "evidence": "Models/Baez/manifest.json (missing_models, experimental_conditions)",
        },
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": (
                "Recombinant protein production in E. coli, with a documented "
                "host and oxygen-induced expression mechanism."
            ),
            "remains_missing": (
                "Different strain (W3110), different construct and the opposite "
                "induction mechanism (dissolved oxygen, not IPTG), so it is not "
                "context-matched evidence."
            ),
            "evidence": "composition.compatibility assessment 'baez'",
        },
        "GAP-MP-CULTURE-MEDIUM": {
            "relation": "relevant_context",
            "contribution": (
                "Reports a feed solution containing 282 g/L yeast extract and "
                "141 g/L glucose."
            ),
            "remains_missing": (
                "That is not GMS medium, and it is not the target's 40% glucose / "
                "12 mg/mL proline feed."
            ),
            "evidence": "Models/Baez/manifest.json (experimental_conditions, reported_parameters)",
        },
        "GAP-INDEPENDENT-VALIDATION": {
            "relation": "relevant_context",
            "contribution": "An independent recombinant E. coli fed-batch data set.",
            "remains_missing": (
                "It uses a different process and does not validate the Zielinski "
                "batch or its reported yields."
            ),
            "evidence": "Models/Baez/MODEL_REPORT.md",
        },
    },
    "lin": {
        "GAP-MP-GROWTH-KINETICS": {
            "relation": "partially_addresses",
            "contribution": (
                "A complete glucose-limited fed-batch model: seven printed ODEs, "
                "the subsidiary chain, two correction branches, Table I parameters "
                "and reported glucose/oxygen uptake capacities."
            ),
            "remains_missing": (
                "It is W3110/RB791 in mineral salt medium at 35 degC in a 15 L or "
                "6 L reactor, not E. coli 20 IBA 1 / pIBAINS in GMS at the target "
                "conditions; two initial-enzyme factors are never valued."
            ),
            "evidence": "Models/Lin/MODEL_REPORT.md; Models/Lin/manifest.json",
        },
        "GAP-MP-OXYGEN-TRANSFER": {
            "relation": "partially_addresses",
            "contribution": (
                "Reports oxygen-uptake capacity (5 mmol g-1 h-1 at the end of "
                "fed-batch) and dissolved oxygen held above 20% with 0.002-2 vvm "
                "and 200-800 rpm in cascade."
            ),
            "remains_missing": (
                "It prints no oxygen-transfer correlation, models no oxygen "
                "limitation, and its strain, medium, scale and temperature differ; "
                "the capacity is not a kLa for the target vessel."
            ),
            "evidence": "Models/Lin/manifest.json (reported_capacities, experimental_context)",
        },
        "GAP-MP-CULTURE-MEDIUM": {
            "relation": "relevant_context",
            "contribution": (
                "An enumerated phosphate-buffered mineral salt medium and feed "
                "solution, with glucose and (NH4)2SO4 concentrations."
            ),
            "remains_missing": (
                "That is a different medium from GMS and does not supply the "
                "target's medium composition or its 40% glucose / proline feed."
            ),
            "evidence": "Models/Lin/manifest.json (experimental_context)",
        },
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": (
                "A glucose-limited E. coli fed-batch context with a plasmid present "
                "but uninduced."
            ),
            "remains_missing": (
                "The strain, construct and induction state differ: W3110/RB791 "
                "with an uninduced plasmid, not E. coli 20 IBA 1 producing insulin "
                "from pIBAINS."
            ),
            "evidence": "composition.compatibility assessment 'lin'",
        },
        "GAP-COMPOSITION-BOUNDARY": {
            "relation": "relevant_context",
            "contribution": (
                "Its ports carry mu, qO, DOT, X and S, which is exactly the kind of "
                "state transfer the target refuses."
            ),
            "remains_missing": (
                "Handing those states to Zielinski would transfer one experiment's "
                "state into another; the model is standalone and unregistered."
            ),
            "evidence": "composition.compatibility assessment 'lin'",
        },
        "GAP-INDEPENDENT-VALIDATION": {
            "relation": "relevant_context",
            "contribution": "Independent glucose-limited fed-batch experiments and capacities.",
            "remains_missing": (
                "They are not repeats of the Zielinski process and cannot validate "
                "its growth, yields or activity."
            ),
            "evidence": "Models/Lin/MODEL_REPORT.md",
        },
    },
    "nanchen": {
        "GAP-MP-GROWTH-KINETICS": {
            "relation": "partially_addresses",
            "contribution": (
                "Pirt's chemostat relation fitted for E. coli MG1655, with a "
                "maintenance coefficient and maximal molar yield."
            ),
            "remains_missing": (
                "It is a non-recombinant MG1655 in a 10 mL chemostat at 37 degC, "
                "not the production strain in GMS under pH-stat feeding; the paper "
                "states that maintenance and yield depend on exactly those "
                "conditions."
            ),
            "evidence": "Models/nanchen/MODEL_REPORT.md; Models/nanchen/manifest.json",
        },
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": "A wild-type E. coli K-12 growth-characterisation context.",
            "remains_missing": (
                "No recombinant construct and not E. coli 20 IBA 1 / pIBAINS, so "
                "it cannot support a target-context biological parameter."
            ),
            "evidence": "composition.compatibility assessment 'nanchen'",
        },
        "GAP-MP-CULTURE-MEDIUM": {
            "relation": "relevant_context",
            "contribution": "An enumerated M9 minimal medium with 1 g/L glucose.",
            "remains_missing": (
                "M9 is not GMS, and the paper's carbon-limited chemostat feed is "
                "not the target's pH-stat glucose/proline feed."
            ),
            "evidence": "Models/nanchen/manifest.json (experimental_context)",
        },
        "GAP-COMPOSITION-BOUNDARY": {
            "relation": "relevant_context",
            "contribution": (
                "An explicit example of condition-dependent maintenance and yield "
                "parameters."
            ),
            "remains_missing": (
                "Transferring its fitted values would silently re-parameterise the "
                "insulin process; the model is standalone and unregistered."
            ),
            "evidence": "composition.compatibility assessment 'nanchen'",
        },
    },
    "simensen": {
        "GAP-BIOLOGICAL-CONTEXT": {
            "relation": "relevant_context",
            "contribution": (
                "A measured macromolecular biomass composition of E. coli in "
                "g gCDW-1."
            ),
            "remains_missing": (
                "It is MG1655 in M9 with 2% glucose at 37 degC, not E. coli 20 "
                "IBA 1 / pIBAINS in GMS, and the paper states that composition is "
                "condition-dependent."
            ),
            "evidence": "Models/Simensen/manifest.json; composition.compatibility assessment 'simensen'",
        },
        "GAP-MP-CULTURE-MEDIUM": {
            "relation": "relevant_context",
            "contribution": "An enumerated M9 medium with 2% glucose.",
            "remains_missing": (
                "It does not enumerate GMS and does not report the target's "
                "glucose or proline feed."
            ),
            "evidence": "Models/Simensen/manifest.json (experimental_context)",
        },
        "GAP-COMPOSITION-BOUNDARY": {
            "relation": "relevant_context",
            "contribution": (
                "A static measured composition that could theoretically constrain "
                "a biomass-composition quantity."
            ),
            "remains_missing": (
                "Zielinski declares no biomass-composition quantity, the dataset "
                "has no input port, and the condition differs, so no comparison "
                "has a meaning."
            ),
            "evidence": "composition.compatibility assessment 'simensen'",
        },
    },
}


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_model_graph(path: Path | None = None) -> dict[str, Any]:
    """Read the model's generated graph, or ``{}`` when it is unavailable."""
    return _read_json(path or MODEL_GRAPH)


def _evidence(source: Path | str, location: str, statement: str, kind: str) -> dict[str, str]:
    source_text = _relative(source) if isinstance(source, Path) else source
    return {
        "source": source_text,
        "location": location,
        "statement": statement,
        "kind": kind,
    }


def _missing_parameters(graph: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """One entry per missing-parameter id, with its nodes and blocked targets merged.

    A parameter can be declared on more than one node (``MP-A280-SOLUTION`` is
    declared on both the citraconylation and trypsin operations). The gap is the
    missing parameter, not the node, so the records are merged rather than
    reported twice.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for node in graph.get("nodes", ()) or ():
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id", "?"))
        for parameter in node.get("missing_parameters", ()) or ():
            if not isinstance(parameter, dict) or not parameter.get("parameter_id"):
                continue
            parameter_id = str(parameter["parameter_id"])
            if parameter_id not in merged:
                merged[parameter_id] = {
                    "node": node,
                    "parameter": dict(parameter),
                    "nodes": [node_id],
                    "node_names": [str(node.get("name", ""))],
                }
                order.append(parameter_id)
                continue
            record = merged[parameter_id]
            if node_id not in record["nodes"]:
                record["nodes"].append(node_id)
                record["node_names"].append(str(node.get("name", "")))
            blocks = list(record["parameter"].get("blocks", ()) or ())
            for block in parameter.get("blocks", ()) or ():
                if block not in blocks:
                    blocks.append(block)
            record["parameter"]["blocks"] = blocks
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for parameter_id in order:
        record = merged[parameter_id]
        parameter = record["parameter"]
        parameter["_nodes"] = record["nodes"]
        parameter["_node_names"] = record["node_names"]
        out.append((record["node"], parameter))
    return out


def _generic_search_terms(parameter_id: str, description: str) -> list[str]:
    words = " ".join(str(description).split()[:8])
    terms = [
        f'"{words}"',
        f'"{parameter_id}" "Escherichia coli"',
    ]
    return [term for term in terms if term.strip('" ')]


def _generic_recommendation(
    parameter_id: str, description: str, why: str, search_terms: Sequence[str]
) -> dict[str, Any]:
    return {
        "what_information_is_needed": [description],
        "why_it_is_needed": why,
        "suitable_paper_must_report": [
            "The same host strain, construct, medium and process mode as the target.",
            "The missing quantity with its measurement or fitting method and uncertainty.",
            "Enough detail for ScaleUp to attach it as a source-qualified record.",
        ],
        "search_terms": list(search_terms),
        "what_scaleup_can_do": (
            "Record the finding against this parameter, run the existing identity "
            "comparison, and leave the parameter unresolved until the evidence "
            "matches the target process."
        ),
    }


def prior_investigation(parameter_id: str) -> dict[str, Any] | None:
    """The project's existing literature investigation for one parameter.

    Read from :mod:`composition.evidence.catalogue`; this function performs no
    search of its own. Values from the candidate findings are deliberately not
    copied: the question here is what was examined and why it did not resolve
    the target gap.
    """
    template = PARAMETER_TEMPLATES.get(parameter_id, {})
    port_id = str(template.get("catalogue_target", ""))
    if not port_id:
        return None
    try:
        from .evidence import catalogue
    except Exception:  # pragma: no cover - only when the evidence package is absent
        return None

    info = catalogue.TARGETS.get(port_id)
    if not info:
        return None
    findings = catalogue.findings_for_port(port_id)
    examined = []
    for finding in findings:
        assessment = finding.assess()
        examined.append({
            "finding_id": finding.finding_id,
            "citation": finding.source.citation,
            "verdict": assessment.verdict.value,
            "independence": assessment.independence.value,
            "reasons": list(assessment.reasons),
            "does_not_resolve": list(finding.does_not_resolve),
        })
    return {
        "port_id": port_id,
        "label": info.get("label", ""),
        "why_it_matters": info.get("why_it_matters", ""),
        "resolved": False,
        "candidate_count": len(findings),
        "verdicts": [item["verdict"] for item in examined],
        "findings": examined,
        "missing_information_required": catalogue.missing_information_required(port_id),
        "note": (
            "This is the project's existing literature investigation, reused as "
            "recorded. It did not resolve the target gap; a finding here is a "
            "proposal with a verdict, never a value adopted by the model."
        ),
    }


def _gap_from_parameter(node: dict[str, Any], parameter: dict[str, Any]) -> dict[str, Any]:
    parameter_id = str(parameter.get("parameter_id", "unknown"))
    template = PARAMETER_TEMPLATES.get(parameter_id, {})
    nodes = [str(value) for value in parameter.get("_nodes", ()) or ()]
    node_names = [str(value) for value in parameter.get("_node_names", ()) or ()]
    if not nodes:
        nodes = [str(node.get("node_id", "?"))]
        node_names = [str(node.get("name", ""))]
    node_id = "/".join(nodes)
    node_name = " + ".join(name for name in node_names if name)
    reason = str(parameter.get("reason", "")).strip()
    blocks = [str(block) for block in parameter.get("blocks", ()) or ()]
    description = (
        f"{parameter_id} is declared on {node_id} ({node_name}): {reason} "
        f"The blocked targets are {', '.join(blocks) if blocks else 'not listed'}."
    )
    category = str(template.get("category", "model_parameters"))
    why = str(template.get("why_it_matters", "")).strip()
    if not why:
        why = (
            "The model declares this parameter missing, so the blocked targets "
            "cannot be computed from inputs without inventing information."
        )
    search_terms = list(template.get("search_terms", ()))
    if not search_terms:
        search_terms = _generic_search_terms(parameter_id, description)
    missing = list(template.get("missing_evidence", ()))
    if not missing:
        missing = [reason or f"No target-context value is recorded for {parameter_id}."]
    recommendation = dict(template.get("recommendation", {}))
    if not recommendation:
        recommendation = _generic_recommendation(parameter_id, description, why, search_terms)
    recommendation["gap_id"] = gap_id_for_parameter(parameter_id)
    recommendation["search_terms"] = search_terms

    gap = {
        "gap_id": gap_id_for_parameter(parameter_id),
        "category": category,
        "category_title": CATEGORY_TITLES.get(category, category),
        "title": str(template.get("title", parameter.get("description", parameter_id))),
        "description": description,
        "why_it_matters": why,
        "variables": [
            f"{node}:{block}" for node in nodes for block in blocks
        ],
        "model_component": node_id,
        "parameter_id": parameter_id,
        "existing_evidence": [
            _evidence(
                MODEL_GRAPH,
                f"nodes[{node_id}].missing_parameters[{parameter_id}]",
                reason or "The model declares this parameter missing.",
                "model_declaration",
            )
        ],
        "missing_evidence": missing,
        "search_terms": search_terms,
        "composition_enabling": bool(template.get("composition_enabling", False)),
        "validation_improving": bool(template.get("validation_improving", True)),
        "recommendation": recommendation,
        "status": "unresolved",
        "addressed_by": [],
        "partly_addressed_by": [],
        "papers": [],
        "prior_investigation": prior_investigation(parameter_id),
    }
    if parameter_id == "MP-INDUCTION-TIME":
        gap["existing_evidence"].append(_evidence(
            MODEL_SUMMARY,
            "source_discrepancy:induction_order",
            "The model records that the narrative order cannot be reconciled with "
            "Fig. 3; induction may have preceded the glucose limitation.",
            "model_report",
        ))
    if parameter_id == "MP-FOLDING-MODEL":
        gap["existing_evidence"].append(_evidence(
            MODEL_SUMMARY,
            "source_discrepancy:refolding_yield_vs_au",
            "The model records that the reported 5460 AU and 5450 AU imply 99.82%, "
            "while the paper also states 95-96%; both are retained.",
            "model_report",
        ))
    return gap


def _assessment_evidence(
    assessments: Sequence[Any], keys: Iterable[str], kind: str = "compatibility_record"
) -> list[dict[str, str]]:
    by_key = {assessment.key: assessment for assessment in assessments}
    out: list[dict[str, str]] = []
    for key in keys:
        assessment = by_key.get(key)
        if assessment is None:
            continue
        statements = list(assessment.blockers) or [assessment.evidence_check]
        statement = " ".join(part for part in statements if part).strip()
        if statement:
            out.append(_evidence(
                COMPATIBILITY_SOURCE,
                f"ASSESSMENTS['{key}'].blockers/evidence_check",
                statement,
                kind,
            ))
    return out


def _biological_gap(assessments: Sequence[Any]) -> dict[str, Any]:
    candidates = [a for a in assessments if not a.is_baseline]
    evidence = [
        _evidence(
            COMPATIBILITY_SOURCE,
            "TARGET_PROCESS",
            f"The target process is recorded as: {TARGET_PROCESS}",
            "compatibility_record",
        )
    ]
    evidence.extend(_assessment_evidence(assessments, [a.key for a in candidates]))
    return {
        "gap_id": GAP_BIOLOGICAL_CONTEXT,
        "category": "biological_context",
        "category_title": CATEGORY_TITLES["biological_context"],
        "title": "No target-context biological characterisation in the assessed library",
        "description": (
            "Every assessed candidate differs from the target on organism, strain "
            "or construct. The compatibility records state, per candidate, that "
            "the organism is a different E. coli lineage or that the construct is "
            "absent or different. The baseline paper is the only record of E. coli "
            "20 IBA 1 carrying pIBAINS, and it is not an independent source for "
            "its own gaps."
        ),
        "why_it_matters": (
            "A parameter or relationship measured in a different strain or "
            "construct cannot be entered as target-context evidence. The "
            "compatibility engine refuses such a candidate before any number is "
            "compared, so without a matched biological source no candidate can "
            "reach evidence_compatible or be composed."
        ),
        "variables": [
            "zielinski2019.rhi_process:organism",
            "zielinski2019.rhi_process:construct",
            "N01:operating_conditions",
        ],
        "model_component": "zielinski2019.rhi_process",
        "parameter_id": "",
        "existing_evidence": evidence,
        "missing_evidence": [
            "An independent characterisation of E. coli 20 IBA 1 carrying pIBAINS "
            "in GMS medium, not merely a restatement of the baseline paper.",
            "Plasmid burden, stability and induction response for pIBAINS in this "
            "host.",
            "A physiological parameter set measured for this strain and construct "
            "under the target process conditions, if a candidate model states "
            "which quantity it needs.",
        ],
        "search_terms": [
            '"Escherichia coli 20 IBA 1" "pIBAINS"',
            '"Escherichia coli 20" "CSH50R" insulin',
            '"pIBAINS" plasmid stability "Escherichia coli"',
            '"Escherichia coli 20" GMS medium physiology',
        ],
        "composition_enabling": True,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "A biological characterisation made on the same host and construct "
                "as the target, independent of Zielinski et al. (2019).",
            ],
            "why_it_is_needed": (
                "The compatibility engine's identity dimensions require the same "
                "organism, strain, construct, medium and mode. No assessed "
                "candidate satisfies them, so the target's own biology remains a "
                "single-paper record."
            ),
            "suitable_paper_must_report": [
                "E. coli 20 IBA 1 or an explicitly identified CSH50R derivative.",
                "The plasmid pIBAINS and its induction/expression behaviour.",
                "GMS medium and the fed-batch operating policy, or a clear "
                "statement of which dimensions differ.",
            ],
            "what_scaleup_can_do": (
                "Run the existing identity comparison against the new source and "
                "record which dimensions match. Only a full match could support a "
                "compatibility reclassification; relevance alone cannot."
            ),
        },
        "status": "unresolved",
        "addressed_by": [],
        "partly_addressed_by": [],
        "papers": [],
        "prior_investigation": None,
    }


def _validation_gap(assessments: Sequence[Any]) -> dict[str, Any]:
    counts = compatibility.summary()["counts"]
    evidence = [
        _evidence(
            MODEL_REPORT,
            "3.2 Figure 3 growth trajectory (digitized, replay only)",
            "The growth evidence is one digitized Fig. 3 trajectory with declared "
            "uncertainty of +/-0.1 h and +/-0.5 OD600, not replicates.",
            "model_report",
        ),
        _evidence(
            MODEL_SUMMARY,
            "Cross-checks and source discrepancies",
            "The model records failed cross-checks (CC05 water volume and CC08 CPB "
            "dose) and states that the paper reports no replicates, standard or "
            "error bars for the mass deviation.",
            "model_report",
        ),
        _evidence(
            COMPATIBILITY_SOURCE,
            "summary()['counts']",
            "The compatibility summary records that no candidate is "
            f"evidence_compatible ({counts.get('evidence_compatible', 0)}) and that "
            "no permitted connection touches the target.",
            "compatibility_record",
        ),
    ]
    return {
        "gap_id": GAP_INDEPENDENT_VALIDATION,
        "category": "independent_validation",
        "category_title": CATEGORY_TITLES["independent_validation"],
        "title": "The process has one published batch and no independent validation record",
        "description": (
            "The baseline's growth evidence is a single digitized figure, and its "
            "harvest, purification and activity numbers are single-run reports. "
            "No assessed paper repeats the Zielinski process. The compatibility "
            "records contain no context-matched evidence and no independently "
            "validated candidate."
        ),
        "why_it_matters": (
            "A replay of one batch establishes what the paper says, not whether "
            "the process reproduces. Without an independent batch or an orthogonal "
            "measurement, a residual difference between a candidate model and the "
            "target cannot be attributed to science rather than batch variability."
        ),
        "variables": [
            "S02_culture_broth:od600_25_crossing_h",
            "S02_culture_broth:od600_50_crossing_h",
            "N02:wet_biomass_g_per_L",
            "N15:batch_activity",
        ],
        "model_component": "zielinski2019.rhi_process",
        "parameter_id": "",
        "existing_evidence": evidence,
        "missing_evidence": [
            "A replicate of the same process, ideally from an independent group, "
            "with the same host, construct, medium and feeding policy.",
            "Replicate measurements or error bars for OD600, wet biomass, "
            "inclusion bodies, AU and activity.",
            "An orthogonal insulin mass or activity measurement that does not "
            "depend on the uncalibrated AU scale.",
        ],
        "search_terms": [
            '"Zielinski" 2019 insulin independent replication',
            '"recombinant human insulin" "Escherichia coli" fed-batch replicate',
            '"insulin inclusion bodies" "mass balance" "AU"',
            '"Escherichia coli 20" insulin batch reproducibility',
        ],
        "composition_enabling": False,
        "validation_improving": True,
        "recommendation": {
            "what_information_is_needed": [
                "An independent repeat of the target process, or at least "
                "replicated measurements of its key outputs.",
            ],
            "why_it_is_needed": (
                "The baseline is an evidence replay of one publication. Without a "
                "second batch, validation claims would rest on the same record "
                "that defines the model."
            ),
            "suitable_paper_must_report": [
                "The same host, construct, medium and operating policy, or an "
                "explicitly justified equivalent.",
                "Raw time series and endpoint measurements with replicates.",
                "The calibration and assay methods, not only the final values.",
            ],
            "what_scaleup_can_do": (
                "Hold the independent batch as a held-out record, compare it with "
                "the replay without changing the baseline, and report residuals "
                "with the batch variability stated."
            ),
        },
        "status": "unresolved",
        "addressed_by": [],
        "partly_addressed_by": [],
        "papers": [],
        "prior_investigation": None,
    }


def _composition_gap(assessments: Sequence[Any]) -> dict[str, Any]:
    summary = compatibility.summary()
    permitted = compatibility.permitted_connections()
    touching = [item for item in permitted if item.get("touches_target")]
    evidence = [
        _evidence(
            COMPATIBILITY_SOURCE,
            "summary()['connections_touching_target']",
            f"The compatibility summary lists {len(touching)} permitted connection(s) "
            "touching the insulin process.",
            "compatibility_record",
        ),
        _evidence(
            COMPATIBILITY_SOURCE,
            "permitted_connections()",
            f"The engine permits {len(permitted)} connection(s) across the whole "
            "project; none reaches the target process.",
            "compatibility_record",
        ),
    ]
    evidence.extend(_assessment_evidence(
        assessments,
        ("ganjave", "morris", "lin", "nanchen"),
    ))
    return {
        "gap_id": GAP_COMPOSITION_BOUNDARY,
        "category": "composition_blockers",
        "category_title": CATEGORY_TITLES["composition_blockers"],
        "title": "No shared quantity or component mapping permits a connection to the insulin process",
        "description": (
            "The composition engine's permitted-connection list contains no "
            "connection that touches zielinski2019.rhi_process. The blockers are "
            "not a missing paper: they are missing shared declarations, including "
            "a common substrate and medium, a dry-to-wet biomass basis, and a "
            "component mapping for the material-balance model. A relevant paper "
            "cannot be attached without these."
        ),
        "why_it_matters": (
            "Composition requires a shared declared quantity and a context that "
            "matches. Without that, attaching a candidate would transfer one "
            "experiment's state or parameters into another experiment, which this "
            "project refuses even when the port shapes are mechanically legal."
        ),
        "variables": [
            "zielinski2019.rhi_process (declared ports)",
            "permitted_connections.touching_target",
            "S02_culture_broth:wet_biomass_total",
            "S03_wet_biomass:wet_biomass_total",
        ],
        "model_component": "zielinski2019.rhi_process",
        "parameter_id": "",
        "existing_evidence": evidence,
        "missing_evidence": [
            "An explicit component mapping between the candidate's conserved "
            "entities and Zielinski's process roles.",
            "A target-context conversion between wet biomass and dry-cell weight, "
            "if a dry-biomass model is to be used.",
            "A shared declared quantity with matching units and a permitted "
            "boundary in cross_model.",
            "A candidate whose organism, strain, construct, medium and mode match "
            "the target process.",
        ],
        "search_terms": [
            '"Escherichia coli" "wet biomass" "dry cell weight" conversion',
            '"insulin" "inclusion bodies" "mass balance"',
            '"Escherichia coli" process model component mapping',
            '"Escherichia coli 20" "pIBAINS" process model',
        ],
        "composition_enabling": True,
        "validation_improving": False,
        "recommendation": {
            "what_information_is_needed": [
                "A candidate model or measurement set that declares a shared "
                "quantity and matches the target's identity dimensions.",
            ],
            "why_it_is_needed": (
                "No permitted connection touches the target. Supplying a relevant "
                "paper is not enough; the project needs an explicit, evidence-backed "
                "quantity and component mapping before composition is legitimate."
            ),
            "suitable_paper_must_report": [
                "A quantity that Zielinski also declares, with compatible units.",
                "The same organism, strain, construct, medium and process mode, "
                "or an explicit statement of which dimensions differ.",
                "Enough component identity to map the candidate's state to "
                "Zielinski's process roles.",
            ],
            "what_scaleup_can_do": (
                "Declare the new boundary only after the shared quantity and "
                "identity match are recorded; re-run the compatibility check and "
                "leave the baseline replay unchanged."
            ),
        },
        "status": "unresolved",
        "addressed_by": [],
        "partly_addressed_by": [],
        "papers": [],
        "prior_investigation": None,
    }


def _default_paper_records() -> Sequence[Any]:
    try:
        from .evidence import papers as paper_index
    except Exception:  # pragma: no cover
        return ()
    return paper_index.PAPERS


def _paper_profiles(
    assessments: Sequence[Any], paper_records: Sequence[Any]
) -> list[dict[str, Any]]:
    records = {
        str(getattr(record, "folder", "")).lower(): record
        for record in paper_records
    }
    profiles: list[dict[str, Any]] = []
    for assessment in assessments:
        record = records.get(str(assessment.paper_folder).lower())
        if assessment.is_baseline:
            role = "baseline_reference"
        elif assessment.classification is compatibility.Classification.EVIDENCE_COMPATIBLE:
            role = "context_matched_evidence"
        elif assessment.contributes:
            role = "potentially_composable_model"
        else:
            role = "relevant_literature"
        suitability = (
            "Defines the target process. It cannot resolve gaps in its own reporting."
            if assessment.is_baseline else
            (assessment.evidence_check or " ".join(assessment.blockers)
             or "No evidence check is recorded for this model.")
        )
        profiles.append({
            "key": assessment.key,
            "display_name": assessment.display_name,
            "citation": str(getattr(record, "citation", "") or assessment.paper),
            "paper": assessment.paper,
            "paper_folder": assessment.paper_folder,
            "package": assessment.package,
            "model_id": assessment.model_id,
            "model_version": assessment.model_version,
            "contributes": assessment.contributes,
            "classification": assessment.classification.value,
            "classification_number": assessment.classification_number,
            "classification_label": assessment.classification_label,
            "blockers": list(assessment.blockers),
            "evidence_check": assessment.evidence_check,
            "summary": assessment.summary,
            "suitability": suitability,
            "evidence_role": role,
            "is_baseline": assessment.is_baseline,
            "registered": assessment.registered,
            "determination": str(getattr(record, "determination", "") or "not_indexed"),
            "independently_validated": False,
            "independently_validated_reason": (
                "No assessment records a target-context independent validation. "
                "The compatibility summary records zero evidence-compatible models."
            ),
            "addressed_gaps": [],
            "partially_addressed_gaps": [],
            "relevant_context_gaps": [],
            "unresolved_gaps": [],
            "matched_gaps": [],
        })
    return profiles


def _paper_entry(profile: dict[str, Any], relation: str,
                 contribution: str, remains_missing: str) -> dict[str, Any]:
    return {
        "key": profile["key"],
        "display_name": profile["display_name"],
        "citation": profile["citation"],
        "paper_folder": profile["paper_folder"],
        "classification": profile["classification"],
        "classification_number": profile["classification_number"],
        "classification_label": profile["classification_label"],
        "contributes": profile["contributes"],
        "relation": relation,
        "relevance": contribution,
        "contribution": contribution,
        "what_information_it_contributes": contribution,
        "remains_missing": remains_missing,
        "what_remains_missing": remains_missing,
        "suitability": profile["suitability"],
        "evidence_role": profile["evidence_role"],
        "model_id": profile["model_id"],
        "package": profile["package"],
    }


def _papers_for_gap(
    gap_id: str, profiles: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    baseline = next((p for p in profiles if p["is_baseline"]), None)
    out: list[dict[str, Any]] = []
    if baseline is not None:
        out.append(_paper_entry(
            baseline,
            "defines_gap",
            "Records the process and states the missing item in its model evidence record.",
            "The baseline cannot supply its own missing information; it is the record that makes the gap visible.",
        ))
    for profile in profiles:
        if profile["is_baseline"]:
            continue
        link = PAPER_GAP_LINKS.get(profile["key"], {}).get(gap_id)
        if link is None:
            continue
        out.append(_paper_entry(
            profile,
            link["relation"],
            link["contribution"],
            link["remains_missing"],
        ))
    return out


def _apply_matches(
    gaps: list[dict[str, Any]], profiles: Sequence[dict[str, Any]]
) -> None:
    by_key = {profile["key"]: profile for profile in profiles}
    all_ids = [gap["gap_id"] for gap in gaps]
    for gap in gaps:
        entries = _papers_for_gap(gap["gap_id"], profiles)
        gap["papers"] = entries
        gap["addressed_by"] = [
            entry["key"] for entry in entries if entry["relation"] == "addresses"
        ]
        gap["partly_addressed_by"] = [
            entry["key"] for entry in entries
            if entry["relation"] == "partially_addresses"
        ]
        if gap["addressed_by"]:
            gap["status"] = "addressed"
        elif gap["partly_addressed_by"]:
            gap["status"] = "partially_addressed"
        else:
            gap["status"] = "unresolved"
        if gap["status"] == "addressed":
            gap["recommendation"] = {}
        else:
            gap["recommendation"]["gap_id"] = gap["gap_id"]
            gap["recommendation"]["search_terms"] = list(gap["search_terms"])
        for entry in entries:
            profile = by_key.get(entry["key"])
            if profile is None:
                continue
            if gap["gap_id"] not in profile["matched_gaps"]:
                profile["matched_gaps"].append(gap["gap_id"])
            if entry["relation"] == "addresses":
                profile["addressed_gaps"].append(gap["gap_id"])
            elif entry["relation"] == "partially_addresses":
                profile["partially_addressed_gaps"].append(gap["gap_id"])
            elif entry["relation"] == "relevant_context":
                profile["relevant_context_gaps"].append(gap["gap_id"])
    for profile in profiles:
        resolved = set(profile["addressed_gaps"]) | set(profile["partially_addressed_gaps"])
        profile["unresolved_gaps"] = [gap_id for gap_id in all_ids if gap_id not in resolved]
        profile["gap_counts"] = {
            "matched": len(profile["matched_gaps"]),
            "addressed": len(profile["addressed_gaps"]),
            "partially_addressed": len(profile["partially_addressed_gaps"]),
            "relevant_context": len(profile["relevant_context_gaps"]),
            "unresolved": len(profile["unresolved_gaps"]),
        }


def _summary(
    gaps: Sequence[dict[str, Any]], profiles: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    by_category = {category: 0 for category in CATEGORY_IDS}
    by_status = {"addressed": 0, "partially_addressed": 0, "unresolved": 0}
    for gap in gaps:
        by_category[gap["category"]] = by_category.get(gap["category"], 0) + 1
        by_status[gap["status"]] = by_status.get(gap["status"], 0) + 1
    fully = by_status["addressed"]
    partial = by_status["partially_addressed"]
    roles: dict[str, int] = {}
    classifications: dict[str, int] = {}
    for profile in profiles:
        roles[profile["evidence_role"]] = roles.get(profile["evidence_role"], 0) + 1
        classifications[profile["classification"]] = (
            classifications.get(profile["classification"], 0) + 1
        )
    return {
        "gaps": len(gaps),
        "fully_addressed": fully,
        "partially_addressed": partial,
        "unresolved": len(gaps) - fully,
        "no_literature_contribution": len(gaps) - fully - partial,
        "composition_enabling": sum(1 for gap in gaps if gap["composition_enabling"]),
        "validation_improving": sum(1 for gap in gaps if gap["validation_improving"]),
        "papers_assessed": len(profiles),
        "by_category": by_category,
        "by_status": by_status,
        "classifications": classifications,
        "evidence_roles": roles,
        "fully_addressed_gaps": [
            gap["gap_id"] for gap in gaps if gap["status"] == "addressed"
        ],
        "partially_addressed_gaps": [
            gap["gap_id"] for gap in gaps if gap["status"] == "partially_addressed"
        ],
    }


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _traceability(graph: dict[str, Any]) -> dict[str, Any]:
    sources = [
        MODEL_GRAPH,
        MODEL_REPORT,
        MODEL_SUMMARY,
        MODEL_SOURCE,
        COMPATIBILITY_SOURCE,
        PAPERS_SOURCE,
        EVIDENCE_SOURCE,
    ]
    return {
        "read_only": True,
        "model_artifacts_written": [],
        "sources": [
            {"path": _relative(path), "sha256": _sha256(path)}
            for path in sources
        ],
        "model_graph": {
            "nodes": len(graph.get("nodes", ()) or ()),
            "streams": len(graph.get("streams", ()) or ()),
            "assumptions": len(graph.get("assumptions", ()) or ()),
            "missing_parameters": len(_missing_parameters(graph)),
        },
        "note": (
            "The analysis reads existing model artifacts, compatibility records "
            "and the paper index. It writes nothing under Models/ and changes no "
            "model equation or replay value."
        ),
    }


def _prior_search_payload() -> dict[str, Any]:
    try:
        from .evidence import catalogue
    except Exception:  # pragma: no cover
        return {
            "available": False,
            "note": "The evidence catalogue package is not present in this build.",
        }
    verdicts: dict[str, int] = {}
    for finding in catalogue.FINDINGS:
        verdict = finding.assess().verdict.value
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {
        "available": True,
        "source": _relative(EVIDENCE_SOURCE),
        "searched": catalogue.SEARCH_SCOPE,
        "targets_examined": len(catalogue.TARGETS),
        "findings": len(catalogue.FINDINGS),
        "verdicts": verdicts,
        "note": (
            "This is the project's existing literature investigation, reused "
            "as recorded. It did not resolve any target gap and was not repeated "
            "or extended by this analysis."
        ),
    }


def analyse(
    model_graph: dict[str, Any] | None = None,
    assessments: Sequence[Any] | None = None,
    paper_records: Sequence[Any] | None = None,
    graph_path: Path | None = None,
) -> dict[str, Any]:
    """Build the complete, reproducible gap-discovery payload.

    ``model_graph``, ``assessments`` and ``paper_records`` are injectable so a
    test can exercise incomplete evidence without touching the real records.
    Passing an empty sequence is respected rather than replaced: the output
    then says there is no literature contribution and every gap stays
    unresolved.
    """
    graph = load_model_graph(graph_path) if model_graph is None else model_graph
    assessments = compatibility.ASSESSMENTS if assessments is None else assessments
    records = _default_paper_records() if paper_records is None else paper_records

    gaps: list[dict[str, Any]] = []
    for node, parameter in _missing_parameters(graph):
        gaps.append(_gap_from_parameter(node, parameter))
    gaps.append(_biological_gap(assessments))
    gaps.append(_validation_gap(assessments))
    gaps.append(_composition_gap(assessments))
    gaps.sort(key=lambda gap: (
        CATEGORY_IDS.index(gap["category"])
        if gap["category"] in CATEGORY_IDS else len(CATEGORY_IDS),
        gap["gap_id"],
    ))

    profiles = _paper_profiles(assessments, records)
    _apply_matches(gaps, profiles)

    warnings: list[str] = []
    if not graph:
        warnings.append(
            f"{_relative(MODEL_GRAPH)} is missing or unreadable. Parameter gaps "
            "could not be built from the model; only the biological, validation "
            "and composition gaps are reported."
        )
    elif not _missing_parameters(graph):
        warnings.append(
            "The model graph declares no missing parameters. That is reported as "
            "a fact, not treated as evidence that the model is complete."
        )
    if not assessments:
        warnings.append("No compatibility assessments were supplied.")
    if not records:
        warnings.append(
            "No paper-index records were supplied. Classifications still come "
            "from the compatibility assessments, but corpus determinations are "
            "labelled not_indexed."
        )

    summary = _summary(gaps, profiles)
    recommendations = [
        gap["recommendation"] for gap in gaps if gap["status"] != "addressed"
    ]
    categories = []
    for category in CATEGORIES:
        category_gaps = [
            gap["gap_id"] for gap in gaps if gap["category"] == category["id"]
        ]
        categories.append({
            **category,
            "count": len(category_gaps),
            "gap_ids": category_gaps,
        })

    body: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "target": {
            "model_id": TARGET_MODEL,
            "model_version": TARGET_MODEL_VERSION,
            "paper": TARGET_PAPER,
            "label": "Zielinski insulin production",
            "process": TARGET_PROCESS,
        },
        "claim_scope": (
            "A gap states what the project's own model, compatibility and paper "
            "records do not contain. It is not a claim that no research exists. "
            "A paper is never upgraded because it is relevant; every "
            "classification below is copied unchanged from "
            "composition.compatibility. A gap is 'addressed' only when an "
            "assessment explicitly supplies target-context evidence."
        ),
        "summary": summary,
        "categories": categories,
        "gaps": gaps,
        "papers": profiles,
        "recommendations": recommendations,
        "prior_literature_search": _prior_search_payload(),
        "role_legend": {
            "baseline_reference": "The target paper itself; it defines the gaps, not their answers.",
            "relevant_literature": "Shares the phenomenon or method but is not target-context evidence.",
            "context_matched_evidence": "Matches the target context and may constrain a target quantity.",
            "potentially_composable_model": "Has a permitted, evidence-backed connection to the target.",
            "independently_validated_evidence": "An independent, target-context validation record.",
            "note": (
                "No assessed paper is in context_matched_evidence, "
                "potentially_composable_model or independently_validated_evidence."
            ),
        },
        "warnings": warnings,
        "traceability": _traceability(graph),
    }
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    body["analysis_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


def describe() -> dict[str, Any]:
    """The whole analysis, as one document the editor renders."""
    return analyse()


GAP_STATUSES = ("addressed", "partially_addressed", "unresolved")


def problems(payload: dict[str, Any] | None = None) -> list[str]:
    """Every way the analysis and its sources disagree, as one list."""
    payload = describe() if payload is None else payload
    failures: list[str] = []
    gaps = payload.get("gaps", []) or []
    if not gaps:
        failures.append("no gaps were generated")

    seen: set[str] = set()
    for gap in gaps:
        gap_id = str(gap.get("gap_id", ""))
        if not gap_id:
            failures.append("a gap has no gap_id")
        if gap_id in seen:
            failures.append(f"duplicate gap_id: {gap_id}")
        seen.add(gap_id)
        if gap.get("category") not in CATEGORY_IDS:
            failures.append(f"{gap_id}: unknown category {gap.get('category')!r}")
        if gap.get("status") not in GAP_STATUSES:
            failures.append(f"{gap_id}: unknown status {gap.get('status')!r}")
        for field in ("title", "description", "why_it_matters"):
            if not str(gap.get(field, "")).strip():
                failures.append(f"{gap_id}: empty {field}")
        for field in ("variables", "existing_evidence", "missing_evidence", "search_terms"):
            if not gap.get(field):
                failures.append(f"{gap_id}: empty {field}")
        for entry in gap.get("existing_evidence", ()) or ():
            source = str(entry.get("source", ""))
            if not source or not (ROOT / source).exists():
                failures.append(f"{gap_id}: evidence source does not exist: {source!r}")
            if not str(entry.get("statement", "")).strip():
                failures.append(f"{gap_id}: evidence entry has no statement")
        if gap.get("status") != "addressed" and not gap.get("recommendation"):
            failures.append(f"{gap_id}: unresolved gap has no recommendation")
        recommendation = gap.get("recommendation") or {}
        if recommendation:
            for field in ("what_information_is_needed", "why_it_is_needed",
                          "suitable_paper_must_report", "what_scaleup_can_do"):
                if not recommendation.get(field):
                    failures.append(f"{gap_id}: recommendation has no {field}")
        if gap.get("status") == "addressed" and not gap.get("addressed_by"):
            failures.append(f"{gap_id}: addressed without an addressing paper")
        if gap.get("value") is not None:
            failures.append(f"{gap_id}: gap carries a value instead of missing information")
        for paper in gap.get("papers", ()) or ():
            if not paper.get("citation") or not paper.get("remains_missing"):
                failures.append(f"{gap_id}: paper match is incomplete")

    for category in CATEGORY_IDS:
        if not any(gap.get("category") == category for gap in gaps):
            failures.append(f"no gap was generated for category {category!r}")

    expected = {a.key: a for a in compatibility.ASSESSMENTS}
    papers = payload.get("papers", []) or []
    if len(papers) != len(expected):
        failures.append(
            f"expected {len(expected)} assessed papers, got {len(papers)}"
        )
    for paper in papers:
        assessment = expected.get(paper.get("key", ""))
        if assessment is None:
            failures.append(f"paper {paper.get('key')!r} is not an assessed model")
            continue
        if paper.get("classification") != assessment.classification.value:
            failures.append(
                f"{paper.get('key')}: classification {paper.get('classification')!r} "
                f"does not match compatibility {assessment.classification.value!r}"
            )
        if int(paper.get("classification_number", 0)) != assessment.classification_number:
            failures.append(
                f"{paper.get('key')}: classification number was changed"
            )

    summary = payload.get("summary", {}) or {}
    if int(summary.get("gaps", -1)) != len(gaps):
        failures.append("summary.gaps does not match the gap list")
    addressed = sum(1 for gap in gaps if gap.get("status") == "addressed")
    if int(summary.get("fully_addressed", -1)) != addressed:
        failures.append("summary.fully_addressed does not match the gap list")
    partial = sum(1 for gap in gaps if gap.get("status") == "partially_addressed")
    if int(summary.get("partially_addressed", -1)) != partial:
        failures.append("summary.partially_addressed does not match the gap list")
    composition = sum(1 for gap in gaps if gap.get("composition_enabling"))
    if int(summary.get("composition_enabling", -1)) != composition:
        failures.append("summary.composition_enabling does not match the gap list")

    trace = payload.get("traceability", {}) or {}
    if not trace.get("read_only"):
        failures.append("the analysis does not declare itself read-only")
    if not payload.get("analysis_digest"):
        failures.append("the analysis has no digest")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m composition.gaps",
        description=(
            "Report the scientific gaps in the Zielinski insulin simulation and "
            "what the project's literature library contributes to each."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a gap loses its evidence, a recommendation disappears, "
             "or a paper classification stops agreeing with compatibility",
    )
    parser.add_argument(
        "--write",
        metavar="<path>",
        help="write the analysis JSON to this path",
    )
    args = parser.parse_args(argv)

    payload = describe()
    if args.write:
        target = Path(args.write)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    failures = problems(payload)
    if args.check:
        for failure in failures:
            print(f"FAIL {failure}")
        if failures:
            return 1
        summary = payload["summary"]
        print(
            "PASS -- "
            f"{summary['gaps']} gaps, "
            f"{summary['fully_addressed']} fully addressed, "
            f"{summary['partially_addressed']} partially informed, "
            f"{summary['unresolved']} unresolved, "
            f"{summary['composition_enabling']} composition-enabling"
        )
        return 0
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

