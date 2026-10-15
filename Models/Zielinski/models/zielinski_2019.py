"""Zielinski et al. (2019) recombinant human insulin process model.

Source
------
M. Zielinski et al., "Expression and purification of recombinant human insulin
from E. coli 20 strain", Protein Expression and Purification 157 (2019) 63-69,
doi:10.1016/j.pep.2019.02.002.  Article PDF pages 1-7 correspond to printed
pages 63-69; `models.source.ev` performs and checks that mapping.

What this module is
-------------------
A faithful, executable representation of the process the paper documents, and
of the numbers the paper reports. It is deliberately *not* a predictive
simulator: the paper publishes no kinetics, no oxygen-transfer data, no AU
calibration and no purification model, so every quantity that would require one
is carried as `unknown` with a recorded reason.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from scaleup_ai import (
    Assumption,
    CrossCheck,
    EquationBinding,
    EvidenceRef,
    ExecutionEngine,
    ExecutionMode,
    MissingParameter,
    OperationKind,
    ProcessGraph,
    ProcessNode,
    Provenance,
    Quantity,
    Resolution,
    Severity,
    SourceExpression,
    StreamKind,
    MaterialStream,
    Uncertainty,
    ValidationMessage,
    derived,
    digitized,
    node_loc,
    reported,
    stream_loc,
)
from scaleup_ai.engine import Ref

from .source import CITATION, DOI, ev, fig3_trajectory

GRAPH_ID = "zielinski2019_rhi_process"


# --------------------------------------------------------------------------- #
# small constructor helpers
# --------------------------------------------------------------------------- #


def rep(
    qid: str,
    label: str,
    value: float,
    unit: str,
    evidence: EvidenceRef,
    *,
    original_text: str | None = None,
    uncertainty: Uncertainty | None = None,
    notes: str = "",
) -> Quantity:
    return reported(
        qid, label, value, unit, evidence,
        original_text=original_text, uncertainty=uncertainty, notes=notes,
    )


def rng(
    qid: str,
    label: str,
    lo: float,
    hi: float,
    unit: str,
    evidence: EvidenceRef,
    *,
    original_text: str | None = None,
    notes: str = "",
) -> Quantity:
    """A quantity the paper reports as an interval.

    The interval is preserved as an interval. It is never collapsed to a point
    value, because doing so would be an undeclared assumption.
    """
    return reported(
        qid, label, None, unit, evidence,
        value_range=(lo, hi), original_text=original_text, notes=notes,
    )


def unk(
    qid: str,
    label: str,
    unit: str | None,
    missing: MissingParameter,
    *,
    notes: str = "",
) -> Quantity:
    return Quantity(
        quantity_id=qid,
        label=label,
        provenance=Provenance.UNKNOWN,
        unit=unit,
        evidence=missing.evidence,
        notes=notes or missing.reason,
    )


def drv(
    qid: str,
    label: str,
    value: float,
    unit: str,
    method: str,
    inputs: Sequence[str],
    *,
    uncertainty: Uncertainty | None = None,
    notes: str = "",
) -> Quantity:
    return derived(
        qid, label, value, unit, method, inputs,
        uncertainty=uncertainty, notes=notes,
    )


# --------------------------------------------------------------------------- #
# assumptions
# --------------------------------------------------------------------------- #

A_DILUTION_TWO_TIMES = Assumption(
    assumption_id="A-DILUTION-2X",
    statement=(
        "'diluted 2 times with H2O' is read as a final volume of 2 x the "
        "starting volume."
    ),
    rationale=(
        "The paper applies this same phrase in secs. 2.11 and 2.15. Under this "
        "reading the DEAE fraction of 250 mL becomes 500 mL, and the paper's own "
        "ZnCl2 formula (2 x V/100) then reproduces the reported 10 mL exactly. "
        "Reading it as a final volume of 250 mL would give 5 mL, which contradicts "
        "sec. 4.9. The alternative reading is therefore not used."
    ),
    affects=("S10_citrately_blocked:diluted_volume", "N10:zinc_chloride_volume"),
    evidence=(ev(3, section="2.11"), ev(3, section="2.12"), ev(4, section="4.9")),
)

A_LINEAR_INTERPOLATION = Assumption(
    assumption_id="A-INTERP-LINEAR",
    statement=(
        "Crossing times on the growth trajectory are linearly interpolated between "
        "adjacent digitized markers."
    ),
    rationale=(
        "Needed to locate when the digitized OD600 curve passes a reported OD600 "
        "threshold. Linear interpolation over the 1 h sampling interval is the "
        "least-assuming choice, but it is an assumption: the true curve is only "
        "known at the sampled points."
    ),
    affects=("S02_culture_broth:od600_25_crossing_h", "S02_culture_broth:od600_50_crossing_h"),
    evidence=(ev(5, figure="Fig. 3", section="4.2"),),
)


# --------------------------------------------------------------------------- #
# shared missing parameters
# --------------------------------------------------------------------------- #

MP_AU_CALIBRATION = MissingParameter(
    parameter_id="MP-AU-CALIBRATION",
    description="Conversion factor between absorbance units and protein mass",
    reason=(
        "sec. 2.18 states the spectrophotometer was calibrated with water. No path "
        "length and no extinction coefficient are given, so the AU scale is "
        "instrument-relative and cannot be converted to grams, molarity or IU."
    ),
    blocks=(
        "insulin_mass_from_au",
        "stage_recovery_percent",
        "final_activity_from_au",
    ),
    evidence=(ev(3, section="2.18"),),
)

MP_GROWTH_KINETICS = MissingParameter(
    parameter_id="MP-GROWTH-KINETICS",
    description="Growth and substrate-uptake parameters for the fermenter",
    reason=(
        "No specific growth rate, saturation constant, maintenance coefficient or "
        "feed rate is reported anywhere in the paper."
    ),
    blocks=("od600_from_inputs", "wet_biomass_from_inputs", "glucose_consumed"),
    evidence=(ev(2, section="2.4"),),
)

MP_OXYGEN_TRANSFER = MissingParameter(
    parameter_id="MP-OXYGEN-TRANSFER",
    description="Oxygen transfer and agitation parameters",
    reason=(
        "The paper reports no air flow, agitation rate, dissolved-oxygen trace or "
        "kLa, so it is not possible to know whether growth was oxygen limited."
    ),
    blocks=("dissolved_oxygen_profile", "specific_growth_rate_mu_max"),
    evidence=(ev(2, section="2.4"),),
)

MP_FOLDING_MODEL = MissingParameter(
    parameter_id="MP-FOLDING-MODEL",
    description="Renaturation rate constant, redox potential and aggregate fraction",
    reason=(
        "sec. 4.5 reports two yields at two temperatures and states that refolding "
        "depends on redox potential and pH but NOT on temperature. Two observations "
        "cannot define a yield function, and the paper's own conclusion contradicts "
        "a temperature-driven reading."
    ),
    blocks=("refolding_yield_predictive", "refolding_time_predictive"),
    evidence=(ev(4, section="4.5"), ev(7, section="5")),
)

MP_INDUCTION_TIME = MissingParameter(
    parameter_id="MP-INDUCTION-TIME",
    description="Time point at which induction was performed",
    reason=(
        "sec. 2.4 states a total growth time and a post-induction duration but never "
        "states when induction occurred. It cannot be recovered from Fig. 3 either."
    ),
    blocks=("induction_time_h", "post_induction_start_h"),
    evidence=(ev(2, section="2.4"),),
)

MP_HOMOGENIZER = MissingParameter(
    parameter_id="MP-HOMOGENIZER",
    description="Homogenizer pressure and number of passes",
    reason=(
        "sec. 2.5 states only that cells 'were lysed by a high-pressure "
        "homogenizer', with no pressure, valve setting or cycle count."
    ),
    blocks=("lysis_efficiency",),
    evidence=(ev(2, section="2.5"),),
)

MP_A280_SOLUTION = MissingParameter(
    parameter_id="MP-A280-SOLUTION",
    description="A280 value and cuvette path length for the protein solutions",
    reason=(
        "The citraconylation and trypsin dosing formulas (secs. 2.8, 2.9) require "
        "A280nm, but the paper reports neither the A280 of any solution nor the "
        "path length."
    ),
    blocks=("citraconic_anhydride_volume_from_formula", "trypsin_volume_from_formula"),
    evidence=(ev(2, section="2.8"), ev(3, section="2.9")),
)

MP_DISSOLUTION_VOLUME = MissingParameter(
    parameter_id="MP-DISSOLUTION-VOLUME",
    description="Volume of buffer used to dissolve the 17.9 g inclusion-body aliquot",
    reason=(
        "sec. 2.6 specifies buffer composition but no volume, and sec. 4.4 reports "
        "5460 AU without a concentration. The dissolved protein concentration is "
        "therefore not computable."
    ),
    blocks=("dissolved_protein_concentration",),
    evidence=(ev(2, section="2.6"), ev(4, section="4.4")),
)

MP_CULTURE_MEDIUM = MissingParameter(
    parameter_id="MP-CULTURE-MEDIUM",
    description="Full composition of GMS growth medium",
    reason=(
        "GMS medium is cited to WO96/20724 A1 and never enumerated in this paper, "
        "so the substrate concentrations needed for any growth or substrate "
        "balance are unavailable."
    ),
    blocks=("glucose_initial_concentration", "nutrient_balance"),
    evidence=(ev(2, section="2.4"),),
)


# --------------------------------------------------------------------------- #
# streams
# --------------------------------------------------------------------------- #


def _build_streams(graph: ProcessGraph) -> None:
    """Declare every material stream with its producer, consumer and lineage."""
    prev: str | None = None

    def stream(
        sid: str,
        name: str,
        kind: StreamKind,
        *,
        produced_by: str | None,
        consumed_by: str | None,
        description: str,
        evidence: Iterable[EvidenceRef] = (),
    ) -> MaterialStream:
        nonlocal prev
        lineage = (prev,) if prev else ()
        prev = sid
        return graph.add_stream(
            MaterialStream(
                stream_id=sid,
                name=name,
                kind=kind,
                produced_by=produced_by,
                consumed_by=consumed_by,
                lineage=lineage,
                description=description,
                evidence=tuple(evidence),
            )
        )

    stream("S01_inoculum", "Inoculum culture", StreamKind.FERMENTATION_MEDIUM,
           produced_by=None, consumed_by="N01",
           description="50 mL GMS medium grown in a shaking flask; external feed to the graph.",
           evidence=[ev(2, section="2.4")])
    stream("S02_culture_broth", "Fermenter culture broth", StreamKind.FERMENTATION_MEDIUM,
           produced_by="N01", consumed_by="N02",
           description="4 L of GMS medium culture at the end of fermentation, carrying the Fig. 3 growth trajectory.",
           evidence=[ev(2, section="2.4"), ev(4, section="4.2"), ev(5, figure="Fig. 3")])
    stream("S03_wet_biomass", "Harvested wet biomass", StreamKind.WET_BIOMASS,
           produced_by="N02", consumed_by="N03",
           description="Pelleted E. coli 20 cells, 15,000 x g / 15 min / 4 C.",
           evidence=[ev(2, section="2.5")])
    stream("S04_inclusion_bodies", "Isolated inclusion bodies", StreamKind.INCLUSION_BODIES,
           produced_by="N03", consumed_by="N04",
           description="Washed inclusion-body pellet, stored at -30 C.",
           evidence=[ev(2, section="2.5"), ev(4, section="4.3")])
    stream("S05_denatured_solution", "Dissolved inclusion-body solution", StreamKind.DENATURED_PROTEIN_SOLUTION,
           produced_by="N04", consumed_by="N05",
           description="Clarified protein solution at pH 10.8 after 45 min at pH ~11.9.",
           evidence=[ev(2, section="2.6"), ev(4, section="4.4")])
    stream("S06_renatured_precursor", "Renatured insulin precursor", StreamKind.RENATURED_PRECURSOR,
           produced_by="N05", consumed_by="N06",
           description="Folded precursor adjusted to pH 9.0.",
           evidence=[ev(2, section="2.7"), ev(4, section="4.5")])
    stream("S07_citraconylated", "Citraconylated precursor", StreamKind.CITRACONYLATED_PRECURSOR,
           produced_by="N06", consumed_by="N07",
           description="Lys/Arg-blocked precursor plus quenched ethanolamine.",
           evidence=[ev(2, section="2.8"), ev(3, section="2.8")])
    stream("S08_digested", "Trypsin digest of precursor", StreamKind.DIGESTED_PRECURSOR,
           produced_by="N07", consumed_by="N08",
           description="Aprotinin-inhibited digest at pH 8.8, conductivity < 5 mS.",
           evidence=[ev(3, section="2.9")])
    stream("S09_deae_fraction", "DEAE Sepharose insulin fraction", StreamKind.INSULIN_FRACTION,
           produced_by="N08", consumed_by="N09",
           description="Eluate in DE buffer (20 mM Tris pH 8.6 + 30% isopropanol).",
           evidence=[ev(4, section="4.7"), ev(3, section="2.10")])
    stream("S10_citrately_blocked", "Decitraconylated fraction", StreamKind.CITRATE_BLOCKED_FRACTION,
           produced_by="N09", consumed_by="N10",
           description="DEAE eluate diluted 2x and held at pH 2.9 to hydrolyse the citraconic amide.",
           evidence=[ev(3, section="2.11"), ev(4, section="4.8")])
    stream("S11_insulin_precipitate", "Insulin zinc precipitate", StreamKind.INSULIN_ZINC_PRECIPITATE,
           produced_by="N10", consumed_by=None,
           description="Insulin precipitated with ZnCl2 at pH 5.9; a storable intermediate, not fed forward within this node.",
           evidence=[ev(3, section="2.12"), ev(4, section="4.9")])
    stream("S12_dissolved_zinc_salt", "Dissolved zinc salt", StreamKind.DISSOLVED_ZINC_SALT,
           produced_by="N10", consumed_by="N11",
           description="Precipitate resuspended in water with 30 mM Tris pH 8.6 and EDTA, conductivity < 3 mS.",
           evidence=[ev(3, section="2.13"), ev(4, section="4.9")])
    stream("S13_q_fraction", "Q Sepharose insulin fraction", StreamKind.CHROMATOGRAPHIC_FRACTION,
           produced_by="N11", consumed_by="N12",
           description="Eluate in QE buffer (20 mM Tris pH 8.6 + 30% isopropanol).",
           evidence=[ev(4, section="4.10"), ev(3, section="2.14")])
    stream("S14_cpb_treated", "Carboxypeptidase B treated fraction", StreamKind.DIGESTED_PRECURSOR,
           produced_by="N12", consumed_by="N13",
           description="Q eluate after Lys-Arg removal at pH 8.8 for 16-18 h at room temperature.",
           evidence=[ev(3, section="2.15")])
    stream("S15_rp_hplc_fraction", "RP-HPLC insulin fraction", StreamKind.CHROMATOGRAPHIC_FRACTION,
           produced_by="N13", consumed_by="N14",
           description="ACE 5C18-300 eluate; insulin peak 90-105 min.",
           evidence=[ev(4, section="4.11"), ev(5, section="4.11"), ev(3, section="2.16"), ev(6, figure="Fig. 6")])
    stream("S16_g25_fraction", "Sephadex G-25 insulin fraction", StreamKind.CHROMATOGRAPHIC_FRACTION,
           produced_by="N14", consumed_by="N15",
           description="Buffer-exchanged insulin in 5 mM ammonium acetate pH 4.0.",
           evidence=[ev(5, section="4.12"), ev(3, section="2.17")])
    stream("S17_final_product", "Recombinant human insulin", StreamKind.FINAL_PRODUCT,
           produced_by="N15", consumed_by=None,
           description="Final characterized product; terminal stream of the graph.",
           evidence=[ev(6, section="4.13")])


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #


def _build_nodes(graph: ProcessGraph) -> None:
    _node_fermentation(graph)
    _node_harvest(graph)
    _node_lysis(graph)
    _node_dissolution(graph)
    _node_renaturation(graph)
    _node_citraconylation(graph)
    _node_trypsinization(graph)
    _node_deae(graph)
    _node_decitraconylation(graph)
    _node_zinc(graph)
    _node_q_sepharose(graph)
    _node_cpb(graph)
    _node_rp_hplc(graph)
    _node_g25(graph)
    _node_characterization(graph)


def _node_fermentation(graph: ProcessGraph) -> ProcessNode:
    p2 = ev(2, section="2.4 Cell culture")
    node = ProcessNode(
        node_id="N01",
        index=1,
        name="Fermentation",
        operation=OperationKind.FERMENTATION,
        input_streams=("S01_inoculum",),
        output_streams=("S02_culture_broth",),
        figure1_label="E. coli 20 cells culture",
        description=(
            "Escherichia coli 20 carrying pIBAINS, grown in a Bioflo Celligen 310 "
            "7.5 L fermenter on 4 L of GMS medium at 37 C, with exponential glucose "
            "and proline feeding, then pH-stat glucose feeding, then induction and "
            "a further 4-5 h to stationary phase."
        ),
        evidence=(p2, ev(4, section="4.2"), ev(5, figure="Fig. 3")),
    )

    node.operating_conditions.update({
        "inoculum_volume": rep("inoculum_volume", "Inoculum volume", 50, "mL", p2,
                               original_text="50 mL GMS medium"),
        "inoculum_cultivation_time": rep("inoculum_cultivation_time",
                                         "Inoculum cultivation time", 18, "h", p2),
        "inoculum_temperature": rep("inoculum_temperature", "Inoculum temperature",
                                    30, "degC", p2),
        "inoculum_target_od600": rng("inoculum_target_od600",
                                      "Target OD600 before inoculation", 0.5, 1.0,
                                      "OD600", p2,
                                      original_text="until the optical density at 600 nm was about 0.5-1.0"),
        "inoculum_tetracycline": rep("inoculum_tetracycline", "Tetracycline in inoculum",
                                      100, "ug/mL", p2),
        "inoculum_proline": rep("inoculum_proline", "Proline in inoculum", 600, "ug/mL", p2),
        "inoculum_thiamine": rep("inoculum_thiamine", "Thiamine in inoculum", 2, "ug/mL", p2),
        "fermenter_nominal_volume": rep("fermenter_nominal_volume",
                                        "Fermenter nominal capacity", 7.5, "L", p2,
                                        original_text="Bioflo Celligen 310 7.5 L fermenter"),
        "starting_medium_volume": rep("starting_medium_volume", "Starting medium volume",
                                      4, "L", p2,
                                      original_text="starting GMS medium volume 4 L"),
        "fermenter_temperature": rep("fermenter_temperature", "Fermenter temperature",
                                     37, "degC", p2,
                                     original_text="Cells were grown for 15-16 h at 37 C"),
        "growth_duration": rng("growth_duration", "Growth duration", 15, 16, "h", p2,
                               original_text="Cells were grown for 15-16 h at 37 C"),
        "post_induction_duration": rng("post_induction_duration", "Post-induction growth",
                                       4, 5, "h", p2,
                                       original_text="the culture was grown for 4-5 h"),
        "glucose_feed_concentration": rep("glucose_feed_concentration", "Glucose feed concentration",
                                          40, "%", p2, original_text="40% glucose"),
        "glucose_target_initial": rng("glucose_target_initial",
                                      "Glucose range during initial exponential feeding",
                                      70, 120, "mg/dL", p2,
                                      original_text="to maintain glucose concentration range 70-120 mg/dL"),
        "proline_feed_concentration": rep("proline_feed_concentration", "Proline feed concentration",
                                          12, "mg/mL", p2,
                                          original_text="12 mg/mL proline"),
        "ph_control_reagent": rep("ph_control_reagent", "pH-control reagent concentration",
                                  16, "%", p2, original_text="16% NH4OH"),
        "ph_stat_glucose_target": rng("ph_stat_glucose_target", "Glucose range during pH-stat feeding",
                                      30, 50, "mg/dL", p2,
                                      original_text="maintained by the pH-stat in the concentration range of 30-50 mg/dL"),
        "ph_stat_dead_band": rep("ph_stat_dead_band", "pH-stat dead band", 0.01, "1", p2,
                                 original_text="dead band was 0.01"),
        "glucose_limitation_od600": rng("glucose_limitation_od600",
                                        "OD600 at which glucose feeding was limited",
                                        25, 35, "OD600", p2,
                                        original_text="When OD600 nm reached about 25-35"),
        "stationary_phase_od600": rng("stationary_phase_od600", "OD600 at stationary phase",
                                      50, 60, "OD600", p2,
                                      original_text="until OD600 nm was about 50-60"),
    })
    node.condition_notes.update({
        "medium": "GMS medium (cited to WO96/20724 A1; composition not enumerated in this paper)",
        "host_strain": "Escherichia coli 20 IBA 1 carrying plasmid pIBAINS",
        "vector": "pIBAINS (4354 bp), deoP1P2 promoter, tetracycline resistance",
        "fermenter": "Bioflo Celligen 310 (Eppendorf), 7.5 L nominal",
        "ph_control": "pH controlled over the entire run by addition of 16% NH4OH",
        "feed_strategy": ("exponential 40% glucose + 12 mg/mL proline feeding; then glucose "
                          "starved to 0 g/dL; then pH-stat glucose feeding with acid"),
        "antibiotics_in_fermenter": "none used in the fermenter",
        "storage": "cells from glycerol stock at -80 C",
    })

    node.measurements.update({
        "od600_max": rep("od600_max", "Maximum OD600", 54.4, "OD600",
                         ev(4, section="4.2 Cell culture"),
                         original_text="Maximum OD600 nm was 54.4"),
    })
    # the paper also states the per-litre biomass figure, which lets the derived
    # g/L value be cross-checked against the source rather than trusted blindly
    node.measurements.update({
        "wet_biomass_g_per_L_reported": rep(
            "wet_biomass_g_per_L_reported", "Wet biomass per litre (as stated by the paper)",
            56, "g/L", ev(4, section="4.2"),
            original_text="56 g from 1 L of the culture media"),
    })

    # descriptive only: an apparent batch-average ratio, not a model parameter
    node.calculated["biomass_per_od_descriptive"] = drv(
        "biomass_per_od_descriptive",
        "Apparent wet biomass per OD600 (descriptive)",
        56.0 / 54.4,
        "g_per_L_per_OD600",
        "56 g/L / 54.4 OD600 = 1.029412 g/L per OD600",
        ["wet_biomass_g_per_L_reported", "od600_max"],
        notes=("Batch-average ratio of two reported numbers. Descriptive only: it is "
               "not a yield coefficient, no growth model is fitted from it, and it is "
               "not used to predict any batch."),
    )

    node.missing_parameters = (
        MissingParameter(parameter_id=MP_GROWTH_KINETICS.parameter_id,
                         description=MP_GROWTH_KINETICS.description,
                         reason=MP_GROWTH_KINETICS.reason, blocks=MP_GROWTH_KINETICS.blocks,
                         evidence=MP_GROWTH_KINETICS.evidence),
        MissingParameter(parameter_id=MP_OXYGEN_TRANSFER.parameter_id,
                         description=MP_OXYGEN_TRANSFER.description,
                         reason=MP_OXYGEN_TRANSFER.reason, blocks=MP_OXYGEN_TRANSFER.blocks,
                         evidence=MP_OXYGEN_TRANSFER.evidence),
        MissingParameter(parameter_id=MP_INDUCTION_TIME.parameter_id,
                         description=MP_INDUCTION_TIME.description,
                         reason=MP_INDUCTION_TIME.reason, blocks=MP_INDUCTION_TIME.blocks,
                         evidence=MP_INDUCTION_TIME.evidence),
        MissingParameter(parameter_id=MP_CULTURE_MEDIUM.parameter_id,
                         description=MP_CULTURE_MEDIUM.description,
                         reason=MP_CULTURE_MEDIUM.reason, blocks=MP_CULTURE_MEDIUM.blocks,
                         evidence=MP_CULTURE_MEDIUM.evidence),
    )
    node.operating_conditions["induction_time"] = unk(
        "induction_time", "Induction time point", "h", MP_INDUCTION_TIME)
    node.operating_conditions["od600_from_inputs"] = unk(
        "od600_from_inputs", "OD600 predicted from medium and feed inputs", "OD600",
        MP_GROWTH_KINETICS)
    node.operating_conditions["wet_biomass_from_inputs"] = unk(
        "wet_biomass_from_inputs", "Wet biomass predicted from medium and feed inputs", "g",
        MP_GROWTH_KINETICS)
    node.operating_conditions["specific_growth_rate"] = unk(
        "specific_growth_rate", "Specific growth rate", "1/h", MP_GROWTH_KINETICS)
    node.operating_conditions["dissolved_oxygen"] = unk(
        "dissolved_oxygen", "Dissolved oxygen profile", "1", MP_OXYGEN_TRANSFER)

    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="source_discrepancy:growth_duration_ambiguity",
            message=(
                "sec. 2.4 reports two durations without stating how they relate: "
                "'Cells were grown for 15-16 h at 37 C' and 'After induction, the "
                "culture was grown for 4-5 h until OD600 nm was about 50-60'. Whether "
                "15-16 h is the total batch duration or the pre-induction duration is "
                "not stated, and the two readings differ by 4-5 h. The digitized "
                "Fig. 3 axis ends at 19 h, which is consistent with a total of about "
                "19-21 h under the second reading but does not settle it. Both "
                "durations are stored as reported intervals and neither is adjusted."
            ),
            where="N01",
            evidence=(p2, ev(5, figure="Fig. 3")),
        )
    )

    node.supported_equations = ("accounting.total_activity_from_per_volume",)

    graph.add_node(node)

    # Fig. 3 reference trajectory, carried on the broth stream it describes
    _attach_growth_trajectory(graph, node)
    return node


def _attach_growth_trajectory(graph: ProcessGraph, node: ProcessNode) -> None:
    """Load the digitized Fig. 3 markers onto S02 and derive two crossing times."""
    data = fig3_trajectory()
    unc = data["digitization_method"]["declared_uncertainty"]
    fig_ev = ev(5, figure="Fig. 3", section="4.2",
                quote="E. coli 20 growth curve. X-axis values are hours of culture, "
                      "y-axis values are optical density (OD) 600 nm.")
    stream = graph.stream("S02_culture_broth")
    pts = {float(p["hour"]): float(p["od600"]) for p in data["trajectory"]}

    for hour in sorted(pts):
        stream.put(
            digitized(
                f"od600_h{int(hour):02d}",
                f"OD600 at t = {int(hour)} h (Fig. 3, digitized)",
                pts[hour], "OD600", fig_ev,
                uncertainty=Uncertainty(
                    kind="digitization", lo=pts[hour] - unc["od600"],
                    hi=pts[hour] + unc["od600"], basis=unc["basis"],
                ),
                method=("marker centroid from the embedded raster of Fig. 3, "
                        "calibrated against the plot gridlines"),
            )
        )
    stream.put(
        digitized(
            "od600_plateau_max",
            "Maximum OD600 read off the Fig. 3 plateau (digitized)",
            max(pts[h] for h in (17.0, 18.0, 19.0)), "OD600", fig_ev,
            uncertainty=Uncertainty(kind="digitization", lo=53.17, hi=54.17,
                                    basis=unc["basis"]),
            method="highest plateau marker (17-19 h) read from Fig. 3",
        )
    )

    def crossing(target: float) -> tuple[float, str]:
        lo_h, hi_h = 13.0, 14.0
        lo_o, hi_o = pts[lo_h], pts[hi_h]
        frac = (target - lo_o) / (hi_o - lo_o)
        return lo_h + frac, (
            f"{lo_h:.0f} h + ({target} - {lo_o}) / ({hi_o} - {lo_o}) * ({hi_h:.0f} - {lo_h:.0f}) h"
        )

    t25, expr25 = crossing(25.0)
    t50, expr50 = crossing(50.0)
    stream.put(
        derived(
            "od600_25_crossing_h",
            "Time at which OD600 reaches the reported glucose-limitation threshold of 25",
            t25, "h", f"linear interpolation: {expr25} = {t25:.4f} h",
            ["od600_h13", "od600_h14"],
            notes="Digitized endpoints; interpolation is assumption " + A_LINEAR_INTERPOLATION.assumption_id,
        )
    )
    stream.put(
        derived(
            "od600_50_crossing_h",
            "Time at which OD600 reaches 50",
            t50, "h", f"linear interpolation: {expr50} = {t50:.4f} h",
            ["od600_h15", "od600_h16"],
            notes="Digitized endpoints; interpolation is assumption " + A_LINEAR_INTERPOLATION.assumption_id,
        )
    )

    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="source_discrepancy:digitized_vs_reported_od600",
            message=(
                "The digitized Fig. 3 plateau reaches "
                f"{max(pts[h] for h in (17.0, 18.0, 19.0)):.2f} OD600, while sec. 4.2 "
                "states a maximum of 54.4 OD600. The difference (0.73) is larger than "
                "the declared +/-0.5 OD digitization uncertainty. Both values are "
                "retained; neither is adjusted to match the other."
            ),
            where="N01",
            evidence=(fig_ev, ev(4, section="4.2")),
        )
    )
    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="source_discrepancy:induction_order",
            message=(
                "The narrative order in sec. 2.4 cannot be reconciled with Fig. 3. "
                "Glucose feeding is limited once OD600 reaches 25-35, which the "
                f"digitized curve places at about {t25:.1f} h; but a 4-5 h "
                "post-induction phase ending at OD600 50-60 (reached at about "
                f"{t50:.1f} h) would place induction at about "
                f"{t50 - 5:.1f}-{t50 - 4:.1f} h, i.e. BEFORE the glucose limitation. "
                "The induction time is not stated, so the conflict is recorded rather "
                "than resolved."
            ),
            where="N01",
            evidence=(ev(2, section="2.4"), fig_ev),
        )
    )


def _node_harvest(graph: ProcessGraph) -> ProcessNode:
    p = ev(2, section="2.5 Isolation of inclusion bodies")
    node = ProcessNode(
        node_id="N02", index=2, name="Biomass harvest", operation=OperationKind.HARVEST,
        input_streams=("S02_culture_broth",), output_streams=("S03_wet_biomass",),
        figure1_label="E. coli 20 cells culture (harvest step)",
        description="Cells separated from the culture medium by refrigerated centrifugation.",
        evidence=(p, ev(4, section="4.2")),
    )
    node.operating_conditions.update({
        "centrifugation_force": rep("centrifugation_force", "Harvest centrifugal force",
                                    15000, "xg", p,
                                    original_text="centrifugation at 15,000 x g"),
        "centrifugation_time": rep("centrifugation_time", "Harvest centrifugation time",
                                   15, "min", p),
        "centrifugation_temperature": rep("centrifugation_temperature",
                                          "Harvest centrifugation temperature", 4, "degC", p),
    })
    node.condition_notes["phase"] = "harvest of cells from the fermentation broth"
    graph.add_node(node)

    # wet biomass total belongs to the physical stream
    graph.stream("S03_wet_biomass").put(
        rep("wet_biomass_total", "Total wet biomass", 224, "g",
            ev(4, section="4.2"),
            original_text="we obtained about 224 g of wet biomass")
    )
    return node


def _node_lysis(graph: ProcessGraph) -> ProcessNode:
    p = ev(2, section="2.5 Isolation of inclusion bodies")
    node = ProcessNode(
        node_id="N03", index=3, name="Cell lysis and inclusion-body isolation",
        operation=OperationKind.LYSIS,
        input_streams=("S03_wet_biomass",), output_streams=("S04_inclusion_bodies",),
        figure1_label="Inclusion bodies isolation",
        description=(
            "Lysozyme/Triton lysis, high-pressure homogenization, then differential "
            "centrifugation and two wash steps to isolate inclusion bodies."
        ),
        evidence=(p, ev(4, section="4.3")),
    )
    node.operating_conditions.update({
        "lysozyme_concentration": rep("lysozyme_concentration", "Lysozyme in lysis buffer",
                                      0.043, "%", p),
        "lysozyme_mix_time": rep("lysozyme_mix_time", "Lysozyme mixing time", 30, "min", p),
        "triton_x100_volume": rep("triton_x100_volume", "Triton X-100 added", 20, "mL", p,
                                  original_text="20 ml of Triton X-100 was added"),
        "triton_stir_time": rep("triton_stir_time", "Stirring after Triton addition", 10, "min", p),
        "clarification_force": rep("clarification_force", "Centrifugal force after homogenization",
                                   18400, "xg", p),
        "clarification_time": rep("clarification_time", "Clarification time", 15, "min", p),
        "clarification_temperature": rep("clarification_temperature", "Clarification temperature",
                                         4, "degC", p),
        "final_centrifugation_force": rep("final_centrifugation_force",
                                          "Final inclusion-body centrifugation force",
                                          15000, "xg", p),
        "final_centrifugation_time": rep("final_centrifugation_time",
                                         "Final inclusion-body centrifugation time", 15, "min", p),
        "final_centrifugation_temperature": rep("final_centrifugation_temperature",
                                                "Final inclusion-body centrifugation temperature",
                                                4, "degC", p),
        "storage_temperature": rep("storage_temperature", "Inclusion-body storage temperature",
                                   -30, "degC", p),
    })
    node.condition_notes.update({
        "lysis_buffer": "50 mM Tris-HCl pH 8.0, 500 mM NaCl, 1 mM EDTA, 0.043% lysozyme",
        "wash_1": "50 mM Tris-HCl pH 8.0, 500 mM NaCl, 1% Triton X-100",
        "wash_2": "twice with 50 mM Tris-HCl pH 8.0, 500 mM NaCl",
        "lysis_method": "high-pressure homogenizer (pressure and cycle count not stated)",
    })
    node.measurements.update({
        "inclusion_bodies_g_per_L_reported": rep(
            "inclusion_bodies_g_per_L_reported",
            "Inclusion bodies per litre (as stated by the paper)", 14.5, "g/L",
            ev(4, section="4.3"),
            original_text="14.5 g from 1 L of the culture media"),
    })
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_HOMOGENIZER.parameter_id,
                         description=MP_HOMOGENIZER.description,
                         reason=MP_HOMOGENIZER.reason, blocks=MP_HOMOGENIZER.blocks,
                         evidence=MP_HOMOGENIZER.evidence),
    )
    graph.add_node(node)

    graph.stream("S04_inclusion_bodies").put(
        rep("inclusion_bodies_total", "Total inclusion bodies", 58, "g",
            ev(4, section="4.3"),
            original_text="we obtained about 58 g of inclusion bodies")
    )
    return node


def _node_dissolution(graph: ProcessGraph) -> ProcessNode:
    p = ev(2, section="2.6 Dissolution of inclusion bodies")
    node = ProcessNode(
        node_id="N04", index=4, name="Inclusion-body dissolution",
        operation=OperationKind.DISSOLUTION,
        input_streams=("S04_inclusion_bodies",), output_streams=("S05_denatured_solution",),
        figure1_label="Inclusion bodies dissolution",
        description=(
            "Inclusion bodies dissolved in 12 mM NaHCO3 with 0.2 mM EDTA at pH ~11.9 "
            "for 45 min, adjusted to pH 10.8, then clarified at 24,000 x g."
        ),
        evidence=(p, ev(4, section="4.4")),
    )
    node.operating_conditions.update({
        "carbonate_buffer": rep("carbonate_buffer", "NaHCO3 buffer concentration", 12, "mM", p),
        "edta_concentration": rep("edta_concentration", "EDTA in dissolution buffer", 0.2, "mM", p),
        "initial_ph": rep("initial_ph", "Initial dissolution pH", 11.9, "pH", p,
                          original_text="adjusted to about 11.9 with 5 M NaOH"),
        "dissolution_time": rep("dissolution_time", "Dissolution time", 45, "min", p),
        "adjusted_ph": rep("adjusted_ph", "pH after dissolution", 10.8, "pH", p,
                           original_text="the pH was adjusted to 10.8 with 2 M HCl"),
        "clarification_force": rep("clarification_force", "Debris clarification force",
                                   24000, "xg", p),
        "clarification_time": rep("clarification_time", "Debris clarification time", 15, "min", p),
        "clarification_temperature": rep("clarification_temperature", "Debris clarification temperature",
                                         4, "degC", p),
    })
    node.condition_notes.update({
        "temperature": "room temperature",
        "pH_adjustment_up": "5 M NaOH",
        "pH_adjustment_down": "2 M HCl",
        "purpose": "removal of insoluble debris",
    })
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_DISSOLUTION_VOLUME.parameter_id,
                         description=MP_DISSOLUTION_VOLUME.description,
                         reason=MP_DISSOLUTION_VOLUME.reason,
                         blocks=MP_DISSOLUTION_VOLUME.blocks,
                         evidence=MP_DISSOLUTION_VOLUME.evidence),
    )
    graph.add_node(node)

    s = graph.stream("S05_denatured_solution")
    s.put(rep("ib_aliquot_mass", "Inclusion-body aliquot dissolved", 17.9, "g",
              ev(4, section="4.4"),
              original_text="An aliquot of 17.9 g of inclusion bodies was dissolved"))
    s.put(rep("dissolved_protein", "Dissolved protein (total AU)", 5460, "AU",
              ev(4, section="4.4"),
              original_text="we obtained 5460 AU of protein",
              notes=("Absorbance units at 280 nm on a water-blanked instrument; not a "
                     "mass, concentration or activity.")))
    s.put(Quantity(
        quantity_id="dissolved_protein_concentration",
        label="Dissolved protein concentration",
        provenance=Provenance.UNKNOWN,
        unit="AU/mL",
        evidence=MP_DISSOLUTION_VOLUME.evidence,
        notes=MP_DISSOLUTION_VOLUME.reason,
    ))
    return node


def _node_renaturation(graph: ProcessGraph) -> ProcessNode:
    p = ev(2, section="2.7 Renaturation")
    r = ev(4, section="4.5 Renaturation")
    node = ProcessNode(
        node_id="N05", index=5, name="Protein renaturation", operation=OperationKind.RENATURATION,
        input_streams=("S05_denatured_solution",), output_streams=("S06_renatured_precursor",),
        figure1_label="Renaturation",
        description=(
            "Oxidative refolding of the dissolved precursor under vigorous stirring "
            "and aeration, then adjustment to pH 9.0."
        ),
        evidence=(p, r),
    )
    node.operating_conditions.update({
        "folding_time_methods": rep("folding_time_methods", "Renaturation time (methods)",
                                    18, "h", p,
                                    original_text="allowed to fold during the subsequent 18 h period"),
        "folding_time_results": rng("folding_time_results", "Refolding time (results)",
                                    18, 19, "h", r,
                                    original_text="The refolding process was completed after 18-19 h"),
        "final_ph": rep("final_ph", "pH at end of renaturation", 9.0, "pH", p,
                        original_text="the pH was adjusted to 9.0 with 2 M HCl"),
    })
    node.condition_notes.update({
        "agitation": "vigorous stirring and aeration (no rate, air flow or redox control reported)",
        "temperatures_studied": "room temperature and 8 C (sec. 2.7); results quote 7-8 C",
        "pH_adjustment": "2 M HCl",
        "reported_dependency": (
            "sec. 4.5: refolding 'was shown to depend on the redox potential and the "
            "pH value, but not on the temperature'"
        ),
    })
    node.measurements.update({
        "refolding_yield_room_temperature": rng(
            "refolding_yield_room_temperature", "Renaturation yield at room temperature",
            95, 96, "%", r, original_text="the yield was around 95-96%"),
        "refolding_yield_low_temperature": rep(
            "refolding_yield_low_temperature", "Renaturation yield at 7-8 C",
            99, "%", r, original_text="at 7-8 C the yield was around 99%"),
    })
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_FOLDING_MODEL.parameter_id,
                         description=MP_FOLDING_MODEL.description,
                         reason=MP_FOLDING_MODEL.reason, blocks=MP_FOLDING_MODEL.blocks,
                         evidence=MP_FOLDING_MODEL.evidence),
    )
    node.operating_conditions["refolding_yield_predictive"] = unk(
        "refolding_yield_predictive", "Refolding yield predicted from conditions", "%",
        MP_FOLDING_MODEL)
    node.operating_conditions["refolding_time_predictive"] = unk(
        "refolding_time_predictive", "Refolding time predicted from conditions", "h",
        MP_FOLDING_MODEL)
    node.supported_equations = ("accounting.percent_yield_from_au",)
    node.assumptions = (A_LINEAR_INTERPOLATION,)

    node.add_validation(
        ValidationMessage(
            severity=Severity.ERROR,
            code="source_discrepancy:refolding_yield_vs_au",
            message=(
                "sec. 4.4 reports 5460 AU after dissolution and sec. 4.5 reports 5450 "
                "AU after renaturation, which is 5450/5460 = 99.82%. The same section "
                "states a room-temperature yield of 95-96%, which would imply only "
                "5187-5242 AU. The two statements are not on the same basis; both are "
                "retained and neither is adjusted."
            ),
            where="N05",
            evidence=(ev(4, section="4.4"), r),
        )
    )
    graph.add_node(node)

    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="source_discrepancy:refolding_duration_methods_vs_results",
            message=(
                "sec. 2.7 states the precursor was 'allowed to fold during the "
                "subsequent 18 h period'; sec. 4.5 states 'The refolding process was "
                "completed after 18-19 h'. The methods value is stored as an exact "
                "18 h and the results value as the 18-19 h interval; neither is "
                "reconciled against the other and no refolding rate is derived from "
                "them."
            ),
            where="N05",
            evidence=(ev(2, section="2.7 Renaturation"), r),
        )
    )

    graph.stream("S06_renatured_precursor").put(
        rep("protein_after_refolding", "Protein after renaturation (total AU)", 5450, "AU",
            r, original_text="We obtained 5450 AU of protein. The refolding process was "
            "completed after 18-19 h")
    )
    return node


def _node_citraconylation(graph: ProcessGraph) -> ProcessNode:
    node = ProcessNode(
        node_id="N06", index=6, name="Citraconylation", operation=OperationKind.CHEMICAL_MODIFICATION,
        input_streams=("S06_renatured_precursor",), output_streams=("S07_citraconylated",),
        figure1_label="Citraconylation reaction",
        description=(
            "Reversible blocking of primary amines with citraconic anhydride to "
            "control tryptic digestion and prevent insulin degradation."
        ),
        evidence=(ev(2, section="2.8 Citraconylation reaction"),
                  ev(3, section="2.8 Citraconylation reaction")),
    )
    node.operating_conditions.update({
        "citraconic_anhydride_volume": rep("citraconic_anhydride_volume",
                                           "Citraconic anhydride added", 1, "mL",
                                           ev(3, section="2.8"),
                                           original_text="1 ml of citraconic anhydride"),
        "naoh_concentration": rep("naoh_concentration", "NaOH used for pH control",
                                  5, "M", ev(3, section="2.8")),
        "ph_window_low": rep("ph_window_low", "Lower bound of pH window", 8.7, "pH",
                             ev(3, section="2.8")),
        "ph_window_high": rep("ph_window_high", "Upper bound of pH window", 9.3, "pH",
                              ev(3, section="2.8")),
        "reaction_time": rep("reaction_time", "Citraconylation reaction time", 2.5, "h",
                             ev(3, section="2.8")),
        "ethanolamine_volume": rep("ethanolamine_volume", "2 M ethanolamine added", 3, "mL",
                                   ev(3, section="2.8"),
                                   original_text="3 ml of a 2 M ethanolamine solution"),
        "ethanolamine_concentration": rep("ethanolamine_concentration",
                                          "Ethanolamine concentration", 2, "M",
                                          ev(3, section="2.8")),
        "quench_time": rep("quench_time", "Mixing time after ethanolamine", 45, "min",
                           ev(3, section="2.8")),
    })
    node.condition_notes.update({
        "pH_control": "anhydride and NaOH added in portions so pH stayed in 8.7-9.3",
        "chemistry": "blocking occurs at alkaline pH (7-9); hydrolysis at pH 3-4 releases citraconic acid and restores the amine (sec. 4.8)",
    })
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_A280_SOLUTION.parameter_id,
                         description=MP_A280_SOLUTION.description,
                         reason=MP_A280_SOLUTION.reason, blocks=MP_A280_SOLUTION.blocks,
                         evidence=MP_A280_SOLUTION.evidence),
    )
    node.source_expressions = (
        SourceExpression(
            expression_id="E-CITRACONYLATION-ANHYDRIDE",
            label="Citraconic anhydride amount",
            expression_text="0.2 x V solution (dm3) x A280 nm",
            variable_definitions={
                "V solution": "volume of the protein solution, in dm3",
                "A280 nm": "absorbance at 280 nm (instrument- and path-length dependent)",
            },
            source_unit="mL of citraconic anhydride",
            expected_output_unit="mL",
            executable=False,
            ambiguity=(
                "A280nm is a raw absorbance while the rest of the paper reports AU "
                "(absorbance x volume). The paper gives neither an A280 value nor a "
                "path length, and '0.2 x dm3 x absorbance' does not reduce to a volume."
            ),
            evidence=(ev(3, section="2.8"),),
        ),
        SourceExpression(
            expression_id="E-ETHANOLAMINE",
            label="Ethanolamine amount",
            expression_text="3 x V citraconic anhydride",
            variable_definitions={
                "V citraconic anhydride": "volume of citraconic anhydride used",
            },
            source_unit="mL of 2 M ethanolamine",
            expected_output_unit="mL",
            executable=False,
            ambiguity=(
                "Blocked upstream: the anhydride volume cannot be computed because "
                "E-CITRACONYLATION-ANHYDRIDE is not executable. The paper separately "
                "reports an absolute 3 mL of 2 M ethanolamine, which is recorded."
            ),
            evidence=(ev(3, section="2.8"),),
        ),
    )
    node.refused_equations = (
        "source_formula.citraconylation_anhydride_amount",
        "source_formula.ethanolamine_amount",
    )
    graph.add_node(node)
    return node


def _node_trypsinization(graph: ProcessGraph) -> ProcessNode:
    p = ev(3, section="2.9 Trypsinization")
    node = ProcessNode(
        node_id="N07", index=7, name="Trypsinization", operation=OperationKind.PROTEOLYSIS,
        input_streams=("S07_citraconylated",), output_streams=("S08_digested",),
        figure1_label="Trypsinization reaction",
        description=(
            "Tryptic digestion of the citraconylated precursor at pH 8.8, stopped "
            "with aprotinin."
        ),
        evidence=(p,),
    )
    node.operating_conditions.update({
        "reaction_ph": rep("reaction_ph", "Digestion pH", 8.8, "pH", p,
                           original_text="the pH of the solution was adjusted to 8.8"),
        "conductivity_limit": rep("conductivity_limit", "Conductivity before loading",
                                  5, "mS", p, original_text="diluted so that the conductivity was below 5 mS"),
        "trypsin_volume": rep("trypsin_volume", "1% trypsin solution added", 70, "uL", p,
                              original_text="70 ul of a 1% trypsin solution"),
        "trypsin_concentration": rep("trypsin_concentration", "Trypsin solution concentration",
                                     1, "g_per_100mL", p, original_text="1% trypsin solution"),
        "reaction_time": rng("reaction_time", "Digestion time", 16, 18, "h", p,
                             original_text="mixed for about 16-18 h at room temperature"),
        "aprotinin_concentration": rep("aprotinin_concentration", "Aprotinin concentration",
                                       1, "mg/mL", p),
    })
    node.condition_notes.update({
        "inhibitor": "reaction inhibited with 1 mg/ml aprotinin",
        "chemistry": "Lys-Arg linker cleavage releasing insulin A and B chains",
        "reaction_temperature": ("room temperature; the paper states no numeric set point, "
                                 "so none is recorded as a quantity"),
    })
    node.source_expressions = (
        SourceExpression(
            expression_id="E-TRYPSIN",
            label="Trypsin amount",
            expression_text="A280 nm x V solution (dm3)/75",
            variable_definitions={
                "A280 nm": "absorbance at 280 nm (instrument- and path-length dependent)",
                "V solution": "volume of the protein solution, in dm3",
            },
            source_unit="uL of 1% trypsin",
            expected_output_unit="uL",
            executable=False,
            ambiguity=(
                "Same A280-vs-AU and path-length ambiguity as the citraconylation "
                "formula, and the divisor 75 carries no stated unit. The paper "
                "separately reports an absolute 70 uL of 1% trypsin, which is recorded."
            ),
            evidence=(p,),
        ),
        SourceExpression(
            expression_id="E-APROTININ",
            label="Aprotinin amount",
            expression_text="V trypsin/21",
            variable_definitions={"V trypsin": "volume of 1% trypsin solution used"},
            source_unit="uL of 1 mg/ml aprotinin",
            expected_output_unit="uL",
            executable=True,
            ambiguity=None,
            evidence=(p,),
        ),
    )
    node.assumptions = (
        Assumption(
            assumption_id="A-APROTININ-UNIT",
            statement=(
                "V trypsin is taken to be a volume in the same unit on both sides, so "
                "the ratio is dimensionless and yields uL."
            ),
            rationale=(
                "The printed formula V[trypsin]/21 is a pure ratio. It is evaluated "
                "only because the paper reports an absolute trypsin volume (70 uL) for "
                "the reference batch. If the paper intended a different unit the "
                "result would be off by that unit factor; the result is therefore "
                "reported as a derived dose, not as a validated procedure value."
            ),
            affects=("N07:aprotinin_volume",),
            evidence=(p,),
        ),
    )
    node.supported_equations = ("source_formula.aprotinin_from_trypsin_volume",)
    node.refused_equations = ("source_formula.trypsin_amount",)
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_A280_SOLUTION.parameter_id,
                         description=MP_A280_SOLUTION.description,
                         reason=MP_A280_SOLUTION.reason, blocks=MP_A280_SOLUTION.blocks,
                         evidence=MP_A280_SOLUTION.evidence),
    )
    graph.add_node(node)
    return node


def _deae_common(node: ProcessNode, sec: str, pdf_page: int) -> None:
    node.operating_conditions.update({
        "equilibration_1": rep("equilibration_1", "First equilibration buffer", 0.5, "M",
                               ev(pdf_page, section=sec),
                               original_text="equilibrated with 0.5 M Tris pH 8.6"),
        "equilibration_2": rep("equilibration_2", "Second equilibration buffer", 20, "mM",
                               ev(pdf_page, section=sec),
                               original_text="followed by 20 mM Tris pH 8.6"),
    })
    node.condition_notes["tris_buffer"] = "Tris-HCl, pH 8.6"
    node.condition_notes["modifier"] = "isopropanol used as the elution modifier"


def _node_deae(graph: ProcessGraph) -> ProcessNode:
    sec = "2.10 Low-pressure chromatography on DEAE Sepharose"
    p = ev(3, section=sec)
    node = ProcessNode(
        node_id="N08", index=8, name="DEAE Sepharose purification",
        operation=OperationKind.CHROMATOGRAPHY,
        input_streams=("S08_digested",), output_streams=("S09_deae_fraction",),
        figure1_label="DEAE Sepharose chromatography",
        description="Anion-exchange low-pressure chromatography; insulin eluted with DE buffer.",
        evidence=(p, ev(4, section="4.7"), ev(5, figure="Fig. 4")),
    )
    _deae_common(node, sec, 3)
    node.operating_conditions.update({
        "wash_dw_i_conductivity": rep("wash_dw_i_conductivity", "DW I conductivity", 6, "mS", p),
        "wash_dw_ii_conductivity": rep("wash_dw_ii_conductivity", "DW II conductivity", 3, "mS", p),
        "wash_dw_ii_isopropanol": rep("wash_dw_ii_isopropanol", "DW II isopropanol", 20, "%", p),
        "elution_de_conductivity": rep("elution_de_conductivity", "DE elution conductivity", 6, "mS", p),
        "elution_de_isopropanol": rep("elution_de_isopropanol", "DE elution isopropanol", 30, "%", p),
        "flow_rate": rep("flow_rate", "Column flow rate", 15, "mL/min", ev(5, figure="Fig. 4")),
    })
    node.condition_notes.update({
        "resin": "DEAE Sepharose Fast Flow (GE Healthcare)",
        "wash_dw_i": "20 mM Tris pH 8.6, 3 CV (no isopropanol stated in the wash buffer)",
        "wash_dw_ii": "20 mM Tris pH 8.6 + 20% isopropanol, 3 CV",
        "elution_de": "20 mM Tris pH 8.6 + 30% isopropanol, 2 CV",
        "strip": "2 CV of 1 M NaCl then 0.5 M NaOH",
        "insulin_peak": "approximately 2650-3200 mL (Fig. 4)",
        "detection": "A280",
    })
    graph.add_node(node)

    s = graph.stream("S09_deae_fraction")
    s.put(rep("fraction_volume", "Insulin fraction volume", 250, "mL",
              ev(4, section="4.7"),
              original_text="250 ml of the insulin fraction was obtained"))
    s.put(rep("protein_concentration", "Protein concentration", 8.57, "AU/mL",
              ev(4, section="4.7"),
              original_text="The protein concentration was 8.57 AU/ml"))
    return node


def _node_decitraconylation(graph: ProcessGraph) -> ProcessNode:
    p = ev(3, section="2.11 Decitraconylation")
    node = ProcessNode(
        node_id="N09", index=9, name="Decitraconylation",
        operation=OperationKind.CHEMICAL_MODIFICATION,
        input_streams=("S09_deae_fraction",), output_streams=("S10_citrately_blocked",),
        figure1_label="Decitraconylation",
        description=(
            "Acid hydrolysis of the citraconic amide at pH 2.9 to restore the "
            "original primary amines."
        ),
        evidence=(p, ev(4, section="4.8")),
    )
    node.operating_conditions.update({
        "dilution_factor": rep("dilution_factor", "Dilution with water", 2, "fold", p,
                               original_text="diluted 2 times with H2O"),
        "reaction_ph": rep("reaction_ph", "Decitraconylation pH", 2.9, "pH", p,
                           original_text="the pH was lowered to 2.9"),
        "reaction_time": rep("reaction_time", "Stirring time", 1, "h", p),
        "hold_temperature": rep("hold_temperature", "Overnight hold temperature", 4, "degC", p),
    })
    node.condition_notes.update({
        "pH_adjustment": "2 M HCl",
        "hold": "stirred 1 h then left at 4 C overnight",
        "chemistry": "at pH 3-4 the amide linkage hydrolyses and citraconic acid is released, restoring the amine (sec. 4.8)",
    })
    node.assumptions = (A_DILUTION_TWO_TIMES,)
    node.supported_equations = ("volume.diluted",)
    graph.add_node(node)
    return node


def _node_zinc(graph: ProcessGraph) -> ProcessNode:
    p12 = ev(3, section="2.12 Precipitation of insulin")
    p13 = ev(3, section="2.13 Dissolving the zinc salt")
    p49 = ev(4, section="4.9 Precipitation of insulin and dissolving the zinc salt")
    node = ProcessNode(
        node_id="N10", index=10, name="Zinc precipitation and zinc-salt dissolution",
        operation=OperationKind.PRECIPITATION,
        input_streams=("S10_citrately_blocked",),
        output_streams=("S11_insulin_precipitate", "S12_dissolved_zinc_salt"),
        figure1_label="Insulin precipitation + Insulin zinc salt dissolving",
        description=(
            "Insulin precipitated with 1 M ZnCl2 at pH 5.9, then the zinc precipitate "
            "redissolved in water with 30 mM Tris pH 8.6 and 0.2 M EDTA."
        ),
        evidence=(p12, p13, p49),
    )
    node.operating_conditions.update({
        "zinc_chloride_stock": rep("zinc_chloride_stock", "ZnCl2 stock concentration", 1, "M", p12),
        "precipitation_ph": rep("precipitation_ph", "Precipitation pH", 5.9, "pH", p12),
        "precipitation_time": rep("precipitation_time", "Precipitation stirring time", 1, "h", p12),
        "precipitation_force": rep("precipitation_force", "Precipitation centrifugation force",
                                   18400, "xg", p12),
        "precipitation_centrifugation_time": rep("precipitation_centrifugation_time",
                                                 "Precipitation centrifugation time", 15, "min", p12),
        "precipitation_centrifugation_temperature": rep(
            "precipitation_centrifugation_temperature",
            "Precipitation centrifugation temperature", 4, "degC", p12),
        "storage_temperature": rep("storage_temperature", "Precipitate storage temperature",
                                   4, "degC", p12),
        "storage_duration": rep("storage_duration", "Maximum precipitate storage time",
                                30, "d", p12, original_text="can be stored at 4 C for up to 30 days"),
        "tris_stock_concentration": rep("tris_stock_concentration", "Tris stock concentration",
                                        1, "M", p49),
        "tris_target_concentration": rep("tris_target_concentration",
                                         "Target Tris concentration", 30, "mM", p49),
        "edta_stock_concentration": rep("edta_stock_concentration", "EDTA stock concentration",
                                        0.2, "M", p49),
        "dissolution_conductivity_limit": rep("dissolution_conductivity_limit",
                                               "Conductivity after dissolution", 3, "mS", p13),
    })
    node.condition_notes.update({
        "zinc_salt_dissolution": "precipitate suspended in water, 1 M Tris pH 8.6 to 30 mM, 0.2 M EDTA, conductivity < 3 mS",
        "ph_adjustment": "2 M HCl for pH 2.9 step; pH adjusted to 5.9 for precipitation",
    })

    # reported absolute amounts for the reference batch (sec. 4.9)
    node.measurements.update({
        "zinc_chloride_volume_reported": rep("zinc_chloride_volume_reported",
                                              "1 M ZnCl2 added", 10, "mL", p49,
                                              original_text="10 ml of 1 M zinc chloride solution was added"),
        "water_volume_reported": rep("water_volume_reported", "Water used to resuspend precipitate",
                                     285, "mL", p49,
                                     original_text="the precipitate of insulin was suspended in 285 ml of water"),
        "tris_stock_volume_reported": rep("tris_stock_volume_reported",
                                          "1 M Tris pH 8.6 added", 9.2, "mL", p49,
                                          original_text="9.2 ml of 1 M Tris pH 8.6"),
        "edta_volume_reported": rep("edta_volume_reported", "0.2 M EDTA added", 11.3, "mL", p49,
                                    original_text="11.3 ml of 0.2 M EDTA"),
    })

    node.source_expressions = (
        SourceExpression(
            expression_id="E-ZNCL2",
            label="ZnCl2 amount",
            expression_text="2 x V cm3 solution/100",
            variable_definitions={"V": "volume of the sample being precipitated, in cm3"},
            source_unit="mL of 1 M ZnCl2",
            expected_output_unit="mL",
            executable=True,
            evidence=(p12,),
        ),
        SourceExpression(
            expression_id="E-WATER",
            label="Water volume for zinc-salt dissolution",
            expression_text="total amount of protein obtained after DEAE/7",
            variable_definitions={
                "total amount of protein obtained after DEAE": "post-DEAE protein, in the paper's AU scale"
            },
            source_unit="mL of water",
            expected_output_unit="mL",
            executable=True,
            evidence=(p13,),
        ),
        SourceExpression(
            expression_id="E-EDTA",
            label="EDTA amount",
            expression_text="total amount of protein obtained after DEAE/190",
            variable_definitions={
                "total amount of protein obtained after DEAE": "post-DEAE protein, in the paper's AU scale"
            },
            source_unit="mL of 0.2 M EDTA",
            expected_output_unit="mL",
            executable=True,
            evidence=(p13,),
        ),
    )
    node.supported_equations = (
        "source_formula.zinc_chloride_from_solution_volume",
        "source_formula.water_volume_from_deae_protein",
        "source_formula.edta_from_deae_protein",
        "accounting.implied_final_volume",
        "volume.sum",
        "accounting.tris_molarity_after_dilution",
    )

    node.add_validation(
        ValidationMessage(
            severity=Severity.ERROR,
            code="source_discrepancy:water_volume_vs_formula",
            message=(
                "sec. 2.13 specifies the dissolution volume as post-DEAE protein / 7. "
                "With the reported post-DEAE protein of 2142.5 AU this evaluates to "
                "306.07 mL, but sec. 4.9 reports 285 mL of water (7.4% lower). The "
                "same paper's 9.2 mL of 1 M Tris to reach 30 mM implies a total volume "
                "of about 306.7 mL, which is consistent with the formula and not with "
                "285 mL. Both statements are retained; neither is adjusted."
            ),
            where="N10",
            evidence=(p13, p49),
        )
    )
    graph.add_node(node)
    return node


def _node_q_sepharose(graph: ProcessGraph) -> ProcessNode:
    sec = "2.14 Low-pressure chromatography on Q Sepharose"
    node = ProcessNode(
        node_id="N11", index=11, name="Q Sepharose purification",
        operation=OperationKind.CHROMATOGRAPHY,
        input_streams=("S12_dissolved_zinc_salt",), output_streams=("S13_q_fraction",),
        figure1_label="Q Sepharose chromatography",
        description="Cation-exchange low-pressure chromatography; insulin eluted with QE buffers.",
        evidence=(ev(3, section=sec), ev(4, section="4.10"), ev(5, figure="Fig. 5")),
    )
    _deae_common(node, sec, 3)
    node.operating_conditions.update({
        "wash_qw_conductivity": rep("wash_qw_conductivity", "QW conductivity", 0.5, "mS", ev(3, section=sec)),
        "wash_qw_isopropanol": rep("wash_qw_isopropanol", "QW isopropanol", 20, "%", ev(3, section=sec)),
        "elution_qe1_conductivity": rep("elution_qe1_conductivity", "QE I conductivity", 0.42, "mS", ev(3, section=sec)),
        "elution_qe1_isopropanol": rep("elution_qe1_isopropanol", "QE I isopropanol", 30, "%", ev(3, section=sec)),
        "elution_qe2_conductivity": rep("elution_qe2_conductivity", "QE II conductivity", 3, "mS", ev(3, section=sec)),
        "elution_qe2_isopropanol": rep("elution_qe2_isopropanol", "QE II isopropanol", 30, "%", ev(3, section=sec)),
        "flow_rate": rep("flow_rate", "Column flow rate", 10, "mL/min", ev(5, figure="Fig. 5")),
    })
    node.condition_notes.update({
        "resin": "Q Sepharose Fast Flow (GE Healthcare)",
        "wash_qw": "20 mM Tris pH 8.6 + 20% isopropanol, 2 CV",
        "elution_qe1": "20 mM Tris pH 8.6 + 30% isopropanol, 2 CV (weakly bound proteins)",
        "elution_qe2": "20 mM Tris pH 8.6 + 30% isopropanol, 2 CV (protein of interest)",
        "strip": "1 CV of 1 M NaCl then 0.5 M NaOH",
        "insulin_peak": "approximately 1400-1800 mL (Fig. 5)",
        "detection": "A280",
    })
    graph.add_node(node)

    s = graph.stream("S13_q_fraction")
    s.put(rep("fraction_volume", "Insulin fraction volume", 226, "mL",
              ev(4, section="4.10"),
              original_text="226 ml of the insulin fraction was obtained"))
    s.put(rep("protein_concentration", "Protein concentration", 2.77, "AU/mL",
              ev(4, section="4.10"),
              original_text="The protein concentration was 2.77 AU/ml"))
    return node


def _node_cpb(graph: ProcessGraph) -> ProcessNode:
    p = ev(3, section="2.15 Reaction with carboxypeptidase B")
    node = ProcessNode(
        node_id="N12", index=12, name="Carboxypeptidase B treatment",
        operation=OperationKind.PROTEOLYSIS,
        input_streams=("S13_q_fraction",), output_streams=("S14_cpb_treated",),
        figure1_label="Carboxypeptidase B reaction",
        description="Hydrolysis of the residual Lys-Arg linker to release native insulin.",
        evidence=(p, ev(4, section="4.11")),
    )
    node.operating_conditions.update({
        "dilution_factor": rep("dilution_factor", "Dilution with water", 2, "fold", p),
        "reaction_ph": rep("reaction_ph", "Reaction pH", 8.8, "pH", p),
        "reaction_time": rng("reaction_time", "Reaction time", 16, 18, "h", p),
    })
    node.measurements.update({
        "cpb_volume_reported": rep("cpb_volume_reported", "2.5 mg/mL carboxypeptidase B added",
                                   50, "uL", p,
                                   original_text="50 ul of carboxypeptidase B (2.5 mg/ml) was added"),
        "cpb_stock_concentration": rep("cpb_stock_concentration",
                                       "Carboxypeptidase B stock concentration",
                                       2.5, "mg/mL", p),
    })
    node.condition_notes.update({
        "chemistry": "carboxypeptidase B hydrolyses the Lys-Arg linker joining chains B and A",
        "dosing_rule": "10 ul for every 150 AU of total protein determined in the main fraction",
        "reaction_temperature": ("room temperature; no numeric set point is stated, so "
                                 "none is recorded as a quantity"),
    })
    node.source_expressions = (
        SourceExpression(
            expression_id="E-CPB",
            label="Carboxypeptidase B amount",
            expression_text="10 ul for every 150 AU of total protein",
            variable_definitions={
                "total protein": "total protein in the main fraction, in AU",
            },
            source_unit="uL of 2.5 mg/ml CPB",
            expected_output_unit="uL",
            executable=True,
            evidence=(p,),
        ),
    )
    node.supported_equations = ("source_formula.cpb_from_au",)
    node.add_validation(
        ValidationMessage(
            severity=Severity.ERROR,
            code="source_discrepancy:cpb_dose_vs_au",
            message=(
                "sec. 2.15 states 10 ul of carboxypeptidase B per 150 AU of main-fraction "
                "protein, and sec. 4.10 reports that fraction as 226 ml at 2.77 AU/ml "
                "(626.02 AU). That dosing rule implies 41.73 ul, but the paper states "
                "50 ul was added (20% more). The paper does not say whether the dose "
                "was rounded up or based on a different batch."
            ),
            where="N12",
            evidence=(p, ev(4, section="4.10")),
        )
    )
    graph.add_node(node)
    return node


def _node_rp_hplc(graph: ProcessGraph) -> ProcessNode:
    p = ev(3, section="2.16 RP-HPLC chromatography")
    node = ProcessNode(
        node_id="N13", index=13, name="RP-HPLC purification",
        operation=OperationKind.CHROMATOGRAPHY,
        input_streams=("S14_cpb_treated",), output_streams=("S15_rp_hplc_fraction",),
        figure1_label="HPLC chromatography",
        description="Preparative reversed-phase HPLC on an ACE 5C18-300 column.",
        evidence=(p, ev(4, section="4.11"), ev(5, section="4.11"), ev(6, figure="Fig. 6")),
    )
    node.operating_conditions.update({
        "mobile_phase_a_na2so4": rep("mobile_phase_a_na2so4", "Mobile phase A sodium sulphate",
                                     0.2, "M", p),
        "mobile_phase_a_na2so4_volume": rep("mobile_phase_a_na2so4_volume",
                                            "Mobile phase A aqueous volume", 2000, "mL", p),
        "mobile_phase_a_acetonitrile": rep("mobile_phase_a_acetonitrile",
                                           "Mobile phase A acetonitrile", 440, "mL", p),
        "mobile_phase_b_na2so4_volume": rep("mobile_phase_b_na2so4_volume",
                                            "Mobile phase B aqueous volume", 1250, "mL", p),
        "mobile_phase_b_acetonitrile": rep("mobile_phase_b_acetonitrile",
                                           "Mobile phase B acetonitrile", 1250, "mL", p),
        "mobile_phase_ph": rep("mobile_phase_ph", "Mobile phase pH", 2.3, "pH", p),
        "post_column_dilution": rep("post_column_dilution", "Post-column dilution with water",
                                    3, "fold", p, original_text="diluted 3 times with H2O"),
    })
    node.condition_notes.update({
        "column": "ACE 5C18-300 (ACE Ltd)",
        "mode": "isocratic (Fig. 6 caption)",
        "detector_wavelength": "214 nm (Fig. 6 caption)",
        "insulin_peak": "approximately 90-105 min (Fig. 6)",
        "preheating": "aqueous phases preheated in warm water to 25-30 C",
        "downstream": "insulin re-precipitated with zinc chloride after dilution",
    })
    graph.add_node(node)

    s = graph.stream("S15_rp_hplc_fraction")
    s.put(rep("fraction_volume", "Insulin fraction volume", 97, "mL",
              ev(5, section="4.11"),
              original_text="97 ml of the insulin fraction was obtained"))
    s.put(rep("protein_concentration", "Protein concentration", 2.42, "AU/mL",
              ev(5, section="4.11"),
              original_text="The protein concentration was 2.42 AU/ml"))
    return node


def _node_g25(graph: ProcessGraph) -> ProcessNode:
    p = ev(3, section="2.17 Sephadex G-25 chromatography")
    node = ProcessNode(
        node_id="N14", index=14, name="Sephadex G-25 buffer exchange",
        operation=OperationKind.CHROMATOGRAPHY,
        input_streams=("S15_rp_hplc_fraction",), output_streams=("S16_g25_fraction",),
        figure1_label="Sephadex G-25 chromatography",
        description="Desalting and buffer exchange to remove residual acetonitrile.",
        evidence=(p, ev(5, section="4.12")),
    )
    node.operating_conditions.update({
        "equilibration_ph": rep("equilibration_ph", "Suspension pH before loading", 3.0, "pH", p),
        "elution_buffer_concentration": rep("elution_buffer_concentration",
                                            "Ammonium acetate concentration", 5, "mM", p),
        "elution_buffer_ph": rep("elution_buffer_ph", "Ammonium acetate pH", 4.0, "pH", p),
    })
    node.condition_notes.update({
        "resin": "Sephadex G-25 (GE Healthcare)",
        "purpose": "exchange the sample buffer and remove residual acetonitrile (sec. 4.12)",
        "note": ("This operation is reported in the full methods and results but is not "
                 "part of the 'three-step purification' summary at sec. 4.13; it is "
                 "retained here as reported."),
    })
    graph.add_node(node)

    s = graph.stream("S16_g25_fraction")
    s.put(rep("fraction_volume", "Insulin fraction volume", 31, "mL",
              ev(5, section="4.12"),
              original_text="31 ml of the insulin fraction was obtained"))
    s.put(rep("protein_concentration", "Protein concentration", 3.59, "AU/mL",
              ev(5, section="4.12"),
              original_text="The protein concentration was 3.59 AU/ml"))
    return node


def _node_characterization(graph: ProcessGraph) -> ProcessNode:
    p31 = ev(3, section="3.1 UHPLC chromatography")
    p413 = ev(6, section="4.13 Purification summary")
    f7 = ev(6, figure="Fig. 7")
    f8 = ev(6, figure="Fig. 8")
    node = ProcessNode(
        node_id="N15", index=15, name="Final product characterization",
        operation=OperationKind.CHARACTERIZATION,
        input_streams=("S16_g25_fraction",), output_streams=("S17_final_product",),
        figure1_label=None,
        description=(
            "UHPLC and ESI-MS characterization of the purified product. This node has "
            "no counterpart in the Fig. 1 block diagram; it collects the analytical "
            "endpoints reported in secs. 3, 4.13 and Figs. 7-8."
        ),
        evidence=(p31, p413, f7, f8, ev(7, section="5 Conclusions")),
    )
    node.operating_conditions.update({
        "uhplc_temperature": rep("uhplc_temperature", "UHPLC column temperature", 23, "degC", p31),
        "uhplc_flow_rate": rep("uhplc_flow_rate", "UHPLC flow rate", 0.713, "mL/min", p31),
        "uhplc_detection_wavelength": rep("uhplc_detection_wavelength",
                                          "UHPLC detection wavelength", 220, "nm", p31),
        "uhplc_injection_volume": rep("uhplc_injection_volume", "UHPLC injection volume",
                                      2, "uL", p31),
        "uhplc_na2h2po4": rep("uhplc_na2h2po4", "NaH2PO4 in eluents", 9.66, "g", p31),
        "uhplc_naclO4": rep("uhplc_naclO4", "NaClO4 in eluent A1", 24.58, "g", p31),
        "uhplc_eluent_volume": rep("uhplc_eluent_volume", "Eluent aqueous volume", 1000, "mL", p31),
        "uhplc_eluent_ph": rep("uhplc_eluent_ph", "Eluent pH", 2.5, "pH", p31),
    })
    node.condition_notes.update({
        "uhplc_system": "Waters Acquity UHPLC with Empower 3",
        "uhplc_column": "ACQUITY UPLC CSH C18, 1.7 um, 2.1 x 50 mm",
        "eluent_a1": "9.66 g NaH2PO4.H2O and 24.58 g NaClO4.H2O in 1000 ml water, pH 2.5",
        "eluent_b1": "9.66 g NaH2PO4.H2O in 1000 ml water pH 2.5 mixed with acetonitrile 1:1 (v/v)",
        "ms": "4800 MALDI TOF/TOF analyzer, positive ion reflector mode, CHCA matrix",
        "reported_purification_summary": "three-step purification: DEAE/Q Sepharose and RP-HPLC (sec. 4.13)",
    })

    node.measurements.update({
        "activity": rep("activity", "Average activity per litre of culture medium",
                        2700, "IU/L", p413,
                        original_text="on the average 2700 IU of up to 99% purity recombinant human insulin from 1L of the culture media"),
        "purity": rep("purity", "Protein purity of purified product", 99, "%", f7,
                      original_text="Protein purity is about 99%",
                      notes=("Reported as 'about 99%' / 'up to 99%' and expressed as an "
                             "approximation, not a precise assay value.")),
        "retention_time": rep("retention_time", "UHPLC retention time of insulin",
                              3.748, "min", f7,
                              original_text="RT value of insulin is 3.748 min"),
        "measured_molecular_mass": rep("measured_molecular_mass",
                                       "Measured molecular mass (ESI-MS)",
                                       5807.5, "Da", p413,
                                       original_text="The molecular weight obtained for insulin by the ESI-MS method was 5807.5 Da",
                                       uncertainty=Uncertainty(
                                           kind="significant_figures",
                                           lo=5807.45, hi=5807.55,
                                           basis=("value is printed to one decimal place, so the "
                                                  "stated precision is +/-0.05 Da; this is a "
                                                  "reporting-precision interval, not an assay "
                                                  "uncertainty, because the paper gives no "
                                                  "replicates, standard or error bars"),
                                       )),
        "theoretical_molecular_mass": rep("theoretical_molecular_mass",
                                          "Theoretical calculated average mass",
                                          5807.63, "Da", p413,
                                          original_text="Theoretical calculated average mass is 5807.63 Da",
                                          uncertainty=Uncertainty(
                                              kind="significant_figures",
                                              lo=5807.625, hi=5807.635,
                                              basis=("printed to two decimal places, so the stated "
                                                     "precision is +/-0.005 Da"),
                                          )),
    })
    node.supported_equations = (
        "characterization.mass_deviation",
        "characterization.relative_mass_deviation_ppm",
        "accounting.total_activity_from_per_volume",
    )
    node.missing_parameters = (
        MissingParameter(parameter_id=MP_AU_CALIBRATION.parameter_id,
                         description=MP_AU_CALIBRATION.description,
                         reason=MP_AU_CALIBRATION.reason,
                         blocks=MP_AU_CALIBRATION.blocks,
                         evidence=MP_AU_CALIBRATION.evidence),
    )
    node.operating_conditions["insulin_mass_from_au"] = unk(
        "insulin_mass_from_au", "Insulin mass derived from the final AU measurement", "g",
        MP_AU_CALIBRATION)
    node.operating_conditions["final_activity_from_au"] = unk(
        "final_activity_from_au", "Activity derived from the final AU measurement", "IU",
        MP_AU_CALIBRATION)
    node.operating_conditions["au_to_protein_mass_factor"] = unk(
        "au_to_protein_mass_factor", "AU to protein mass conversion factor", "g/AU",
        MP_AU_CALIBRATION)

    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="scope:no_significance_claim_for_mass_deviation",
            message=(
                "The signed deviation 5807.5 - 5807.63 = -0.13 Da is reported as an "
                "arithmetic difference only. The measured value is printed to +/-0.05 "
                "Da and the theoretical value to +/-0.005 Da, giving a reporting-precision "
                "interval of about +/-0.055 Da. The paper reports no replicates, no "
                "standard and no error bars, so this is NOT a statistical test and no "
                "claim of significance, agreement or disagreement is made."
            ),
            where="N15",
            evidence=(p413, f8),
        )
    )
    node.add_validation(
        ValidationMessage(
            severity=Severity.WARNING,
            code="scope:activity_is_retrospective_average",
            message=(
                "2700 IU/L is reported at the end of the whole process as a "
                "retrospective average per litre of culture medium. It is not a "
                "stage measurement and no equation links it to any AU value, so it "
                "cannot be reproduced by this model."
            ),
            where="N15",
            evidence=(p413,),
        )
    )
    graph.add_node(node)
    return node


# --------------------------------------------------------------------------- #
# graph assembly
# --------------------------------------------------------------------------- #


AU_CAVEAT = (
    "Absorbance units at 280 nm from a water-blanked spectrophotometer (sec. 2.18). "
    "With no path length and no extinction coefficient the scale is instrument-relative: "
    "AU is NOT grams, molarity, IU or pure-insulin mass, and must not be converted as if it were."
)


def _apply_au_caveat(graph: ProcessGraph) -> None:
    """Attach the AU caveat to every absorbance quantity in the graph.

    Doing this once here guarantees no AU value can enter the model without the
    warning that makes its interpretation unambiguous.
    """
    for _location, _qid, q in graph.iter_quantities():
        if q.unit in ("AU", "AU/mL") and AU_CAVEAT not in q.notes:
            q.notes = f"{q.notes} {AU_CAVEAT}".strip()


def build_graph() -> ProcessGraph:
    graph = ProcessGraph(
        graph_id=GRAPH_ID,
        title="Recombinant human insulin from Escherichia coli 20 (Zielinski et al. 2019)",
        source_id="zielinski2019",
        assumptions=(A_DILUTION_TWO_TIMES, A_LINEAR_INTERPOLATION),
    )
    graph.description = CITATION
    graph.doi = DOI
    _build_streams(graph)
    _build_nodes(graph)
    _apply_au_caveat(graph)
    return graph


# --------------------------------------------------------------------------- #
# equation wiring
# --------------------------------------------------------------------------- #


def build_bindings() -> list[EquationBinding]:
    """Wire registered equations to concrete quantities in the graph."""

    def ref(location: str, qid: str) -> Ref:
        return Ref(location=location, quantity_id=qid)

    n1, n3, n5 = node_loc("N01"), node_loc("N03"), node_loc("N05")
    n7, n9 = node_loc("N07"), node_loc("N09")
    n10, n12, n15 = node_loc("N10"), node_loc("N12"), node_loc("N15")

    s3 = stream_loc("S03_wet_biomass")
    s4 = stream_loc("S04_inclusion_bodies")
    s5, s6 = stream_loc("S05_denatured_solution"), stream_loc("S06_renatured_precursor")
    s9, s10 = stream_loc("S09_deae_fraction"), stream_loc("S10_citrately_blocked")
    s13, s15 = stream_loc("S13_q_fraction"), stream_loc("S15_rp_hplc_fraction")
    s16 = stream_loc("S16_g25_fraction")

    return [
        # --- N02: wet biomass concentration -----------------------------
        EquationBinding(
            binding_id="B01", node_id="N02",
            equation_id="accounting.mass_per_volume",
            inputs={"total_mass": ref(s3, "wet_biomass_total"),
                    "volume": ref(n1, "starting_medium_volume")},
            output_quantity_id="wet_biomass_g_per_L", output_location=node_loc("N02"),
        ),
        # --- N03: inclusion-body concentration and IB fraction ----------
        EquationBinding(
            binding_id="B02", node_id="N03",
            equation_id="accounting.mass_per_volume",
            inputs={"total_mass": ref(s4, "inclusion_bodies_total"),
                    "volume": ref(n1, "starting_medium_volume")},
            output_quantity_id="inclusion_bodies_g_per_L", output_location=n3,
        ),
        EquationBinding(
            binding_id="B03", node_id="N03",
            equation_id="accounting.mass_fraction",
            inputs={"part_mass": ref(s4, "inclusion_bodies_total"),
                    "total_mass": ref(s3, "wet_biomass_total")},
            output_quantity_id="inclusion_body_fraction_of_biomass",
            output_location=n3,
            notes="Descriptive ratio of two reported totals; not a model parameter.",
        ),
        # --- N05: AU-based refolding yield --------------------------------
        EquationBinding(
            binding_id="B04", node_id="N05",
            equation_id="accounting.percent_yield_from_au",
            inputs={"before_au": ref(s5, "dissolved_protein"),
                    "after_au": ref(s6, "protein_after_refolding")},
            output_quantity_id="implied_refolding_yield_pct", output_location=n5,
            notes="Absorbance-based ratio, not a mass yield.",
        ),
        # --- N07: aprotinin dose ------------------------------------------
        EquationBinding(
            binding_id="B05", node_id="N07",
            equation_id="source_formula.aprotinin_from_trypsin_volume",
            inputs={"trypsin_volume_ul": ref(n7, "trypsin_volume")},
            output_quantity_id="aprotinin_volume", output_location=n7,
        ),
        # --- N08: total AU after DEAE --------------------------------------
        EquationBinding(
            binding_id="B06", node_id="N08",
            equation_id="absorbance.total_from_volume_and_concentration",
            inputs={"volume_ml": ref(s9, "fraction_volume"),
                    "concentration_au_per_ml": ref(s9, "protein_concentration")},
            output_quantity_id="total_au", output_location=s9,
        ),
        # --- N09: decitraconylation dilution ------------------------------
        EquationBinding(
            binding_id="B07", node_id="N09",
            equation_id="volume.diluted",
            inputs={"volume": ref(s9, "fraction_volume"),
                    "factor": ref(n9, "dilution_factor")},
            output_quantity_id="diluted_volume", output_location=s10,
        ),
        # --- N10: zinc precipitation and salt dissolution -------------------
        EquationBinding(
            binding_id="B08", node_id="N10",
            equation_id="source_formula.zinc_chloride_from_solution_volume",
            inputs={"volume_ml": ref(s10, "diluted_volume")},
            output_quantity_id="zinc_chloride_volume", output_location=n10,
        ),
        EquationBinding(
            binding_id="B09", node_id="N10",
            equation_id="source_formula.water_volume_from_deae_protein",
            inputs={"deae_total_au": ref(s9, "total_au")},
            output_quantity_id="water_volume_from_formula", output_location=n10,
        ),
        EquationBinding(
            binding_id="B10", node_id="N10",
            equation_id="source_formula.edta_from_deae_protein",
            inputs={"deae_total_au": ref(s9, "total_au")},
            output_quantity_id="edta_volume_from_formula", output_location=n10,
        ),
        EquationBinding(
            binding_id="B11", node_id="N10",
            equation_id="accounting.implied_final_volume",
            inputs={"stock_concentration": ref(n10, "tris_stock_concentration"),
                    "stock_volume": ref(n10, "tris_stock_volume_reported"),
                    "target_concentration": ref(n10, "tris_target_concentration")},
            output_quantity_id="implied_final_volume_from_tris", output_location=n10,
        ),
        EquationBinding(
            binding_id="B12", node_id="N10",
            equation_id="volume.sum",
            inputs={"a": ref(n10, "water_volume_reported"),
                    "b": ref(n10, "tris_stock_volume_reported")},
            output_quantity_id="final_volume_reported_path", output_location=n10,
        ),
        EquationBinding(
            binding_id="B13", node_id="N10",
            equation_id="accounting.tris_molarity_after_dilution",
            inputs={"stock_volume_ml": ref(n10, "tris_stock_volume_reported"),
                    "stock_concentration": ref(n10, "tris_stock_concentration"),
                    "final_volume": ref(n10, "final_volume_reported_path")},
            output_quantity_id="tris_concentration_from_reported_volume",
            output_location=n10,
        ),
        # --- N11 / N13 / N14: stage AU totals ------------------------------
        EquationBinding(
            binding_id="B14", node_id="N11",
            equation_id="absorbance.total_from_volume_and_concentration",
            inputs={"volume_ml": ref(s13, "fraction_volume"),
                    "concentration_au_per_ml": ref(s13, "protein_concentration")},
            output_quantity_id="total_au", output_location=s13,
        ),
        # --- N12: carboxypeptidase B dose -----------------------------------
        EquationBinding(
            binding_id="B15", node_id="N12",
            equation_id="source_formula.cpb_from_au",
            inputs={"main_fraction_au": ref(s13, "total_au")},
            output_quantity_id="cpb_volume_from_formula", output_location=n12,
        ),
        EquationBinding(
            binding_id="B16", node_id="N13",
            equation_id="absorbance.total_from_volume_and_concentration",
            inputs={"volume_ml": ref(s15, "fraction_volume"),
                    "concentration_au_per_ml": ref(s15, "protein_concentration")},
            output_quantity_id="total_au", output_location=s15,
        ),
        EquationBinding(
            binding_id="B17", node_id="N14",
            equation_id="absorbance.total_from_volume_and_concentration",
            inputs={"volume_ml": ref(s16, "fraction_volume"),
                    "concentration_au_per_ml": ref(s16, "protein_concentration")},
            output_quantity_id="total_au", output_location=s16,
        ),
        # --- N15: mass accuracy and batch activity --------------------------
        EquationBinding(
            binding_id="B18", node_id="N15",
            equation_id="characterization.mass_deviation",
            inputs={"measured_da": ref(n15, "measured_molecular_mass"),
                    "theoretical_da": ref(n15, "theoretical_molecular_mass")},
            output_quantity_id="mass_deviation", output_location=n15,
        ),
        EquationBinding(
            binding_id="B19", node_id="N15",
            equation_id="characterization.relative_mass_deviation_ppm",
            inputs={"measured_da": ref(n15, "measured_molecular_mass"),
                    "theoretical_da": ref(n15, "theoretical_molecular_mass")},
            output_quantity_id="mass_deviation_ppm", output_location=n15,
        ),
        EquationBinding(
            binding_id="B20", node_id="N15",
            equation_id="accounting.total_activity_from_per_volume",
            inputs={"activity_per_volume": ref(n15, "activity"),
                    "volume": ref(n1, "starting_medium_volume")},
            output_quantity_id="batch_activity", output_location=n15,
            notes="Per-litre reported average x reported culture volume; not a validated scale-up prediction.",
        ),
    ]


def build_cross_checks() -> list[CrossCheck]:
    """Declared comparisons of computed values against values the paper states."""
    p42 = ev(4, section="4.2 Cell culture")
    p43 = ev(4, section="4.3 Isolation of inclusion bodies")
    p49 = ev(4, section="4.9 Precipitation of insulin and dissolving the zinc salt")
    p415 = ev(3, section="2.15 Reaction with carboxypeptidase B")
    p410 = ev(4, section="4.10 Low-pressure chromatography on Q Sepharose")

    return [
        CrossCheck(
            check_id="CC01", node_id="N02",
            description="wet biomass per litre: computed 224 g / 4 L vs the paper's own 56 g/L",
            computed=Ref(node_loc("N02"), "wet_biomass_g_per_L"),
            reported=Ref(node_loc("N01"), "wet_biomass_g_per_L_reported"),
            tolerance_rel=0.01, evidence=(p42,),
        ),
        CrossCheck(
            check_id="CC02", node_id="N03",
            description="inclusion bodies per litre: computed 58 g / 4 L vs the paper's own 14.5 g/L",
            computed=Ref(node_loc("N03"), "inclusion_bodies_g_per_L"),
            reported=Ref(node_loc("N03"), "inclusion_bodies_g_per_L_reported"),
            tolerance_rel=0.01, evidence=(p43,),
        ),
        CrossCheck(
            check_id="CC03", node_id="N10",
            description="ZnCl2 dose: formula 2 x V/100 on 500 mL vs the reported 10 mL",
            computed=Ref(node_loc("N10"), "zinc_chloride_volume"),
            reported=Ref(node_loc("N10"), "zinc_chloride_volume_reported"),
            tolerance_rel=0.01, evidence=(p49,),
        ),
        CrossCheck(
            check_id="CC04", node_id="N10",
            description="EDTA dose: formula 2142.5 AU / 190 vs the reported 11.3 mL",
            computed=Ref(node_loc("N10"), "edta_volume_from_formula"),
            reported=Ref(node_loc("N10"), "edta_volume_reported"),
            tolerance_rel=0.02, evidence=(p49,),
        ),
        CrossCheck(
            check_id="CC05", node_id="N10",
            description=(
                "zinc-salt dissolution water: formula 2142.5 AU / 7 vs the reported 285 mL"
            ),
            computed=Ref(node_loc("N10"), "water_volume_from_formula"),
            reported=Ref(node_loc("N10"), "water_volume_reported"),
            tolerance_rel=0.02, evidence=(p49,), on_failure="error",
        ),
        CrossCheck(
            check_id="CC06", node_id="N10",
            description=(
                "total volume implied by 9.2 mL of 1 M Tris to reach 30 mM vs the "
                "volume implied by the paper's own /7 formula"
            ),
            computed=Ref(node_loc("N10"), "implied_final_volume_from_tris"),
            reported=Ref(node_loc("N10"), "water_volume_from_formula"),
            tolerance_rel=0.02, evidence=(p49,),
        ),
        CrossCheck(
            check_id="CC07", node_id="N10",
            description=(
                "Tris concentration actually achieved on the reported 285 + 9.2 mL "
                "path vs the stated 30 mM target"
            ),
            computed=Ref(node_loc("N10"), "tris_concentration_from_reported_volume"),
            reported=Ref(node_loc("N10"), "tris_target_concentration"),
            tolerance_rel=0.03, evidence=(p49,), on_failure="warning",
        ),
        CrossCheck(
            check_id="CC08", node_id="N12",
            description="carboxypeptidase B dose: 626.02 AU x 10/150 vs the reported 50 uL",
            computed=Ref(node_loc("N12"), "cpb_volume_from_formula"),
            reported=Ref(node_loc("N12"), "cpb_volume_reported"),
            tolerance_rel=0.02, evidence=(p415, p410), on_failure="error",
        ),
    ]


def build_capabilities() -> dict[str, tuple[str, ...]]:
    """Map a target quantity to the models that would be needed to produce it."""
    return {
        "node:N01:od600_from_inputs": ("kinetics.growth_ode", "kinetics.monod_substrate", "transfer.oxygen_kla"),
        "node:N01:wet_biomass_from_inputs": ("kinetics.growth_ode", "kinetics.monod_substrate", "transfer.oxygen_kla"),
        "node:N01:specific_growth_rate": ("kinetics.growth_ode", "transfer.oxygen_kla"),
        "node:N01:dissolved_oxygen": ("transfer.oxygen_kla",),
        "node:N05:refolding_yield_predictive": ("folding.renaturation_kinetics",),
        "node:N05:refolding_time_predictive": ("folding.renaturation_kinetics",),
        "node:N15:au_to_protein_mass_factor": ("calibration.au_to_mass",),
        "node:N15:insulin_mass_from_au": ("calibration.au_to_mass", "recovery.stage_yield"),
        "node:N15:final_activity_from_au": ("activity.iu_from_au",),
        "stream:S16_g25_fraction:insulin_mass": ("calibration.au_to_mass",),
        "stream:S16_g25_fraction:stage_recovery_percent": ("recovery.stage_yield", "calibration.au_to_mass"),
        "node:N03:inclusion_body_recovery_percent": ("recovery.stage_yield", "calibration.au_to_mass"),
        # industrial / scale-up projections
        "node:N01:scaled_up_od600": ("scaleup.effect_of_scale", "kinetics.growth_ode", "transfer.oxygen_kla"),
        "node:N01:scaled_up_wet_biomass": ("scaleup.effect_of_scale", "kinetics.growth_ode"),
        "node:N01:industrial_insulin_yield": ("scaleup.effect_of_scale", "calibration.au_to_mass"),
        "node:N15:industrial_scale_activity": ("scaleup.effect_of_scale", "activity.iu_from_au"),
        "graph:industrial_scale_process": ("scaleup.effect_of_scale",),
    }


def build_keyword_models() -> dict[str, tuple[str, ...]]:
    """Substring -> missing models, for predictive targets not named explicitly.

    Scale-up is the important case: a reviewer asking for an industrial-scale
    result names an arbitrary target, and the answer must still identify the
    absence of scale-up correlation rather than failing generically.
    """
    return {
        "scale": ("scaleup.effect_of_scale",),
        "industrial": ("scaleup.effect_of_scale",),
        "extrapolat": ("scaleup.effect_of_scale",),
        "od600": ("kinetics.growth_ode", "transfer.oxygen_kla"),
        "dissolved_oxygen": ("transfer.oxygen_kla",),
        "kinetic": ("kinetics.growth_ode", "folding.renaturation_kinetics"),
        "fold": ("folding.renaturation_kinetics",),
        "renaturation": ("folding.renaturation_kinetics",),
        "insulin_mass": ("calibration.au_to_mass",),
        "au_to_mass": ("calibration.au_to_mass",),
        "activity": ("activity.iu_from_au",),
        "iu": ("activity.iu_from_au",),
        "recovery": ("recovery.stage_yield", "calibration.au_to_mass"),
        "yield": ("recovery.stage_yield",),
    }


def build_engine() -> ExecutionEngine:
    graph = build_graph()
    return ExecutionEngine(
        graph,
        bindings=build_bindings(),
        cross_checks=build_cross_checks(),
        predictive_capabilities=build_capabilities(),
        keyword_models=build_keyword_models(),
    )


def replay(engine: ExecutionEngine | None = None):
    """Run evidence replay and return the ordered node results."""
    eng = engine or build_engine()
    return eng.run(mode=ExecutionMode.EVIDENCE_REPLAY)


def predict(target: str, engine: ExecutionEngine | None = None) -> Resolution:
    """Attempt a predictive result for `target`; fails closed when unsupported."""
    eng = engine or build_engine()
    return eng.request(target, mode=ExecutionMode.PREDICTIVE)