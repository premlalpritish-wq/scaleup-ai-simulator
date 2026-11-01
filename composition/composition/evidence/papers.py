"""Which ingested papers have a model, and what was decided about the rest.

``Models/`` is a literature corpus: one folder per paper, holding the PDF the
project was given. Some of those papers have a model package; most do not. Before
this module nothing recorded that mapping, so the corpus could grow -- as it did,
from four folders to fifteen -- without anything noticing that a paper had arrived
and nobody had decided what it was for.

Each record below answers the questions the audit in
``reports/PAPER_MODEL_COVERAGE_AUDIT.md`` asks of a paper:

* **folder** -- where the paper lives;
* **model_package** -- the package that encodes it, if one exists;
* **model_id** -- the composition registration, if it is registered;
* **determination** -- one of the closed vocabulary below;
* **reason** -- why, stated as a *kind* of mismatch (strain, construct, mode,
  medium, scale, review) rather than as a verdict about quality.

This module is an index, not a scientific claim. It reads the corpus and the
registry; it does not decide compatibility, does not restate
:mod:`composition.cross_model`, and is imported by no model. ``--check`` fails when
a folder has no record, when a record names a folder that is gone, when a recorded
registration does not exist, when a record claims a package the tree does not
contain, or when a determination is outside the vocabulary.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Repository root: this file is <root>/composition/composition/evidence/papers.py
ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "Models"

#: The closed vocabulary. A determination outside it is a typo, not a new outcome.
DETERMINATIONS = (
    #: A model package exists and is registered, so it can be placed in a graph.
    "encoded",
    #: A model package exists but is deliberately not registered.
    "encoded_unregistered",
    #: A measurement exists, but for a different process context.
    "refused",
    #: Nothing in the paper can support a model: a review, a method, or mechanism.
    "not_supportable",
    #: Could inform a model that does not yet exist (a spanning model).
    "candidate_input",
)

#: The process a paper must describe to carry a quantity into the insulin model.
TARGET_PROCESS = (
    "E. coli 20 IBA 1 (CSH50R derivative), plasmid pIBAINS, GMS medium, 4 L in a "
    "7.5 L Bioflo Celligen 310, batch with pH-stat glucose feeding, 30 degC"
)


@dataclass(frozen=True)
class Paper:
    """One paper in the corpus and the standing of its findings.

    The link to a model or to an evidence-only record is **derived**, not stored
    a second time: a paper whose folder appears in
    :data:`composition.evidence.standalone.STANDALONE_MODELS` links to that
    standalone package, a paper with a ``model_id`` links to the composition
    registry, and everything else is evidence-only and links to its own record in
    this index. There is nothing here to keep in step by hand.
    """

    folder: str
    citation: str
    determination: str
    reason: str
    model_package: str = ""
    model_id: str = ""

    # -- the link --------------------------------------------------------- #

    @property
    def standalone(self):
        """The standalone-model entry for this folder, or ``None``."""
        from .standalone import by_paper

        return by_paper(self.folder)

    @property
    def executables_standalone(self) -> bool:
        """True when a runnable package implements this paper on its own."""
        return self.standalone is not None

    @property
    def composes(self) -> bool:
        """True when the composition layer can place this model in a graph."""
        return bool(self.model_id)

    @property
    def link_kind(self) -> str:
        """``composed_model``, ``standalone_model`` or ``evidence_only``."""
        if self.composes:
            return "composed_model"
        if self.executables_standalone:
            return "standalone_model"
        return "evidence_only"

    @property
    def evidence_record(self) -> str:
        """The evidence-only record id for a paper with no model at all."""
        if self.composes or self.executables_standalone:
            return ""
        return f"paper:{self.folder}#{self.determination}"

    @property
    def link(self) -> str:
        """What this entry points at: an id, a module, or an evidence record."""
        if self.composes:
            return self.model_id
        if self.executables_standalone:
            return self.standalone.module
        return self.evidence_record

    def to_dict(self) -> dict[str, object]:
        entry = self.standalone
        return {
            "folder": self.folder,
            "citation": self.citation,
            "determination": self.determination,
            "reason": self.reason,
            "model_package": self.model_package,
            "model_id": self.model_id,
            "registered": bool(self.model_id),
            "executable_standalone": self.executables_standalone,
            "composable": self.composes,
            "link_kind": self.link_kind,
            "link": self.link,
            "standalone_module": entry.module if entry else "",
            "standalone_artefact_id": entry.artefact_id if entry else "",
            "standalone_kind": entry.kind if entry else "",
            "evidence_record": self.evidence_record,
        }


PAPERS: tuple[Paper, ...] = (
    Paper(
        "Baez",
        "A. Baez, N. Majdalani, J. Shiloach (2014), Production of recombinant protein "
        "by a novel oxygen-induced system in Escherichia coli",
        "encoded_unregistered",
        "Standalone model package (baez2014): one printed formula and the reported "
        "observations, explicitly excluding a growth, oxygen or GFP predictive model. "
        "Not registered, so it cannot be composed.",
        model_package="Models/Baez",
    ),
    Paper(
        "Baez and Shiloach",
        "A. Baez, J. Shiloach (2013), Escherichia coli avoids high dissolved oxygen "
        "stress by activation of SoxRS and manganese-superoxide dismutase",
        "not_supportable",
        "Strain differs (MG1655, not E. coli 20) and the finding is mechanism "
        "(oxygen-stress regulation), not a process quantity.",
    ),
    Paper(
        "Bhattacharya",
        "S. K. Bhattacharya, A. K. Dubey (1997), Effects of dissolved oxygen and oxygen "
        "mass transfer on overexpression of target gene in recombinant E. coli",
        "refused",
        "Construct and product differ (K-12/JM109 expressing MspI methylase, not "
        "pIBAINS/human insulin): kLa and DO optima are another construct's oxygen demand.",
    ),
    Paper(
        "Farrell",
        "P. Farrell et al. (2015), The use of dissolved oxygen-controlled, fed-batch "
        "aerobic cultivation for recombinant protein subunit vaccine manufacturing",
        "refused",
        "Strains and feed control differ (unnamed recombinant E. coli, DO-stat rather "
        "than the pH-stat cascade), and the content is a scale-down method.",
    ),
    Paper(
        "Ganjave",
        "Ganjave et al. (2022), cybernetic growth and fed-batch model, Biotechnology "
        "Reports 33:e00694",
        "encoded",
        "Registered as a cybernetic fed-batch growth model; different strain, medium "
        "and scale from the target process.",
        model_package="Models/Ganjave",
        model_id="ganjave",
    ),
    Paper(
        "Krause",
        "M. Krause, A. Neubauer, P. Neubauer (2016), The fed-batch principle for the "
        "molecular biology lab (review)",
        "not_supportable",
        "Review: aggregations across many strains, vectors and media, with no single "
        "process and medium to declare.",
    ),
    Paper(
        "Lemuth",
        "K. Lemuth et al. (2008), Global transcription and metabolic flux analysis of "
        "Escherichia coli in glucose-limited fed-batch cultivations",
        "refused",
        "Strain differs (K-12 W3110) and the quantities are transcript levels and "
        "intracellular fluxes, not process quantities.",
    ),
    Paper(
        "Lin",
        "H. Y. Lin et al. (2000), Determination of the maximum specific uptake "
        "capacities for glucose and oxygen in glucose-limited fed-batch cultivations",
        "encoded_unregistered",
        "The Appendix prints a complete simulation model, so it is encoded as the "
        "standalone package lin2000. Different strain (W3110/K-12), medium, reactor "
        "and feed control from the target process, so it is not registered and "
        "cannot be composed.",
        model_package="Models/Lin",
    ),
    Paper(
        "Marish",
        "K. Marisch et al. (2013), A comparative analysis of industrial Escherichia "
        "coli K-12 and B strains in high-glucose batch cultivations",
        "refused",
        "Strains differ (BL21, RV308, HMS174) and the mode differs (high-glucose batch, "
        "not pH-stat fed-batch). Folder name misspells the first author.",
    ),
    Paper(
        "Mikiewicz",
        "D. Mikiewicz et al. (2017), Soluble insulin analogs combining rapid- and "
        "long-acting hypoglycemic properties",
        "refused",
        "Same institute, strain, vector, medium and fermenter as the target, but it "
        "reports no kinetic parameter and its cited passage occurs in the target paper "
        "itself (evidence catalogue CF-003, CFL-01 not_independent_of_target).",
    ),
    Paper(
        "Morris",
        "R. Morris, G. Geiger, L. Fine (2011), material balances (Chapter 4)",
        "encoded",
        "Registered as an instance-parameterised non-reacting control-volume engine; "
        "not an organism model.",
        model_package="Models/Morris",
        model_id="morris2011.material_balance",
    ),
    Paper(
        "nanchen",
        "A. Nanchen, A. Schicker, U. Sauer (2006), Nonlinear dependency of intracellular "
        "fluxes on growth rate in miniaturized continuous cultures",
        "encoded_unregistered",
        "Equation (3) prints Pirt's chemostat relation with this paper's own fitted "
        "maintenance parameters, so it is encoded as the standalone package "
        "nanchen2006. The 13C flux-ratio equations are declared absent (their inputs "
        "are not tabulated). Different strain, mode and scale from the target "
        "process, so it is not registered.",
        model_package="Models/nanchen",
    ),
    Paper(
        "Siew and Zhang",
        "Y. Y. Siew, W. Zhang (2021), Downstream processing of recombinant human insulin "
        "and its analogues production from E. coli inclusion bodies (review)",
        "not_supportable",
        "Review: aggregated across strains and plants, and its only mention of "
        "'E. coli 20' is a reference-list citation of the target paper itself.",
    ),
    Paper(
        "Simensen",
        "V. Simensen et al. (2022), Experimental determination of Escherichia coli "
        "biomass composition for constraint-based metabolic modeling",
        "encoded_unregistered",
        "Table 1 is a quantitative dataset of the paper's own measurement, so it is "
        "encoded as the standalone package simensen2022. Strain, medium, scale and "
        "mode differ from the target process, and the paper states that biomass "
        "composition is condition-dependent, so it is not registered.",
        model_package="Models/Simensen",
    ),
    Paper(
        "Zielinski",
        "M. Zielinski et al. (2019), Expression and purification of recombinant human "
        "insulin from E. coli 20 strain, Protein Expr Purif 157:63-69",
        "encoded",
        "Registered as the target process; evidence replay with fail-closed prediction "
        "and eight declared absent models.",
        model_package="Models/Zielinski",
        model_id="zielinski2019.rhi_process",
    ),
)


def registered_model_ids() -> set[str]:
    """Every model id the composition layer registers, imported lazily."""
    from ..adapters import REGISTRATIONS

    return {registration.model_id for registration in REGISTRATIONS}


def corpus_folders(corpus: Path = CORPUS) -> tuple[str, ...]:
    """Folder names under the corpus that actually hold a PDF."""
    if not corpus.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in corpus.iterdir()
            if entry.is_dir() and any(entry.glob("*.pdf"))
        )
    )


def audit(
    corpus: Path = CORPUS, registered: set[str] | None = None
) -> dict[str, object]:
    """The index, plus every way it can disagree with the tree."""
    known = registered_model_ids() if registered is None else registered
    folders = corpus_folders(corpus)
    recorded = {paper.folder for paper in PAPERS}

    return {
        "corpus": str(corpus),
        "target_process": TARGET_PROCESS,
        "papers": [paper.to_dict() for paper in PAPERS],
        "counts": {
            determination: sum(
                1 for paper in PAPERS if paper.determination == determination
            )
            for determination in DETERMINATIONS
        },
        "folders_on_disk": list(folders),
        #: Papers present in the corpus with no recorded determination.
        "unrecorded_folders": [name for name in folders if name not in recorded],
        #: Records naming a folder the corpus does not contain.
        "missing_folders": [name for name in sorted(recorded) if name not in folders],
        #: Records whose model_id is not a registration.
        "unknown_registrations": sorted(
            paper.model_id
            for paper in PAPERS
            if paper.model_id and paper.model_id not in known
        ),
        #: Records claiming a model package the tree does not contain.
        "missing_packages": sorted(
            paper.model_package
            for paper in PAPERS
            if paper.model_package and not (ROOT / paper.model_package).is_dir()
        ),
        #: Records using a determination outside the closed vocabulary.
        "unknown_determinations": sorted(
            {
                paper.determination
                for paper in PAPERS
                if paper.determination not in DETERMINATIONS
            }
        ),
        #: A record with no reason cannot be reviewed.
        "unexplained": sorted(paper.folder for paper in PAPERS if not paper.reason.strip()),
        #: A record that claims a package must say which registration it is, or
        #: state that it is deliberately unregistered.
        "unattributed_packages": sorted(
            paper.folder
            for paper in PAPERS
            if paper.model_package and not paper.model_id
            and paper.determination != "encoded_unregistered"
        ),
        #: Every entry must point somewhere: a registration, a standalone model,
        #: or its own evidence-only record.
        "papers_without_a_link": sorted(paper.folder for paper in PAPERS if not paper.link),
        #: A package that is neither registered nor a known standalone model would
        #: be a model nothing can run and nothing can reach.
        "unlinked_model_packages": sorted(
            paper.folder
            for paper in PAPERS
            if paper.model_package and not paper.composes
            and not paper.executables_standalone
        ),
        #: A paper whose model is both composable and standalone would conflate two
        #: different configurations; the index must keep them apart.
        "conflicting_claims": sorted(
            paper.folder
            for paper in PAPERS
            if paper.composes and paper.executables_standalone
        ),
        #: A standalone-model record naming a folder the index does not record.
        "orphan_standalone_entries": sorted(
            entry.paper_folder
            for entry in standalone_entries()
            if entry.paper_folder not in recorded
        ),
        #: How every paper is reachable, which is the question this step answers.
        "execution": {
            "composable": sorted(p.folder for p in PAPERS if p.composes),
            "standalone": sorted(
                p.folder for p in PAPERS if p.executables_standalone
            ),
            "evidence_only": sorted(
                p.folder for p in PAPERS if p.link_kind == "evidence_only"
            ),
        },
    }


def standalone_entries() -> tuple[Any, ...]:
    """The standalone-model registry, imported lazily to keep this module cheap."""
    from .standalone import STANDALONE_MODELS

    return STANDALONE_MODELS


#: The keys `problems()` reports on, in the order they are printed.
PROBLEM_KEYS = (
    "unrecorded_folders",
    "missing_folders",
    "unknown_registrations",
    "missing_packages",
    "unknown_determinations",
    "unexplained",
    "unattributed_packages",
    "papers_without_a_link",
    "unlinked_model_packages",
    "conflicting_claims",
    "orphan_standalone_entries",
)


def problems(report: dict[str, object]) -> list[str]:
    """Every way the index and the tree disagree, as one list of messages."""
    out: list[str] = []
    for key in PROBLEM_KEYS:
        for item in report[key]:
            out.append(f"{key}: {item}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m composition.evidence.papers",
        description=(
            "Report which ingested papers a model encodes, and why the rest do not."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the corpus and this index disagree",
    )
    args = parser.parse_args(argv)

    report = audit()
    counts = report["counts"]
    print(f"corpus: {report['corpus']}")
    print(f"papers recorded: {len(report['papers'])}")
    for determination in DETERMINATIONS:
        print(f"  {determination:20s} {counts[determination]}")

    execution = report["execution"]
    print("execution:")
    for kind in ("composable", "standalone", "evidence_only"):
        print(f"  {kind:15s} {len(execution[kind]):2d}  {', '.join(execution[kind])}")

    failures = problems(report)
    for failure in failures:
        print(("FAIL " if args.check else "NOTE ") + failure)
    if args.check:
        if failures:
            return 1
        print("PASS -- every paper has a determination and links to a model or a record")
    return 0


if __name__ == "__main__":
    sys.exit(main())


