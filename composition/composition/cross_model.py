"""Which models may be composed, and why -- as declared data, enforced at validation.

The engine already refuses a connection whose quantities differ, whose units do
not convert, or whose component identity does not line up. Every one of those
checks is *mechanical*. A matching quantity and a convertible unit are together
necessary and nowhere near sufficient: ``ganjave/biomass_concentration`` and
``zielinski/node:N01#wet_biomass_g_per_L_reported`` are both
``mass_concentration`` in ``g/L``, both describe an *E. coli* culture, and no
amount of arithmetic makes one the other. The first is dry-cell weight in a
2022 cybernetic fed-batch; the second is wet biomass in a 2019 insulin culture.
Feeding one into the other would silently substitute a definitional factor of
about three and, worse, assert that two unrelated experiments share a culture.

This module states the position between models explicitly, so that:

* the engine refuses such a connection **at validation time**, with the reason
  attached, rather than accepting it and letting a reader conclude it meant
  something; and
* the whole position is **inspectable as data** -- ``python -m composition.runner
  --describe-connections`` -- rather than only existing as behaviour.

## What is permitted

Exactly one boundary, and it is permitted for the reason the balance engine
itself exists:

``morris2011.material_balance -> morris2011.material_balance``

Conservation across adjacent non-reacting control volumes is the premise of
Morris, Geiger & Fine (2011) Chapter 4. Both instances declare their component
sets, the engine checks that the sets agree, and the balance closes. That is
also the only boundary in this repository that is exercised by a shipped
example, and the only one whose propagated quantities carry a provenance chain
that names the upstream instance.

"Same model on both sides" is not one answer but two. ``Ganjave ->
Ganjave`` is **permitted** as a forward cascade, on the assumption
Ganjave's own connection contract states for the one port it declares
upstream-supplyable. ``Zielinski -> Zielinski`` is refused: Zielinski
declares no supplyable port, because its ports are the operating
conditions of one reported experiment and not a stream another run
could take.

## What is refused, and why

Every other pairing falls into one of three groups:

1. **No shared quantity exists.** Morris publishes ``mass`` and ``mass_fraction``
   and accepts only Morris's five kinds; Ganjave publishes
   ``mass_concentration``, ``dimensionless``, ``volume`` and ``time``. The sets
   are disjoint, so no connection between them is even mechanically constructible
   (see :data:`composition.dimensions.MORRIS_KIND_TO_QUANTITY` and
   :data:`composition.dimensions.GANJAVE_KIND_TO_QUANTITY`).
2. **The engine already refuses it.** Anything between Morris and Zieliński is
   refused by CG-08 (``connection.component_unattributed``) or CG-09
   (``capability.reactive_balance_refused``), because Zieliński publishes
   process roles rather than conserved entities. This module records the
   verdict and its evidence; it deliberately does not emit a second, redundant
   diagnostic for the same connection.
3. **Mechanically legal, scientifically unsupported.** Every Zieliński <-> Ganjave
   pairing. These are the ones the engine had no rule for, and they are refused
   here.

## What this module does not do

It does not claim that the two cultures are scientifically unrelated. They are
both *Escherichia coli* fed-batch cultures, and a future model built to be
matched to both -- declaring a shared component set, a dry-to-wet biomass basis
and a scale relationship -- could legitimately carry quantities between them.
That model does not exist here, and writing the connection now would be
predicting the answer. Each refusal says what would have to exist first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .adapters.ganjave_contract import INPUT_CONTRACT as _INPUT_CONTRACT

MORRIS = "morris2011.material_balance"
ZIELINSKI = "zielinski2019.rhi_process"
GANJAVE = "ganjave"


@dataclass(frozen=True)
class Verdict:
    """One connection's standing between two models."""

    source_model: str
    target_model: str
    #: (source quantity, target quantity) this verdict was selected by.
    quantity_pair: tuple[str, str] | None
    permitted: bool
    #: A short, stable slug for the position, for tests and for the report.
    stance: str
    reason: str
    evidence: tuple[str, ...] = ()
    #: What would have to exist before the connection could be made honestly.
    unresolved: tuple[str, ...] = ()
    remediation: str = ""
    #: *Why* this verdict was reached, which is not the same as whether it is
    #: permitted. ``documented_incompatibility`` means a source states the two
    #: cannot be connected. ``evidence_limited`` means no rule classifies the
    #: pair and the policy fails closed -- which is an absence of a judgement,
    #: **not** evidence of physical incompatibility, and a report must not
    #: present it as one. ``permitted`` means a source supports it.
    evidence_basis: str = "documented_incompatibility"
    #: The physical premises a permitted connection rests on. An operator has to
    #: accept these; a matching quantity does not discharge them.
    assumptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "source_model": self.source_model,
            "target_model": self.target_model,
            "quantity_pair": list(self.quantity_pair) if self.quantity_pair else None,
            "permitted": self.permitted,
            "stance": self.stance,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "unresolved": list(self.unresolved),
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class Boundary:
    """The standing of one ordered pair of models, and the rules under it."""

    source_model: str
    target_model: str
    stance: str
    permitted: bool
    #: True when the engine's own mechanical rules already refuse every
    #: connection this boundary could carry. The engine consults
    #: :func:`check` only after those pass, so this boundary contributes a
    #: recorded position rather than a duplicate diagnostic.
    enforced_by_engine: bool
    reason: str
    evidence: tuple[str, ...] = field(default=())
    unresolved: tuple[str, ...] = field(default=())
    remediation: str = ""
    rules: tuple[tuple[str, str], ...] = field(default=())
    #: The physical premises a permitted connection rests on. Declared here so
    #: each boundary carries its own, rather than one boundary's premise being
    #: applied to another.
    assumptions: tuple[str, ...] = field(default=())
    #: Why the pairing has no port pair at all, when it does not.
    dimensional_note: str = ""

    @property
    def evidence_basis(self) -> str:
        """*Why* this boundary has the standing it has.

        ``documented_incompatibility`` means a source states the two cannot
        be connected. ``evidence_limited`` means no rule classifies the pair
        and the policy fails closed -- an absence of a judgement, **not**
        evidence of physical incompatibility. ``permitted`` means a source
        supports it.
        """
        if self.permitted:
            return "permitted"
        if self.stance == "refused_unclassified":
            return "evidence_limited"
        return "documented_incompatibility"


