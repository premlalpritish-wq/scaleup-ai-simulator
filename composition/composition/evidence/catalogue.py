"""The curated candidate-evidence catalogue for the Zielinski 2019 model.

Every record here was extracted from a publication that was actually retrieved
during development, and each carries the passage it was taken from. Nothing is
inferred from a title or an abstract summary alone: ``quote`` holds the text the
extraction was based on.

Three findings are registered. Together they demonstrate the three outcomes the
workflow has to distinguish:

* **incompatible** -- a published kinetic constant whose measurement conditions
  do not match the target process (CF-001, CF-002);
* **found, but not sufficient** -- a perfectly matched source that supplies no
  kinetic parameter at all and therefore cannot close the gap (CF-003);
* **no candidates at all** -- quantities for which nothing was found, recorded
  honestly as an empty result with a stated search scope.

Nothing here modifies or is imported by ``Models/Zielinski``. The model keeps
reporting its unknowns as unknown.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .candidate import (
    CandidateFinding,
    CompatibilityAssessment,
    ExtractionConfidence,
    ExperimentalConditions,
    Provenance,
    SourceLocation,
    UncertaintyRecord,
    Verdict,
    catalogue_payload,
)

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
    conditions=ExperimentalConditions(
        organism="Escherichia coli",
        strain="E. coli ML30",
        construct="none; wild type, no recombinant plasmid",
        product="none; no heterologous product expressed",
        medium="minimal medium, carbon limited",
        substrate="glucose",
        mode="continuous glucose-limited chemostat",
        temperature_c="not stated",
        ph="not stated",
        oxygen_transfer="not stated",
        measurement="population growth rate against steady-state glucose concentration",
        scale="laboratory chemostat",
    ),
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
    conditions=ExperimentalConditions(
        organism="Escherichia coli",
        strain="E. coli MG1655 transformed with pVWEx1-gfpUV",
        construct="pVWEx1-gfpUV, a GFP reporter plasmid; not an insulin expression construct",
        product="green fluorescent protein, a visualisation reporter rather than insulin",
        medium="M9 minimal medium",
        substrate="glucose, 1% w/v",
        mode="microfluidic perfusion and agarose-pad single-cell cultivation",
        temperature_c="37",
        ph="not stated",
        oxygen_transfer="not applicable at this scale; not stated",
        measurement="single-cell optical dry mass by quantitative phase imaging",
        scale="microscale; 606 pL picolitre batch chambers, 1.5 um growth channels",
    ),
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
    conditions=ExperimentalConditions(
        organism="Escherichia coli",
        strain="E. coli 20 (CSH50R derivative)",
        construct="pIBAINS (SOD-INS fusion, TetR, deoP1P2 promoter)",
        product="recombinant human insulin analogs as SOD fusions; the 2019 process expresses wild-type insulin",
        medium="GMS minimal medium",
        substrate="glucose, 40% w/v feed",
        mode="batch with pH-stat glucose feeding",
        temperature_c="37",
        ph="controlled with 16% NH4OH, dead band 0.01",
        oxygen_transfer="not reported",
        measurement="population OD600",
        scale="4 L working volume in a 7.5 L fermenter",
    ),
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


def inventory() -> dict[str, Any]:
    """What is registered, and what is known to be absent."""
    out: dict[str, Any] = {"targets": {}, "findings": []}
    for port_id, info in TARGETS.items():
        matched = findings_for_port(port_id)
        verdicts = [f.assess().verdict.value for f in matched]
        out["targets"][port_id] = {
            **info,
            "candidate_count": len(matched),
            "verdicts": verdicts,
            "resolved": False,
            "search_scope": SEARCH_SCOPE,
        }
    for f in FINDINGS:
        out["findings"].append(f.to_dict())
    out["search_scope"] = SEARCH_SCOPE
    out["totals"] = {
        "targets": len(TARGETS),
        "findings": len(FINDINGS),
        "by_verdict": _verdict_counts(),
    }
    return out


def _verdict_counts() -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for f in FINDINGS:
        counts[f.assess().verdict.value] += 1
    return counts


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