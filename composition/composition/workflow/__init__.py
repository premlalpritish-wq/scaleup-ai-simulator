"""Research-to-simulation workflow.

This package implements the five stages that precede a composition run:

1. :mod:`composition.workflow.problem` -- turn a problem statement into a
   :class:`ProblemSpec`, recording every absent field as unknown;
2. :mod:`composition.workflow.literature` -- rank a local, already-downloaded
   corpus and acquire the selected papers;
3. :mod:`composition.workflow.extract` -- read JATS XML, plain text or PDF into
   section-located text;
4. :mod:`composition.workflow.encoding` -- verify every quote and number and
   separate target-organism evidence from analogy;
5. :mod:`composition.workflow.model_builder` -- build an evidence-constrained
   model spec and place it in a normal composition graph.

:func:`composition.workflow.execute.run_workflow` orchestrates those stages and
then hands the graph to the existing :func:`composition.runner.run_graph`.
"""

from .encoding import EncodingError, encode, load_passages
from .execute import run_workflow
from .literature import LiteratureError, discover, load_corpus
from .problem import ProblemInput, load_problem, parse_problem
from .schema import (
    CLAIM_KINDS,
    SPECIFICITIES,
    STATE_DERIVED,
    STATE_REPORTED,
    STATE_UNKNOWN,
    EncodedResearch,
    EvidenceClaim,
    ModelSpec,
    ProblemSpec,
    ProtocolStep,
    SourceRecord,
    SourceText,
    StepParameter,
    TrackedValue,
    WorkflowDiagnostic,
    WorkflowRun,
)

__all__ = [
    "CLAIM_KINDS",
    "SPECIFICITIES",
    "STATE_DERIVED",
    "STATE_REPORTED",
    "STATE_UNKNOWN",
    "EncodedResearch",
    "EncodingError",
    "EvidenceClaim",
    "LiteratureError",
    "ModelSpec",
    "ProblemInput",
    "ProblemSpec",
    "ProtocolStep",
    "SourceRecord",
    "SourceText",
    "StepParameter",
    "TrackedValue",
    "WorkflowDiagnostic",
    "WorkflowRun",
    "discover",
    "encode",
    "load_corpus",
    "load_passages",
    "load_problem",
    "parse_problem",
    "run_workflow",
]