#: The shared, cited evidence. Repeated in every verdict that leans on it, so a
#: diagnostic read in isolation still carries its own sources.
EVIDENCE = {
    "morris": (
        "Morris, Geiger & Fine (2011), Fundamentals of Material Balances with "
        "Applications to Non-Reacting Systems, Chapter 4: conservation "
        "equations sum(inflow) - sum(outflow) [- accumulation] = 0, with no "
        "reaction term.",
        "composition/composition/adapters/morris.py::_slot_map -- the "
        "composition-side port surface derived from a declared control volume.",
        "composition/examples/brass_batch_chain.json -- the shipped graph that "
        "carries material between two Morris instances.",
    ),
    "zielinski": (
        "Zielinski et al. (2019), Protein Expression and Purification 157: "
        "63-69, doi:10.1016/j.pep.2019.02.002. E. coli 20 strain, recombinant "
        "human insulin, 4 L working volume in a 7.5 L nominal fermenter.",
        "Models/Zielinski/scaleup_ai: the process graph declares operating "
        "conditions, measurements and calculated quantities; StreamKind is a "
        "process-role vocabulary (wet_biomass, inclusion_bodies, "
        "chromatographic_fraction), not a set of conserved entities.",
        "composition/composition/adapters/zielinski.py -- the adapter publishes "
        "every quantity the model's own graph declares, with its provenance.",
    ),
    "ganjave": (
        "Ganjave et al. (2022), Biotechnology Reports 33:e00694, "
        "doi:10.1016/j.btre.2021.e00694. Cybernetic fed-batch culture, "
        "equations (8)-(16), parameters from the paper's Table 2 loaded as "
        "fitted.",
        "Models/Ganjave/models/composition.py -- the model's own declaration of "
        "its ports, its required inputs and its unsupported capabilities, "
        "including component_identity.",
        "composition/composition/adapters/ganjave_contract.py::INPUT_CONTRACT "
        "-- what Ganjave will and will not accept on an input port, in the "
        "model's own words.",
    ),
    "quantity": (
        "composition/composition/dimensions.py -- the declared quantity "
        "vocabularies of all three models, kept as data rather than inferred "
        "from a unit.",
    ),
}


MORRIS_NOT_A_CULTURE = (
    "Morris is not an organism model. It is a non-reacting control-volume "
    "engine: it conserves declared masses and fractions and has nowhere to "
    "declare a yield, a rate constant or a reaction. Feeding a culture into it "
    "would require a component set the culture does not publish, and drawing a "
    "balance around a reaction it cannot express would be arithmetically valid "
    "and physically wrong."
)

