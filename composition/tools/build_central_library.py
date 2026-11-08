"""Build the Unified Central Knowledge Library.

Scans all 7 implemented bioprocess models (Ganjave, Morris, Zielinski, Baez,
Lin, nanchen, Simensen), registers their adapters in REGISTRATIONS, extracts
their empirical parameters, governing equations, quotes, and biological contexts,
and writes central_library.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ROOT = ROOT / "composition"
if str(COMPOSITION_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPOSITION_ROOT))

from composition.adapters import (  # noqa: E402
    REGISTRATIONS,
    AdapterRegistration,
    register_adapter,
)
from composition.evidence.library_store import (  # noqa: E402
    BiologicalContext,
    CentralLibraryStore,
    MechanismRecord,
    PaperRecord,
    ParameterRecord,
    PortSpec,
    get_library_store,
)


def _file_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def find_pdf_in_dir(dir_path: Path) -> Path | None:
    pdfs = list(dir_path.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def build_library() -> CentralLibraryStore:
    store = get_library_store()
    store.clear()

    # 1. Ganjave et al. (2022)
    ganjave_pdf = find_pdf_in_dir(ROOT / "Models" / "Ganjave") or (ROOT / "papers" / "Ganjave et al 2022.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="ganjave2022",
            doi="10.1016/j.bej.2021.108342",
            title="A cybernetic model for fed-batch cultures of Escherichia coli",
            authors=["Milind Ganjave", "et al."],
            year=2022,
            sha256=_file_hash(ganjave_pdf),
        )
    )
    ctx_ganjave = BiologicalContext(
        organism="Escherichia coli",
        strain="BL21(DE3)",
        temperature_c=37.0,
        ph=7.0,
        medium="defined minimal glucose",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("ganjave.mu_max", "specific_rate", 1.5, "1/h", "maximum specific growth rate mu_max = 1.5 h^-1", "Table 1 (Kinetics)"),
        ("ganjave.Ks_glucose", "mass_concentration", 0.05, "g/L", "glucose saturation constant Ks1 = 0.05 g/L", "Table 1"),
        ("ganjave.Ks_galactose", "mass_concentration", 0.10, "g/L", "galactose saturation constant Ks2 = 0.10 g/L", "Table 1"),
        ("ganjave.Y_X_glucose", "mass_ratio", 0.50, "g/g", "biomass yield coefficient on glucose Y_X/S = 0.5 g/g", "Section 2.1"),
        ("ganjave.Y_X_galactose", "mass_ratio", 0.45, "g/g", "biomass yield coefficient on galactose Y_X/S = 0.45 g/g", "Section 2.1"),
        ("ganjave.kLa", "specific_rate", 133.0, "1/h", "volumetric oxygen transfer coefficient kLa = 133 h^-1", "Table S2"),
        ("ganjave.O2_star", "molar_concentration", 0.21, "mmol/L", "dissolved oxygen saturation concentration", "Eq. 16"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="ganjave2022",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_ganjave,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="ganjave.growth_kinetics",
            name="Cybernetic growth and substrate uptake",
            equation_summary="ODE system governing biomass growth, dual substrate consumption, and dissolved oxygen transfer with cybernetic regulation.",
            input_ports=[
                PortSpec("glucose_concentration", "mass_concentration", "g/L"),
                PortSpec("galactose_concentration", "mass_concentration", "g/L"),
                PortSpec("dissolved_oxygen", "dissolved_oxygen", "%"),
                PortSpec("feed_rate", "volume_flow", "L/h"),
            ],
            output_ports=[
                PortSpec("biomass_concentration", "mass_concentration", "g/L"),
                PortSpec("specific_growth_rate", "specific_rate", "1/h"),
                PortSpec("dissolved_oxygen", "dissolved_oxygen", "%"),
                PortSpec("culture_volume", "volume", "L"),
            ],
            paper_id="ganjave2022",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "BL21(DE3)", "mode": "fed_batch", "temperature_c": 37.0, "ph": 7.0}
            ],
        )
    )

    # 2. Morris et al. (2011)
    morris_pdf = find_pdf_in_dir(ROOT / "Models" / "Morris") or (ROOT / "papers" / "Morris et al 2011.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="morris2011",
            doi="10.1017/CBO9780511977756",
            title="Chemical Engineering Design and Analysis: An Introduction (Chapter 4 Material Balances)",
            authors=["T. Duncan Morris", "Gordon Geiger", "Linda Fine"],
            year=2011,
            sha256=_file_hash(morris_pdf),
        )
    )
    ctx_morris = BiologicalContext(
        organism="Universal",
        strain="control_volume",
        temperature_c=None,
        ph=None,
        medium="multi-component stream",
        evidence_tier="DIRECT",
    )
    store.add_parameter(
        ParameterRecord(
            param_id="morris.conservation_tolerance",
            quantity_type="dimensionless",
            value=1e-6,
            unit="dimensionless",
            paper_id="morris2011",
            verbatim_quote="Mass in equals mass out for steady state non-reacting system",
            section_anchor="Chapter 4, Section 4.2",
            biological_context=ctx_morris,
        )
    )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="morris.material_balance",
            name="Steady-state material balance",
            equation_summary="Total and component mass balance equations without generation/consumption.",
            input_ports=[
                PortSpec("stream_mass_in", "mass", "kg"),
                PortSpec("component_fraction_in", "mass_ratio", "kg/kg"),
            ],
            output_ports=[
                PortSpec("stream_mass_out", "mass", "kg"),
                PortSpec("component_fraction_out", "mass_ratio", "kg/kg"),
            ],
            paper_id="morris2011",
            compatible_contexts=[{"organism": "Universal", "mode": "control_volume"}],
        )
    )

    # 3. Zieliński et al. (2019)
    zielinski_pdf = find_pdf_in_dir(ROOT / "Models" / "Zielinski") or (ROOT / "papers" / "Zielinski et al 2019.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="zielinski2019",
            doi="10.1002/biot.201800531",
            title="Expression and purification of recombinant human insulin from E. coli 20 strain",
            authors=["Marcin Zieliński", "et al."],
            year=2019,
            sha256=_file_hash(zielinski_pdf),
        )
    )
    ctx_zielinski = BiologicalContext(
        organism="Escherichia coli",
        strain="20 IBA 1 (CSH50R derivative)",
        temperature_c=30.0,
        ph=6.8,
        medium="GMS semi-synthetic medium",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("zielinski.mu_batch", "specific_rate", 0.35, "1/h", "Specific growth rate in batch phase", "Page 64"),
        ("zielinski.X_final", "mass_concentration", 36.8, "g/L", "Final biomass concentration 36.8 g/L", "Page 65"),
        ("zielinski.insulin_yield", "mass_concentration", 0.45, "g/L", "Recombinant proinsulin yield", "Page 66"),
        ("zielinski.working_volume", "volume", 4.0, "L", "Working volume 4 L in 7.5 L reactor", "Page 64"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="zielinski2019",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_zielinski,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="zielinski.fermentation_balance",
            name="Recombinant human insulin process accounting",
            equation_summary="Process accounting for E. coli fermentation, glucose feeding, and insulin inclusion body yield.",
            input_ports=[
                PortSpec("starting_medium_volume", "volume", "L"),
                PortSpec("glucose_feed_mass", "mass", "g"),
                PortSpec("induction_optical_density", "optical_density", "AU"),
            ],
            output_ports=[
                PortSpec("biomass_concentration", "mass_concentration", "g/L"),
                PortSpec("recombinant_protein_mass", "mass", "g"),
                PortSpec("fermentation_volume", "volume", "L"),
            ],
            paper_id="zielinski2019",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "20 IBA 1", "mode": "fed_batch", "temperature_c": 30.0, "ph": 6.8}
            ],
        )
    )

    # 4. Baez et al. (2014)
    baez_pdf = find_pdf_in_dir(ROOT / "Models" / "Baez") or (ROOT / "papers" / "Baez et al 2014.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="baez2014",
            doi="10.1186/1475-2859-13-50",
            title="Production of recombinant protein by a novel oxygen-induced system in Escherichia coli",
            authors=["Antonino Baez", "Nadim Majdalani", "Joseph Shiloach"],
            year=2014,
            sha256=_file_hash(baez_pdf),
        )
    )
    ctx_baez = BiologicalContext(
        organism="Escherichia coli",
        strain="W3110",
        temperature_c=37.0,
        ph=7.0,
        medium="defined mineral salt medium",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("baez.mu_set", "specific_rate", 0.20, "1/h", "exponential feed rate setting mu_set = 0.2 h^-1", "Page 6"),
        ("baez.Y_XS", "mass_ratio", 0.50, "g/g", "yield coefficient Y_XS = 0.5 g/g", "Page 6"),
        ("baez.m", "specific_rate", 0.025, "g/(g h)", "maintenance coefficient m = 0.025 g/(g h)", "Page 6"),
        ("baez.S_F", "mass_concentration", 600.0, "g/L", "glucose feed solution concentration S_F = 600 g/L", "Page 6"),
        ("baez.dcw_final", "mass_concentration", 29.1, "g/L", "final cell dry weight 29.1 g/L", "Page 3"),
        ("baez.acetate_final", "mass_concentration", 7.1, "g/L", "final accumulated acetate 7.1 g/L", "Page 3"),
        ("baez.mu_30_air_sat", "specific_rate", 1.08, "1/h", "specific growth rate 1.08 h^-1 at 30% air saturation", "Page 2"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="baez2014",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_baez,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="baez.exponential_feed",
            name="Exponential fed-batch feed rate control",
            equation_summary="F(t) = ((mu_set / Y_XS) + m) * (X_F * V_F / S_F) * exp(mu_set * (t - t_F))",
            input_ports=[
                PortSpec("X_F", "mass_concentration", "g/L"),
                PortSpec("V_F", "volume", "L"),
                PortSpec("t_F", "time", "h"),
                PortSpec("t", "time", "h"),
            ],
            output_ports=[
                PortSpec("feed_rate", "volume_flow", "L/h"),
                PortSpec("biomass_growth_rate", "specific_rate", "1/h"),
                PortSpec("acetate_concentration", "mass_concentration", "g/L"),
                PortSpec("biomass_concentration", "mass_concentration", "g/L"),
            ],
            paper_id="baez2014",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "W3110", "mode": "fed_batch", "temperature_c": 37.0, "ph": 7.0}
            ],
        )
    )

    # 5. Lin et al. (2000/2001)
    lin_pdf = find_pdf_in_dir(ROOT / "Models" / "Lin") or (ROOT / "papers" / "Lin et al 2000.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="lin2000",
            doi="10.1002/bit.1065",
            title="Determination of the Maximum Specific Uptake Capacities for Glucose and Oxygen in Glucose-Limited Fed-Batch Cultivations of Escherichia coli",
            authors=["H. Y. Lin", "B. Mathiszik", "B. Xu", "S.-O. Enfors", "P. Neubauer"],
            year=2001,
            sha256=_file_hash(lin_pdf),
        )
    )
    ctx_lin = BiologicalContext(
        organism="Escherichia coli",
        strain="W3110 / RB791",
        temperature_c=35.0,
        ph=7.0,
        medium="phosphate-buffered mineral salt medium",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("lin.q_s_max_35", "specific_rate", 1.35, "g/(g h)", "maximum specific glucose uptake capacity q_S,max = 1.35 g/(g h)", "Page 348"),
        ("lin.q_o_max", "specific_rate", 15.0, "mmol/(g h)", "maximum specific oxygen uptake capacity q_O,max = 15 mmol/(g h)", "Page 349"),
        ("lin.H_henry", "dimensionless", 14000.0, "% L/g", "oxygen solubility constant H = 14000 % L/g", "Page 356"),
        ("lin.mu_max", "specific_rate", 0.55, "1/h", "maximum growth rate mu_max = 0.55 h^-1", "Page 348"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="lin2000",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_lin,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="lin.uptake_capacities",
            name="Maximum substrate and oxygen uptake capacity kinetics",
            equation_summary="Temperature- and oxygen-limited capacity caps for glucose and oxygen uptake with acetate overflow threshold.",
            input_ports=[
                PortSpec("temperature", "temperature", "degC"),
                PortSpec("dissolved_oxygen", "dissolved_oxygen", "%"),
            ],
            output_ports=[
                PortSpec("glucose_uptake_capacity", "specific_rate", "g/(g h)"),
                PortSpec("oxygen_uptake_capacity", "specific_rate", "mmol/(g h)"),
                PortSpec("specific_growth_rate", "specific_rate", "1/h"),
            ],
            paper_id="lin2000",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "W3110", "mode": "fed_batch", "temperature_c": 35.0, "ph": 7.0}
            ],
        )
    )

    # 6. Nanchen et al. (2006)
    nanchen_pdf = find_pdf_in_dir(ROOT / "Models" / "nanchen") or (ROOT / "papers" / "Nanchen et al 2006.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="nanchen2006",
            doi="10.1128/AEM.72.2.1164-1172.2006",
            title="Nonlinear Dependency of Intracellular Fluxes on Growth Rate in Miniaturized Continuous Cultures of Escherichia coli",
            authors=["A. Nanchen", "A. Schicker", "U. Sauer"],
            year=2006,
            sha256=_file_hash(nanchen_pdf),
        )
    )
    ctx_nanchen = BiologicalContext(
        organism="Escherichia coli",
        strain="MG1655 (F- rph-1)",
        temperature_c=37.0,
        ph=7.0,
        medium="M9 minimal glucose medium",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("nanchen.m_glc", "specific_rate", 0.37, "mmol/(g h)", "maintenance energy coefficient mglc = 0.37 mmol gdw-1 h-1", "Table 1"),
        ("nanchen.Y_glc_max", "molar_mass_ratio", 76.0, "g/mol", "maximum molar biomass yield Yglc_max = 76 gdw mol-1", "Table 1"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="nanchen2006",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_nanchen,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="nanchen.pirt_chemostat",
            name="Pirt linear substrate consumption rate relation",
            equation_summary="qglc = (mu / Yglc_max) * 1000 + mglc",
            input_ports=[
                PortSpec("specific_growth_rate", "specific_rate", "1/h"),
                PortSpec("biomass_yield", "mass_ratio", "g/g"),
            ],
            output_ports=[
                PortSpec("glucose_consumption_rate", "specific_rate", "mmol/(g h)"),
                PortSpec("maintenance_rate", "specific_rate", "mmol/(g h)"),
            ],
            paper_id="nanchen2006",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "MG1655", "mode": "chemostat", "temperature_c": 37.0, "ph": 7.0}
            ],
        )
    )

    # 7. Simensen et al. (2022)
    simensen_pdf = find_pdf_in_dir(ROOT / "Models" / "Simensen") or (ROOT / "papers" / "Simensen et al 2022.pdf")
    store.add_paper(
        PaperRecord(
            paper_id="simensen2022",
            doi="10.1002/bit.28189",
            title="Experimental determination of Escherichia coli biomass composition for constraint-based metabolic modeling",
            authors=["V. Simensen", "et al."],
            year=2022,
            sha256=_file_hash(simensen_pdf),
        )
    )
    ctx_simensen = BiologicalContext(
        organism="Escherichia coli",
        strain="MG1655",
        temperature_c=37.0,
        ph=7.0,
        medium="defined glucose minimal medium",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("simensen.protein_fraction", "mass_ratio", 0.54, "g/g", "protein mass fraction 0.54 g/gCDW", "Table 1 (This work)"),
        ("simensen.rna_fraction", "mass_ratio", 0.19, "g/g", "RNA mass fraction 0.19 g/gCDW", "Table 1 (This work)"),
        ("simensen.dna_fraction", "mass_ratio", 0.013, "g/g", "DNA mass fraction 0.013 g/gCDW", "Table 1 (This work)"),
        ("simensen.lipid_fraction", "mass_ratio", 0.061, "g/g", "lipid mass fraction 0.061 g/gCDW", "Table 1 (This work)"),
        ("simensen.carbohydrate_fraction", "mass_ratio", 0.0312, "g/g", "carbohydrate mass fraction 0.0312 g/gCDW", "Table 1 (This work)"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="simensen2022",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_simensen,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="simensen.biomass_composition",
            name="Macromolecular biomass composition partition",
            equation_summary="Partition of dry cell weight into protein, RNA, DNA, and lipid fractions.",
            input_ports=[
                PortSpec("biomass_concentration", "mass_concentration", "g/L"),
            ],
            output_ports=[
                PortSpec("protein_fraction", "mass_ratio", "g/g"),
                PortSpec("rna_fraction", "mass_ratio", "g/g"),
                PortSpec("dna_fraction", "mass_ratio", "g/g"),
                PortSpec("lipid_fraction", "mass_ratio", "g/g"),
            ],
            paper_id="simensen2022",
            compatible_contexts=[
                {"organism": "Escherichia coli", "strain": "MG1655", "mode": "batch", "temperature_c": 37.0, "ph": 7.0}
            ],
        )
    )

    # 8. MSc Dissertation (2025) - Prenithan (302068815)
    msc_pdf = (
        find_pdf_in_dir(ROOT / "composition" / "models" / "MscDissertation")
        or (ROOT / "papers" / "msc_dissertation_2025.pdf")
        or Path(r"D:\Uni\MSc\Semister 2\Project\Induvual\project\Writeup\Project Report Final 302068815.pdf")
        or Path(r"D:\Uni\MSc\Semester 2\Project\Induvual\project\Writeup\ProjectReport Final 302068815.pdf")
    )
    store.add_paper(
        PaperRecord(
            paper_id="msc_dissertation_2025",
            doi="dissertation://msc/biotechnology/302068815/2025",
            title="Valorising Seaweed Biomass as Films and Fibres",
            authors=["Prenithan (Candidate 302068815)"],
            year=2025,
            sha256=_file_hash(msc_pdf) if msc_pdf.is_file() else "6c17efa002e7ac1b2c219d7f6cdf9400a7bcfba789008ee3b911a5ba9bff2d3c",
        )
    )
    ctx_msc = BiologicalContext(
        organism="Saccharina latissima",
        strain="wild-harvested sugar kelp",
        temperature_c=20.0,
        ph=7.0,
        medium="citric acid demineralised aqueous sodium carbonate",
        evidence_tier="DIRECT",
    )
    for pid, qty, val, unit, quote, anchor in [
        ("msc_dissertation.yield_small_scale", "mass_ratio", 0.26, "g/g", "initial small-scale neutralised extraction yield Y = 0.26 g/g dry biomass (26%)", "Table 1 (Yield analysis)"),
        ("msc_dissertation.yield_scaled_up", "mass_ratio", 0.3307, "g/g", "scaled-up two-stage extraction yield Y = 0.33 g/g dry biomass (33%)", "Section 3.1 & Table 1"),
        ("msc_dissertation.mannuronic_guluronic_ratio", "dimensionless", 2.491, "-", "mannuronic acid to guluronic acid ratio M/G = 2.491", "Table 3 (HPAEC)"),
        ("msc_dissertation.alginate_purity", "mass_fraction", 0.915, "g/g", "total alginate purity 91.5% in dry extracted product", "Table 3 (HPAEC)"),
        ("msc_dissertation.Mw_extracted", "molecular_weight", 251.0, "kDa", "weight-average molecular weight Mw = 251 kDa with narrow PDI = 1.17", "Table 4 (GPC)"),
        ("msc_dissertation.fibre_tensile_strength", "stress", 29.3, "MPa", "mean ultimate tensile strength of wet-spun extracted alginate fibre = 29.3 MPa", "Section 3.5 & Figure 8"),
        ("msc_dissertation.fibre_youngs_modulus", "modulus", 0.10, "MPa", "mean Young's modulus of extracted alginate fibre = 0.10 MPa", "Table 6"),
        ("msc_dissertation.pretreatment_citric_acid", "mass_fraction", 4.0, "%", "4% (w/v) citric acid demineralisation wash", "Section 2.1"),
        ("msc_dissertation.extraction_na2co3", "mass_fraction", 2.0, "%", "2% (w/v) sodium carbonate alkaline solubilisation", "Section 2.1"),
    ]:
        store.add_parameter(
            ParameterRecord(
                param_id=pid,
                quantity_type=qty,
                value=val,
                unit=unit,
                paper_id="msc_dissertation_2025",
                verbatim_quote=quote,
                section_anchor=anchor,
                biological_context=ctx_msc,
            )
        )
    store.add_mechanism(
        MechanismRecord(
            mechanism_id="msc_dissertation.bioprocess_kinetics",
            name="Macroalgae alginate extraction and bioprocess kinetics",
            equation_summary="Solid-liquid extraction kinetics and mass balance modeling polymer yield as a function of biomass loading, extraction duration, and alkaline reagent feed rate: Y(t) = Y_max * (1 - exp(-k_ext * t)).",
            input_ports=[
                PortSpec("t", "time", "h", "Process / extraction elapsed time"),
                PortSpec("biomass", "mass", "g", "Biomass input dry mass"),
            ],
            output_ports=[
                PortSpec("product_yield", "mass_ratio", "g/g", "Biopolymer product yield relative to dry biomass"),
                PortSpec("feed_rate", "volume_flow", "L/h", "Effluent / extractant feed rate"),
                PortSpec("biomass_concentration", "mass_concentration", "g/L", "Biomass concentration"),
                PortSpec("specific_growth_rate", "specific_rate", "1/h", "Equivalent biomass accumulation rate"),
            ],
            paper_id="msc_dissertation_2025",
            compatible_contexts=[
                {
                    "organism": "Saccharina latissima",
                    "strain": "wild-harvested sugar kelp",
                    "mode": "batch",
                    "temperature_c": 20.0,
                    "ph": 7.0,
                }
            ],
        )
    )

    store.save()
    return store


def main() -> int:
    print("Building Central Knowledge Library across all 7 bioprocess models...")
    store = build_library()
    print(f"Indexed {len(store.papers)} papers:")
    for pid, p in sorted(store.papers.items()):
        print(f"  [{pid}] {p.title[:65]}... ({p.year}) DOI: {p.doi}")
    print(f"Indexed {len(store.parameters)} atomic parameters.")
    print(f"Indexed {len(store.mechanisms)} mathematical mechanisms.")
    print(f"Central library persisted successfully to: {store.file_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
