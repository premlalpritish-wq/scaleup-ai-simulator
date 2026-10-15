"""The curated candidate-evidence catalogue for the Zielinski 2019 model.

Every record here was extracted from a publication that was actually retrieved
during development, and each carries the passage it was taken from. Nothing is
inferred from a title or an abstract summary alone: ``quote`` holds the text the
extraction was based on.

Each finding's conditions are transcribed in **that paper's own wording**, each
bound to a passage from that paper. The target process is transcribed the same
way from the Zielinski publication. Agreement between the two is therefore a
claim about two independently checkable passages, not an artefact of writing the
same string on both sides.

Correction to an earlier version of this file. CF-003 was previously recorded as
a *found* external source: a 2017 paper from the same institute, on the same
strain, vector and medium. That verdict was circular -- the candidate's
condition strings had been written identical to the target's, and the supporting
passage turns out to occur verbatim in the Zielinski 2019 text itself. The 2019
methods section and the 2017 methods section describe the same run in
near-identical wording. CF-003 is therefore the target publication's own content
reached through a second paper. It is retained, but it is flagged as
non-independent by :mod:`composition.evidence.sourcing` and can no longer be
recorded as found.

The three findings now demonstrate three outcomes:

* **incompatible, independent** -- a published kinetic constant measured under
  conditions that do not match the target process (CF-001, CF-002);
* **not independent** -- a source whose passages are the target's own (CF-003);
* **no candidates at all** -- quantities for which nothing was found, recorded
  as an empty result with a stated search scope.

Nothing here modifies or is imported by ``Models/Zielinski``. The model keeps
reporting its unknowns as unknown.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .candidate import (
    CandidateFinding,
    ExtractionConfidence,
    Independence,
    Provenance,
    SourceLocation,
    UncertaintyRecord,
    Verdict,
    catalogue_payload,
)
from .conflicts import Conflict, RecordExamined, detect
from .sourcing import Condition

#: The registered model this catalogue assesses evidence against.
REGISTERED_MODEL_ID = "zielinski2019.rhi_process"

#: The exact artefact every verdict below was made against.
#:
#: Identity, citation and DOI are read from the *registry*, not written here, so
#: they cannot drift from the model that actually exists. Two corrections
#: follow from that, both recorded because they were real errors: an earlier
#: version of this file named a model_id ("zielinski2019.recombinant-insulin")
#: that was never registered, and carried a DOI of 10.1016/j.jbiotec.2019.03.011
#: that no artefact declares. The registry reads the DOI the model itself
#: states, 10.1016/j.pep.2019.02.002.
#:
#: The graph digest is the one the run actually reported, read from the result
#: document rather than remembered; a test asserts they match.
def _build_record() -> RecordExamined:
    from ..registry import audit_references, build_registry

    models, _ = build_registry()
    resolved = audit_references(REGISTERED_MODEL_ID, models)
    model = models.get(REGISTERED_MODEL_ID)
    return RecordExamined(
        model_id=REGISTERED_MODEL_ID,
        model_reference=resolved.value or "",
        registry_resolution=("resolved" if resolved.is_known else "unresolved"),
        registry_detail=resolved.basis,
        model_version=model.model_version if model else "",
        model_source=(model.source_paper.value if model else "") or "",
        model_doi=(model.doi.value if model else "") or "",
        run_id="zielinski-replay",
        graph_reproducibility_digest=(
            "2f5a2820c622b74d2ad46fcf9b6f90a5632d249dec9ec27b7523a3a588ce5fad"
        ),
        missing_parameters_examined=(
            "MP-GROWTH-KINETICS",
            "MP-OXYGEN-TRANSFER",
            "MP-INDUCTION-TIME",
        ),
    )


ZIELINSKI_RECORD: RecordExamined = _build_record()

# --------------------------------------------------------------------------- #
# What is missing, in the model's own words
# --------------------------------------------------------------------------- #

TARGETS: dict[str, dict[str, Any]] = {
    "node:N01#specific_growth_rate": {
        "label": "Growth rate of the culture",
        "missing_parameter": "MP-GROWTH-KINETICS",
        "why_it_matters": (
            "Without a specific growth rate the model cannot predict biomass from "
            "the feed, cannot integrate growth over time, and cannot say how much "
            "substrate the batch consumed."
        ),
        "blocks": ["od600_from_inputs", "wet_biomass_from_inputs", "glucose_consumed"],
    },
    "node:N01#stationary_phase_od600": {
        "label": "Density at which the culture stopped growing",
        "missing_parameter": "",
        "why_it_matters": (
            "The published paper gives this as a range. The model refuses to "
            "collapse a range into a single number, so it stays unknown."
        ),
        "blocks": [],
    },
    "node:N01#glucose_limitation_od600": {
        "label": "Density at which glucose feeding was curtailed",
        "missing_parameter": "",
        "why_it_matters": (
            "Marks the transition from carbon-limited to pH-stat fed operation. "
            "Published as a range, so the model keeps it as a range."
        ),
        "blocks": [],
    },
    "node:N01#dissolved_oxygen": {
        "label": "Dissolved oxygen during the batch",
        "missing_parameter": "MP-OXYGEN_TRANSFER",
        "why_it_matters": (
            "Without it there is no way to know whether growth was oxygen limited, "
            "so no kinetic parameter can be assumed transferable."
        ),
        "blocks": ["dissolved_oxygen_profile", "specific_growth_rate_mu_max"],
    },
    "node:N01#induction_time": {
        "label": "Time at which protein expression was induced",
        "missing_parameter": "MP-INDUCTION-TIME",
        "why_it_matters": (
            "Separates the growth phase from the production phase. The paper "
            "reports a total growth time and a post-induction duration but never "
            "states when induction happened."
        ),
        "blocks": ["induction_time_h", "post_induction_start_h"],
    },
}

#: What was actually searched, so an empty result is auditable.
SEARCH_SCOPE: dict[str, Any] = {
    "description": (
        "Searched for growth kinetics or substrate-affinity parameters applicable "
        "to the Zielinski 2019 fermentation, and for any source that restates the "
        "operating ranges the 2019 paper leaves as ranges."
    ),
    "queries": [
        "Escherichia coli recombinant human insulin pIBAINS growth kinetics",
        "Escherichia coli K-12 Monod mu_max Ks glucose minimal medium chemostat",
    ],
    "databases": ["general web literature", "Europe PMC REST (bibliographic verification)"],
    "result": (
        "No source reports a kinetic parameter for E. coli 20 carrying pIBAINS in "
        "GMS medium. The closest-matched publication, from the same institute and "
        "the same strain/vector/medium, reports no kinetics at all."
    ),
}


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

#: The passage each finding's central value was taken from, kept here so the
#: condition records above can quote the same text without repeating it.
_S = ("Depending on the model used, calculated glucose concentrations "
      "supporting half maximum growth rate (Ks) were in the range of 40-88 "
      "micrograms.1-1.")

CF_001 = CandidateFinding(
    finding_id="CF-001",
    target_missing_parameter="MP-GROWTH-KINETICS",
    target_quantity_ids=("node:N01#specific_growth_rate",),
    quantity_id="monod_half_saturation_constant",
    quantity_label="Half-saturation glucose concentration (Monod Ks)",
    value=88.0,
    unit="ug_per_L",
    provenance=Provenance.REPORTED,
    source=SourceLocation(
        citation=(
            "Senn H, Lendenmann U, Snozzi M, Hamer G, Egli T (1994). The growth of "
            "Escherichia coli in glucose-limited chemostat cultures: a "
            "re-examination of the kinetics. Biochim Biophys Acta 1201(3):424-436."
        ),
        doi="10.1016/0304-4165(94)90072-8",
        url="https://doi.org/10.1016/0304-4165(94)90072-8",
        pmid="7803473",
        open_access=False,
        section="Abstract",
        figure="",
        quote=(
            "Depending on the model used, calculated glucose concentrations "
            "supporting half maximum growth rate (Ks) were in the range of 40-88 "
            "micrograms.1-1."
        ),
    ),
    conditions={
        # Transcribed from Senn 1994's own wording. Where the abstract does not
        # state a condition it is recorded as "not stated", never omitted -- an
        # omitted condition would read as agreement.
        "organism": Condition(
            "organism", "Escherichia coli", _S, "senn1994"),
        "strain": Condition(
            "strain", "Escherichia coli ML30",
            "The relationship between specific growth rate (mu) and steady-state "
            "glucose concentration was investigated for Escherichia coli ML30 in "
            "carbon-limited chemostat culture.", "senn1994"),
        "construct": Condition(
            "construct", "none; wild type",
            "Escherichia coli ML30 in carbon-limited chemostat culture", "senn1994"),
        "product": Condition(
            "product", "none; no heterologous product expressed",
            "Escherichia coli ML30 in carbon-limited chemostat culture", "senn1994"),
        "medium": Condition(
            "medium", "minimal medium, carbon limited",
            "carbon-limited chemostat culture", "senn1994"),
        "substrate": Condition(
            "substrate", "glucose",
            "steady-state glucose concentration", "senn1994"),
        "mode": Condition(
            "mode", "continuous glucose-limited chemostat",
            "in carbon-limited chemostat culture", "senn1994"),
        "temperature_c": Condition("temperature_c", "not stated", "", "senn1994"),
        "ph": Condition("ph", "not stated", "", "senn1994"),
        "oxygen_transfer": Condition("oxygen_transfer", "not stated", "", "senn1994"),
        "measurement": Condition(
            "measurement", "population growth rate against steady-state glucose concentration",
            "The relationship between specific growth rate (mu) and steady-state "
            "glucose concentration was investigated", "senn1994"),
        "scale_l": Condition(
            "scale_l", "not stated",
            "laboratory chemostat", "senn1994"),
    },
    method=(
        "Steady-state glucose-limited chemostat. Cells were adapted for 100-200 "
        "volume changes at D = 0.6 h-1 before steady state. Ks was fitted between "
        "0.2 < D < 0.8 h-1 using three kinetic models that fit the data equally "
        "well (Monod 1942; Shehata & Marr 1971; Westerhoff et al. 1982)."
    ),
    uncertainty=UncertaintyRecord(
        kind="reported_range",
        lo=40.0,
        hi=88.0,
        basis=(
            "The three fitted models return different Ks across the same data; the "
            "source does not collapse them to one number."
        ),
    ),
    extraction_confidence=ExtractionConfidence.MEDIUM,
    does_not_resolve=(
        "The maintenance coefficient ms is not reported by this source.",
        "No oxygen-transfer parameter (kLa, agitation or air flow) is reported.",
        "The source itself concludes that published Ks values differ by orders of "
        "magnitude because of how far the cells were adapted, and that it is "
        "\"probably not possible to describe the kinetic properties of a bacterium "
        "with a single set of kinetic 'constants'\".",
    ),
    notes=(
        "The source reports a range, 40-88 micrograms.l-1. The upper bound is "
        "carried as the point value and the full range is kept in the uncertainty "
        "record. No midpoint was invented. The unit string in the quote is a "
        "text-extraction artefact for 'micrograms per litre'."
    ),
)

CF_002 = CandidateFinding(
    finding_id="CF-002",
    target_missing_parameter="MP-GROWTH-KINETICS",
    target_quantity_ids=("node:N01#specific_growth_rate",),
    quantity_id="specific_growth_rate",
    quantity_label="Specific growth rate, single cell",
    value=0.61,
    unit="per_h",
    provenance=Provenance.REPORTED,
    source=SourceLocation(
        citation=(
            "Smaluch K, Wollenhaupt B, Steinhoff H, Kohlheyer D, Gruenberger A, "
            "Dusny C (2023). Assessing the growth kinetics and stoichiometry of "
            "Escherichia coli at the single-cell level. Eng Life Sci 23(1):e2100157."
        ),
        doi="10.1002/elsc.202100157",
        url="https://doi.org/10.1002/elsc.202100157",
        pmid="36619887",
        open_access=True,
        section="Results and discussion",
        figure="Fig. 2B",
        quote=(
            "The obtained glucose-dependent specific growth rates of individual "
            "microcolonies based on quantitative phase imaging measurements ranged "
            "from mu = 0.19 h-1 to mu = 0.61 h-1 (see Figure 2B)."
        ),
    ),
    conditions={
        # Transcribed from the open-access full text of Smaluch 2023.
        "organism": Condition(
            "organism", "Escherichia coli",
            "the well-known and well-characterized Escherichia coli MG-1655", "smaluch2023"),
        "strain": Condition(
            "strain", "Escherichia coli MG1655",
            "we decided to investigate the growth kinetics and stoichiometry of the "
            "well-known and well-characterized Escherichia coli MG-1655", "smaluch2023"),
        "construct": Condition(
            "construct", "pVWEx1-gfpUV",
            "Escherichia coli MG-1655 transformed with the GFP expression plasmid "
            "pVWEx1-gfpUV", "smaluch2023"),
        "product": Condition(
            "product", "green fluorescent protein",
            "the GFP expression plasmid pVWEx1-gfpUV", "smaluch2023"),
        "medium": Condition(
            "medium", "M9 minimal medium",
            "Escherichia coli MG-1655 was cultivated in M9 minimal medium "
            "supplemented with trace elements and 1% (w/v) glucose", "smaluch2023"),
        "substrate": Condition(
            "substrate", "glucose, 1% (w/v)",
            "1% (w/v) glucose", "smaluch2023"),
        "mode": Condition(
            "mode", "microfluidic perfusion and agarose-pad single-cell cultivation",
            "cultivated in microfluidic perfusion systems on agarose pads",
            "smaluch2023"),
        "temperature_c": Condition(
            "temperature_c", "37",
            "all experiments were conducted at 37 degrees Celsius", "smaluch2023"),
        "ph": Condition("ph", "not stated", "", "smaluch2023"),
        "oxygen_transfer": Condition("oxygen_transfer", "not stated", "", "smaluch2023"),
        "measurement": Condition(
            "measurement", "single-cell optical dry mass by quantitative phase imaging",
            "specific growth rates of individual microcolonies based on quantitative "
            "phase imaging measurements", "smaluch2023"),
        "scale_l": Condition(
            "scale_l", "606 pL",
            "picoliter batch reactors with a volume of 606 pL", "smaluch2023"),
    },
    method=(
        "Quantitative phase imaging of single cells on agarose pads over a glucose "
        "range, giving a per-cell growth rate. Growth rate is normalised to optical "
        "cell mass rather than to a population OD."
    ),
    uncertainty=UncertaintyRecord(
        kind="reported_range",
        lo=0.19,
        hi=0.61,
        basis=(
            "Range across individual microcolonies; per-cell doubling times were "
            "combined as a geometric mean, which the source notes is less "
            "susceptible to outliers."
        ),
    ),
    extraction_confidence=ExtractionConfidence.HIGH,
    does_not_resolve=(
        "The measurement is a single-cell rate, which is not the population rate "
        "the 2019 process observed.",
        "The source reports no saturation constant of its own; the value it cites "
        "for comparison belongs to another paper.",
        "Nothing here speaks to a stirred-tank culture at litre scale.",
    ),
    notes=(
        "Temperature and substrate match the target process, but the construct, "
        "the medium, the mode and the measurement basis do not."
    ),
)

CF_003 = CandidateFinding(
    finding_id="CF-003",
    target_missing_parameter="",
    target_quantity_ids=(
        "node:N01#stationary_phase_od600",
        "node:N01#glucose_limitation_od600",
    ),
    quantity_id="growth_phase_od600_range",
    quantity_label="Growth-phase operating density ranges",
    value=35.0,
    unit="OD600",
    provenance=Provenance.REPORTED,
    source=SourceLocation(
        citation=(
            "Mikiewicz D, Bierczynska-Krzysik A, Sobolewska A, Stadnik D, et al. "
            "(2017). Soluble insulin analogs combining rapid- and long-acting "
            "hypoglycemic properties - From an efficient E. coli expression system "
            "to a pharmaceutical formulation. PLoS ONE 12(3):e0172600."
        ),
        doi="10.1371/journal.pone.0172600",
        url="https://doi.org/10.1371/journal.pone.0172600",
        open_access=True,
        section="Materials and methods, Cell culture and recovery of inclusion bodies",
        figure="",
        quote=(
            "When OD600 reached about 25-35, the glucose feeding was limited until "
            "its concentration in the medium was reduced to 0 g/dL."
        ),
    ),
    conditions={
        # Transcribed from Mikiewicz 2017's own wording, NOT harmonised to the
        # target's phrasing. These passages substantially overlap the Zielinski
        # 2019 methods section, which is exactly what the independence check is
        # there to detect -- and it does detect it.
        "organism": Condition(
            "organism", "Escherichia coli",
            "Escherichia coli 20 (IBA 1)", "mikiewicz2017"),
        "strain": Condition(
            "strain", "Escherichia coli 20 (IBA 1)",
            "Escherichia coli 20 (IBA 1), a derivative of Escherichia coli CSH50R",
            "mikiewicz2017"),
        "construct": Condition(
            "construct", "pIBAINS",
            "Escherichia coli 20 (IBA 1) harboring pIBAINS", "mikiewicz2017"),
        "product": Condition(
            "product", "recombinant human insulin analogs",
            "soluble insulin analogs expressed as fusions with superoxide dismutase",
            "mikiewicz2017"),
        "medium": Condition(
            "medium", "GMS medium",
            "cultivated in GMS medium supplemented with tetracycline, proline "
            "and thiamine", "mikiewicz2017"),
        "substrate": Condition(
            "substrate", "40% glucose",
            "40% (w/v) glucose was exponentially added as the carbon source",
            "mikiewicz2017"),
        "mode": Condition(
            "mode", "batch culture; glucose fed by pH-stat control",
            "glucose feeding was limited until its concentration in the medium was "
            "reduced to 0 g/dL", "mikiewicz2017"),
        "temperature_c": Condition(
            "temperature_c", "37",
            "cells were grown for 15-16 h at 37 degrees Celsius", "mikiewicz2017"),
        "ph": Condition(
            "ph", "pH-stat cascade control, dead band 0.01",
            "pH-stat control using cascade", "mikiewicz2017"),
        "oxygen_transfer": Condition("oxygen_transfer", "not reported", "", "mikiewicz2017"),
        "measurement": Condition(
            "measurement", "optical density at 600 nm",
            "When OD600 reached about 25-35", "mikiewicz2017"),
        "scale_l": Condition(
            "scale_l", "7.5 L",
            "a Bioflo Celligen 310 7.5 L fermenter", "mikiewicz2017"),
    },
    method=(
        "Operational description of the same institute's production culture on the "
        "same host and vector. Reported as prose ranges, not as fitted kinetics."
    ),
    uncertainty=UncertaintyRecord(
        kind="reported_range",
        lo=25.0,
        hi=35.0,
        basis="The source states the band as 'about 25-35'; no narrower range is given.",
    ),
    extraction_confidence=ExtractionConfidence.HIGH,
    does_not_resolve=(
        "This source reports NO kinetic parameter of any kind. It supplies no "
        "specific growth rate, no saturation constant and no maintenance "
        "coefficient, so it cannot inform MP-GROWTH-KINETICS at all.",
        "It reports ranges, so adopting it would not collapse the model's ranges "
        "either; the model declines to collapse ranges by policy.",
    ),
    notes=(
        "This is the closest-matched publication that exists: same institute, same "
        "host strain, same vector, same medium, same supplements, same fermenter, "
        "same pH-stat strategy. It is included precisely because it matches and "
        "still does not supply the missing number."
    ),
)

FINDINGS: tuple[CandidateFinding, ...] = (CF_001, CF_002, CF_003)


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def findings_for_port(port_id: str) -> tuple[CandidateFinding, ...]:
    return tuple(f for f in FINDINGS if port_id in f.target_quantity_ids)


def missing_information_required(port_id: str) -> list[str]:
    """What would actually be needed to close this gap, stated concretely.

    A gap that says only "more information needed" is not actionable. Each entry
    names the specific measurement and the process conditions it would have to
    come from.
    """
    matched = findings_for_port(port_id)
    if not matched:
        base = [
            "A measurement of this quantity made in this process: the same host "
            "strain carrying pIBAINS, in GMS medium, batch-fed by pH-stat, at "
            "37 degrees Celsius, in a 7.5 L fermenter.",
            "Either the raw time-series data behind it, or the fitted parameters "
            "with their stated fitting procedure.",
        ]
        if port_id.endswith("dissolved_oxygen"):
            base.append("Agitation rate, air flow and sparger geometry, so that a "
                        "kLa can be estimated rather than assumed.")
        if port_id.endswith("induction_time"):
            base.append("The point in the batch at which induction was triggered, "
                        "or the rule by which it was triggered.")
        return base

    needed: list[str] = []
    for f in matched:
        for reason in f.assess().reasons:
            if "differs from the target process" in reason or "not stated" in reason:
                needed.append("For %s: a measurement with %s." % (f.finding_id, reason))
    return needed or [
        "No candidate examined supplies this quantity under conditions matching "
        "the target process."
    ]


def inventory() -> dict[str, Any]:
    """The full machine-readable report.

    Structured to the nine required outputs: paper identity and provenance,
    records examined, extracted evidence with units and context, compatibility
    classification, reasons, missing information, conflicting evidence, and
    the unresolved-questions statement. Registry changes are not applied here;
    the report records what a reader might propose and leaves it at that.
    """
    conflicts = detect(FINDINGS)
    out: dict[str, Any] = {
        "report_version": "2",
        "records_examined": ZIELINSKI_RECORD.to_dict(),
        "targets": {},
        "findings": [],
        "conflicts": [c.to_dict() for c in conflicts],
        "search_scope": SEARCH_SCOPE,
    }

    for port_id, info in TARGETS.items():
        matched = findings_for_port(port_id)
        verdicts = [f.assess().verdict.value for f in matched]
        independent = [
            f.finding_id for f in matched
            if f.assess().independence is Independence.EXTERNAL
        ]
        out["targets"][port_id] = {
            **info,
            "candidate_count": len(matched),
            "verdicts": verdicts,
            "independent_candidates": independent,
            "resolved": False,
            "missing_information_required": missing_information_required(port_id),
            "search_scope": SEARCH_SCOPE,
        }

    for f in FINDINGS:
        out["findings"].append(f.to_dict())

    out["totals"] = {
        "targets": len(TARGETS),
        "findings": len(FINDINGS),
        "by_verdict": _verdict_counts(),
        "by_independence": _independence_counts(),
        "conflicts": summarise_conflicts(conflicts),
        "unresolved": sum(
            1 for f in FINDINGS if f.assess().verdict is not Verdict.VALIDATED
        ),
    }
    # Whether this report may state a definitive verdict at all. An unregistered
    # or ambiguous model makes every verdict in it provisional.
    out["verdict_authority"] = (
        "definitive" if ZIELINSKI_RECORD.is_definitive()
        else "provisional - " + (ZIELINSKI_RECORD.registry_detail
                                 or "the assessed model did not resolve to a "
                                    "registered model version")
    )
    # The governing statement, in the artefact itself rather than only in prose.
    out["authority"] = {
        "may_do": [
            "determine what is present, absent, inconsistent, or mechanically "
            "connectable under the declared rules",
        ],
        "may_not_do": [
            "invent a missing scientific value",
            "settle a conflict between sources",
            "infer equivalence from similar wording",
            "modify an existing model",
            "treat a literature match as validation",
        ],
        "validated_findings": 0,
        "registry_changes_applied": 0,
    }
    return out


def _verdict_counts() -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for f in FINDINGS:
        counts[f.assess().verdict.value] += 1
    return counts


def _independence_counts() -> dict[str, int]:
    counts = {i.value: 0 for i in Independence}
    for f in FINDINGS:
        counts[f.assess().independence.value] += 1
    return counts


def summarise_conflicts(conflicts) -> dict[str, int]:
    from .conflicts import summarise
    return summarise(conflicts)


def main(argv: list[str] | None = None) -> int:
    """Emit the assessed catalogue as JSON.

    Takes the same ``--result <path>`` contract as ``composition.runner`` so
    the Godot side reads it from disk exactly as it reads a model result,
    rather than needing to capture a subprocess's stdout.

    This performs no model execution and reads nothing at run time; it renders
    the curated records and the deterministic assessment of them.
    """
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="python -m composition.evidence.catalogue",
        description=(
            "Report candidate literature evidence for quantities a model could not resolve."
        ),
    )
    parser.add_argument("--result", help="path to write the catalogue JSON")
    args = parser.parse_args(argv)

    payload = inventory()
    text = json.dumps(payload, indent=2) + "\n"
    if args.result:
        path = Path(args.result)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        json.dump(
            {
                "catalogue_file": str(path),
                "targets": payload["totals"]["targets"],
                "findings": payload["totals"]["findings"],
                "by_verdict": payload["totals"]["by_verdict"],
                "exit_code": 0,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())