_GANJAVE_TO_ZIELINSKI = (
    "Both models describe an Escherichia coli fed-batch culture, and neither "
    "quantity nor unit is what stands between them. They are two different "
    "experiments: different strain, different construct, different medium, "
    "different scale, different objective, five years apart. A matching "
    "quantity here is a coincidence of the vocabulary, not a shared physical "
    "quantity, and connecting them would substitute one culture's reported "
    "number for another's while reporting a success."
)

_ZIELINSKI_TO_GANJAVE = (
    "The two cultures share an organism and nothing else. Nothing in either "
    "paper declares a relationship between them: not a component set, not a "
    "biomass basis, not a scale relationship, and not a medium. Forwarding a "
    "quantity between them is not a transfer, it is an assertion about two "
    "unrelated batches that no source in this repository supports."
)

_RESOLVE_BY_COMPONENT = (
    "A model built to be matched to both -- declaring a shared component set, "
    "an explicit dry-to-wet biomass basis, a scale relationship and a common "
    "medium -- could carry quantities between them honestly. No such model "
    "exists here."
)

#: The Ganjave cascade's physical premise, read from the model rather than
#: restated here. ``ganjave_contract.INPUT_CONTRACT`` is where that premise is
#: recorded, in the words of whoever wrote it; copying the string into this file
#: would be a second place to update and a way for the two to drift apart.
_GANJAVE_CASCADE_ASSUMPTION: tuple[str, ...] = (
    "ganjave/initial_glycerol_concentration: "
    + next(
        rule.assumption
        for rule in _INPUT_CONTRACT
        if rule.port_id == "initial_glycerol_concentration"
    ),
)


#: The refusals that matter, keyed by (source model, target model), then by the
#: quantity pair they apply to. A quantity pair, not a port id: the rule is
#: about what the numbers mean, and the port list would go stale the moment a
#: model published a new one.
_GANJAVE_QUANTITY_REASONS: Mapping[tuple[str, str], tuple[str, str, str]] = {
    ("mass_concentration", "mass_concentration"): (
        "Ganjave's three concentrations are dry-cell weight, residual glycerol "
        "and a lumped complex substrate fitted as one number with one fitted "
        "yield. Zielinski's mass_concentration inputs are medium components "
        "(inoculum supplements, glucose targets, trypsin and aprotinin stocks) "
        "and its two reported culture loadings -- wet biomass at 56.0 g/L and "
        "inclusion bodies. No substance is shared, and dry-cell weight is not "
        "wet biomass: the two differ by a conversion factor neither paper "
        "prints.",
        "Ganjave et al. (2022) eq. (8)-(16) and Table 2; Zielinski et al. "
        "(2019) sec. 2-3, where wet biomass is a reported observation.",
        "A strain- and construct-matched model declaring the biomass basis on "
        "both sides.",
    ),
    ("volume", "volume"): (
        "Ganjave's culture_volume is the liquid working volume at the end of a "
        "24 h fed batch in a 3 L vessel, after feeding. Zielinski's volume "
        "ports are charges made at t = 0 (inoculum, starting medium, triton, "
        "citraconic anhydride), a nominal vessel volume, or chromatography "
        "elution volumes. A volume after 24 h of feeding is not a volume "
        "charged at the start of a different batch, and it differs from "
        "Zielinski's by more than an order of magnitude.",
        "Ganjave et al. (2022) sec. 3.1 (feeding begins at 6 h) and the "
        "published culture_volume output; Zielinski et al. (2019) sec. 2.1 "
        "(4 L starting medium in a 7.5 L fermenter).",
        "A vessel-scaled model that declares the working-volume relationship "
        "it is using, rather than transferring the raw number.",
    ),
    ("dimensionless", "dimensionless"): (
        "The contract has one dimensionless quantity and these models use it "
        "for at least four different things. Ganjave's dissolved_oxygen is a "
        "percentage of this probe's saturation reading in this medium (100 % is "
        "C* = 0.0075 g/L). Zielinski publishes optical densities, a refolding "
        "yield in per cent, an inclusion-body fraction, and a specific growth "
        "rate in 1/h that the contract cannot even unit. Nothing in a shared "
        "'dimensionless' label says which of those is meant.",
        "composition/composition/adapters/ganjave_contract.py::INPUT_CONTRACT "
        "on initial_dissolved_oxygen; Zielinski's own manifest, which declares "
        "one port per quantity with its unit and provenance.",
        "Distinct contract quantities, or a declared conversion carrying the "
        "missing calibration (C*, an OD600-to-DCW factor, a yield basis).",
    ),
    ("time", "time"): (
        "Ganjave's simulation_time is the horizon of one integration: 24 h, "
        "the whole fed batch. Zielinski's time ports are residence times of "
        "individual unit operations -- centrifugation in minutes, refolding in "
        "hours, induction. A batch horizon is not a step residence time, and "
        "v0.1 has no iterative solve, so the two could not be iterated to a "
        "consistent pair even if the clock were shared.",
        "Ganjave et al. (2022) eq. (12)-(16) over a declared duration_h; "
        "Zielinski et al. (2019) sec. 4, where each step carries its own time.",
        "A model that consumes a batch horizon and declares how it apportions "
        "it across steps.",
    ),
}


BOUNDARIES: tuple[Boundary, ...] = (
    Boundary(
        source_model=MORRIS, target_model=MORRIS,
        stance="permitted", permitted=True, enforced_by_engine=False,
        reason=(
            "Conservation across adjacent non-reacting control volumes is the "
            "premise the balance engine exists to apply. Both instances declare "
            "their components, the engine checks the sets agree, and the "
            "balance closes. This is the only boundary here that a published "
            "source directly supports, and the only one with a shipped example."
        ),
        evidence=EVIDENCE["morris"],
        remediation="Connect the ports the upstream instance publishes.",
    ),
    Boundary(
        source_model=MORRIS, target_model=GANJAVE,
        stance="no_shared_quantity", permitted=False, enforced_by_engine=False,
        reason=(
            MORRIS_NOT_A_CULTURE + " Independently of that, the two models share "
            "no quantity: Morris publishes mass and mass_fraction and accepts "
            "only mass, mass_flow, mass_fraction, amount and amount_flow, while "
            "Ganjave publishes mass_concentration, dimensionless, volume and "
            "time. There is no port pair to refuse."
        ),
        evidence=EVIDENCE["morris"] + EVIDENCE["ganjave"] + EVIDENCE["quantity"],
        dimensional_note=(
            "Morris quantities {mass, mass_flow, mass_fraction, amount, "
            "amount_flow} and Ganjave quantities {mass_concentration, "
            "dimensionless, volume, time, volume_flow} are disjoint."
        ),
        remediation=(
            "Nothing in this repository can connect them. A control volume for "
            "a fed-batch culture would need the component-resolved reaction "
            "model that does not exist here."
        ),
    ),
    Boundary(
        source_model=GANJAVE, target_model=MORRIS,
        stance="no_shared_quantity", permitted=False, enforced_by_engine=False,
        reason=(
            MORRIS_NOT_A_CULTURE + " The quantity vocabularies are disjoint in "
            "this direction too, so no connection is mechanically constructible "
            "even before the component rules are reached."
        ),
        evidence=EVIDENCE["morris"] + EVIDENCE["ganjave"] + EVIDENCE["quantity"],
        dimensional_note=(
            "Ganjave publishes no quantity Morris accepts."
        ),
        remediation=(
            "Same as the reverse direction: a reaction-aware, "
            "component-resolved culture model would have to exist first."
        ),
    ),
    Boundary(
        source_model=MORRIS, target_model=ZIELINSKI,
        stance="refused_component_identity", permitted=False, enforced_by_engine=True,
        reason=(
            "Zielinski publishes process roles, not conserved chemical "
            "entities: no stream of its own carries a component amount or a "
            "mass fraction. A Morris port either names a component (and the "
            "names will not agree) or is a control-volume total whose every "
            "entering unit must be attributable to one (and it is not). A "
            "Zielinski quantity forwarded into a Chapter 4 balance would "
            "therefore be relabelled as a component, which is an invented "
            "assumption that silently determines the answer."
        ),
        evidence=EVIDENCE["zielinski"] + EVIDENCE["morris"],
        remediation=(
            "Declare the component mapping explicitly, with a justification and "
            "a component definition, or do not connect the ports."
        ),
    ),
    Boundary(
        source_model=ZIELINSKI, target_model=MORRIS,
        stance="refused_component_identity", permitted=False, enforced_by_engine=True,
        reason=(
            "The same refusal from the other side, and a stronger one: Morris is "
            "a non-reacting control volume, so drawing a balance across a "
            "boundary whose model publishes neither component identity nor "
            "reaction terms is the case CG-09 names explicitly as numerically "
            "valid and physically wrong. Zielinski's own manifest declares "
            "component_identity unsupported, in those words."
        ),
        evidence=EVIDENCE["zielinski"] + EVIDENCE["morris"],
        remediation=(
            "Provide a non-reactive boundary with a declared component set, or "
            "a reaction-aware engine that can declare its reaction terms."
        ),
    ),
    Boundary(
        source_model=GANJAVE, target_model=ZIELINSKI,
        stance="refused_dimensional_only", permitted=False, enforced_by_engine=False,
        reason=_GANJAVE_TO_ZIELINSKI,
        evidence=EVIDENCE["ganjave"] + EVIDENCE["zielinski"],
        unresolved=(_RESOLVE_BY_COMPONENT,),
        remediation=(
            "Leave the ports unconnected and declare the value on the Zielinski "
            "instance instead, with its own source reference -- which is what "
            "the shipped examples already do."
        ),
        rules=tuple(_GANJAVE_QUANTITY_REASONS),
    ),
    Boundary(
        source_model=ZIELINSKI, target_model=GANJAVE,
        stance="refused_dimensional_only", permitted=False, enforced_by_engine=False,
        reason=_ZIELINSKI_TO_GANJAVE,
        evidence=EVIDENCE["zielinski"] + EVIDENCE["ganjave"],
        unresolved=(_RESOLVE_BY_COMPONENT,),
        remediation=(
            "Declare the value on the Ganjave instance instead. Ganjave's own "
            "contract already refuses two of its required inputs from any "
            "upstream model; this refuses the rest of the biological boundary."
        ),
        rules=tuple(_GANJAVE_QUANTITY_REASONS),
    ),
    Boundary(
        source_model=ZIELINSKI, target_model=ZIELINSKI,
        stance="refused_no_supplyable_port", permitted=False, enforced_by_engine=False,
        reason=(
            "Zielinski declares no port as supplyable by another instance, and "
            "that omission is deliberate: its ports are the operating "
            "conditions, measurements and transcribed values of a single "
            "reported experiment, and none of them is a stream another run "
            "could take. Two connected instances would both describe the same "
            "published batch, so the connection would assert a relationship "
            "between them that no source states -- not a transfer, and not a "
            "conservation check, since there is nothing to conserve."
        ),
        evidence=EVIDENCE["zielinski"],
        remediation=(
            "Run the graph once and let the model report its own cross-checks, "
            "which is what its five declared checks already do."
        ),
    ),
    Boundary(
        source_model=GANJAVE, target_model=GANJAVE,
        stance="permitted_forward_cascade", permitted=True, enforced_by_engine=False,
        reason=(
            "A forward cascade between two instances of the same model is a "
            "sequential use, not a fixed point: the second instance is ordered "
            "after the first and never feeds back, so nothing has to iterate. "
            "Ganjave's contract declares exactly one thing upstream-supplyable "
            "for this purpose -- initial_glycerol_concentration -- on the stated "
            "assumption that the upstream value is residual glycerol in this "
            "medium, and the project's own acceptance suite runs the cascade."
        ),
        evidence=EVIDENCE["ganjave"],
        unresolved=(
            "The cascade is permitted under the model's declared assumption, not "
            "validated by it: nothing in the paper seeds a second culture from "
            "the first. A run through it demonstrates that the software carries "
            "a quantity across the boundary, not that the resulting batch is "
            "the one the paper describes.",
        ),
        remediation=(
            "Connect the port the model's contract names. Two of Ganjave's "
            "required inputs accept no upstream model at all, and continue to "
            "refuse one here."
        ),
        assumptions=_GANJAVE_CASCADE_ASSUMPTION,
    ),
)


def boundary_for(source_model: str, target_model: str) -> Boundary | None:
    """The declared position between two models, or None if none is declared."""
    for boundary in BOUNDARIES:
        if boundary.source_model == source_model and boundary.target_model == target_model:
            return boundary
    return None


def check(
    source_model: str,
    source_port_id: str,
    source_quantity: str,
    target_model: str,
    target_port_id: str,
    target_quantity: str,
) -> Verdict | None:
    """The standing of one proposed connection.

    Returns ``None`` when the engine's own mechanical rules own this boundary,
    or when no policy is declared for it -- in both cases this module has
    nothing to add, and saying so is better than inventing a reason.

    The port ids are accepted and not used for the decision: the rules are about
    what the numbers *mean*, and keying them on port ids would make them go
    stale the first time a model published a new port. They appear in the
    message so a reader can see which pair was judged.
    """
    boundary = boundary_for(source_model, target_model)
    if boundary is None or boundary.enforced_by_engine:
        return None

    pair = (source_quantity, target_quantity)
    detail = _GANJAVE_QUANTITY_REASONS.get(pair) if boundary.rules else None

    if boundary.source_model == boundary.target_model:
        # Same model on both sides. Permitted only where a source supports it --
        # which is not "automatically fine", it is a per-boundary decision.
        return Verdict(
            source_model=source_model, target_model=target_model,
            quantity_pair=pair, permitted=boundary.permitted,
            stance=boundary.stance, reason=boundary.reason,
            evidence=boundary.evidence, unresolved=boundary.unresolved,
            remediation=boundary.remediation,
            evidence_basis="permitted" if boundary.permitted else "documented_incompatibility",
            assumptions=boundary.assumptions,
        )

    if detail is None:
        # Dimensional candidates between these two models that no rule names.
        # Refusing without a reason would be the thing this module exists to
        # avoid -- but note what this refusal is *not*: it is not a claim that
        # the quantities are physically incompatible. It is a claim that nobody
        # has written down whether they are. `evidence_limited` says so, and a
        # report must carry that through rather than presenting an absence of
        # evidence as evidence of absence.
        return Verdict(
            source_model=source_model, target_model=target_model,
            quantity_pair=pair, permitted=False, stance="refused_unclassified",
            reason=(
                "No rule in composition/composition/cross_model.py classifies a "
                f"{source_quantity} -> {target_quantity} connection between "
                f"{source_model} and {target_model}. The connection is not "
                "permitted, because an unclassified pair is refused rather than "
                "passed through unexamined. This is an absence of a documented "
                "judgement, not a documented finding that the two quantities are "
                "physically incompatible."
            ),
            evidence=boundary.evidence,
            unresolved=(boundary.reason,),
            remediation=(
                "Add the rule before connecting ports like these, or declare "
                "the value on the instance instead."
            ),
            evidence_basis="evidence_limited",
        )

    reason, evidence, unresolved = detail
    return Verdict(
        source_model=source_model, target_model=target_model,
        quantity_pair=pair, permitted=False,
        stance="%s:%s" % (boundary.stance, source_quantity),
        # The engine already names both ports and the quantity pair in its own
        # message, so the reason starts with the science rather than repeating
        # the address.
        reason=f"{reason} {boundary.reason}",
        evidence=boundary.evidence + (evidence,),
        unresolved=boundary.unresolved + (unresolved,),
        remediation=boundary.remediation,
    )


def matrix() -> list[dict[str, object]]:
    """Every declared boundary, as plain data, for inspection."""
    return [_boundary_dict(b) for b in BOUNDARIES]


def _boundary_dict(boundary: Boundary) -> dict[str, object]:
    return {
        "source_model": boundary.source_model,
        "target_model": boundary.target_model,
        "stance": boundary.stance,
        "permitted": boundary.permitted,
        "enforced_by_engine": boundary.enforced_by_engine,
        "reason": boundary.reason,
        "evidence": list(boundary.evidence),
        "unresolved": list(boundary.unresolved),
        "remediation": boundary.remediation,
        "quantity_pairs": [list(pair) for pair in boundary.rules],
        "dimensional_note": boundary.dimensional_note,
        "assumptions": list(boundary.assumptions),
        "evidence_basis": boundary.evidence_basis,
    }


def describe() -> dict[str, object]:
    """The whole cross-model position, as one inspectable document."""
    return {
        "contract_version": "0.1.0",
        "claim_scope": (
            "A connection is judged on dimensional compatibility, semantic "
            "compatibility, organism/strain/process context, the initial and "
            "operating conditions each model requires, the evidence supporting "
            "the relationship, and what remains unresolved. A matching unit is "
            "necessary and never sufficient."
        ),
        "validation_status": (
            "This is a composition-side assessment of interfaces. It is not a "
            "scientific validation of any model, and running these checks does "
            "not upgrade any model's reproduction_status."
        ),
        "boundaries": matrix(),
        "quantity_pairs_examined": sorted(
            pair for boundary in BOUNDARIES for pair in boundary.rules
        ),
    }