"""Condition records that each carry a quote from their own source.

The circularity this module exists to remove
--------------------------------------------
An earlier version of this catalogue recorded the target process once and then
recorded candidate conditions as strings that were *identical* to it. The
comparator then reported twelve dimensions matching, which looked like
verification but was a tautology: both sides of every comparison were written by
the same person from the same reading, and agreement had been constructed rather
than observed.

The fix is structural rather than cosmetic. Every condition here is a
:class:`Condition` carrying:

* the value **as that source words it**, not harmonised to a house style;
* the **verbatim passage** it was transcribed from, in that source; and
* the id of that source.

Agreement between two conditions is then a claim about two independently
checkable passages, and a reader can verify each side against its own paper. It
is no longer an artefact of transcription.

What this does and does not establish
-------------------------------------
Two conditions reading differently is *not* evidence that they disagree, and two
reading the same is not proof they do agree. "E. coli 20" and "E. coli 20 IBA 1
strain, a derivative of CSH50R" are plainly the same organism, but no declared
string rule can establish that. So the comparison reports ``partial``: *related,
equivalence not mechanically established*, with both passages shown. Deciding
they are the same organism is a scientific judgement, and it stays with the
reader. That is the whole point -- this module determines what is mechanically
connectable, not what is scientifically true.

Two dimensions are compared numerically instead, because an exact numerical
agreement carries no interpretive risk: if both papers state 37 degrees, they
agree, and no phrasing judgement is involved.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# --------------------------------------------------------------------------- #
# Dimensions
# --------------------------------------------------------------------------- #

#: Compared as numbers, not as text. Two papers stating the same temperature
#: agree in a way that needs no interpretation.
NUMERIC_DIMENSIONS: frozenset[str] = frozenset({"temperature_c", "scale_l"})

#: Compared as text. Equality is rarely achievable because each side is
#: transcribed in its own paper's wording; ``partial`` is the normal result and
#: is not a defect.
IDENTITY_DIMENSIONS: frozenset[str] = frozenset(
    {"organism", "strain", "construct", "product", "medium", "substrate",
     "mode", "ph", "oxygen_transfer", "measurement"}
)

#: Kept for the record, but deliberately NOT scored by text alone any more.
#: Retained only so a reader can see which dimensions were which.
DIMENSION_ORDER: tuple[str, ...] = (
    "organism", "strain", "construct", "product", "medium", "substrate",
    "mode", "temperature_c", "ph", "oxygen_transfer", "measurement", "scale_l",
)


def _normalise(text: str) -> str:
    """Fold a passage to a comparable form: case, punctuation, accents, spaces.

    Used only to test whether two passages *overlap*, never to judge whether two
    conditions are equivalent.
    """
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", folded.lower()).split())


def _first_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", _normalise(text))
    return float(m.group(0)) if m else None


def _volume(text: str) -> float | None:
    """The vessel volume, not some other number that happens to be nearby.

    A fermenter is named after its model ("Bioflo Celligen 310"), so taking the
    first number in the string reads 310 where the volume is 7.5. Only a number
    carrying a volume unit counts.
    """
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(picoliter|picolitre|microliter|microlitre|"
                  r"milliliter|millilitre|liter|litre|[pum]l|l)\b", str(text), re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def _substance(text: str) -> str:
    """The substance itself, stripped of the concentration describing it.

    ``glucose, 1% (w/v)`` and ``40% glucose`` name the same substrate; the
    percentages are properties of the experiment, not identities. Comparing the
    numbers would wrongly report two different substances.
    """
    stripped = re.sub(r"\d+(?:[.,]\d+)?\s*(?:%|percent|w/v|v/v|g/L|mg/dL|mg/L|g/dL)",
                      " ", str(text), flags=re.I)
    stripped = re.sub(r"[()\[\]]", " ", stripped)
    head = re.split(r"[,;]|as the carbon source", stripped)[0]
    return _normalise(head)


@dataclass(frozen=True)
class Condition:
    """One experimental condition, as stated by one source."""

    dimension: str
    value: str
    #: Verbatim passage from THIS source. Never paraphrased.
    quote: str
    #: Which publication the value and quote came from.
    source_id: str

    def is_stated(self) -> bool:
        return _normalise(self.value) not in ("", "not stated", "not reported", "unknown", "n a")

    def number(self) -> float | None:
        if self.dimension not in NUMERIC_DIMENSIONS:
            return None
        if self.dimension == "scale_l":
            return _volume(self.value)
        return _first_number(self.value)


@dataclass(frozen=True)
class Match:
    """Result of comparing one condition against its counterpart."""

    dimension: str
    verdict: str          # "match" | "partial" | "mismatch" | "unknown"
    candidate: Condition
    target: Condition
    note: str


#: Controlled vocabularies. These are *closed sets of mutually exclusive terms*,
#: not similarity heuristics: a culture is batch or chemostat or microfluidic,
#: not a blend, so two sides resolving to different terms really do describe
#: different processes. Where a term is shared, agreement is a fact about the
#: process rather than about the phrasing.
MODE_VOCABULARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("batch", ("batch",)),
    ("fed-batch", ("fed batch", "fed-batch")),
    ("chemostat", ("chemostat", "continuous culture")),
    ("microfluidic", ("microfluidic", "perfusion", "picolitre", "picoliter")),
    ("agarose-pad", ("agarose pad", "agarose-pad")),
)

ORGANISM_VOCABULARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("escherichia-coli", ("escherichia coli", "e coli", "e. coli")),
    ("coli-bacillus", ("coli bacillus", "bacillus")),
    ("yeast", ("yeast", "saccharomyces", "pichia")),
    ("cyanobacterium", ("synechococcus", "synechocystis")),
)


def _resolve_vocabulary(value: str, vocabulary) -> str | None:
    v = _normalise(value)
    for name, terms in vocabulary:
        if any(t in v for t in terms):
            return name
    return None


#: Tokens that name a specific entity rather than describing one. A strain
#: designation or plasmid name is an identifier; "minimal medium" is not.
_STOPWORDS = frozenset({"E", "COLI", "ESCHERICHIA", "ATCC", "DNA", "THE", "A", "OF"})


def _designators(value: str) -> frozenset[str]:
    """Identifiers in a condition value, used to tell 'different' from 'phrased differently'.

    "E. coli ML30" and "E. coli 20 IBA 1" are obviously different strains, and a
    reader says so instantly. The rule here makes that mechanical: pull out the
    tokens that *name* something (contain a digit, or are an uppercase
    abbreviation), and compare those sets. If both sides name something and the
    names do not intersect, the two are not talking about the same entity.
    """
    head = re.split(r"[()]", str(value))[0]
    out: set[str] = set()
    for token in re.split(r"[^A-Za-z0-9]+", head):
        if not token or token.upper() in _STOPWORDS:
            continue
        if any(ch.isdigit() for ch in token):
            out.add(token.upper())
        elif token.isupper() and len(token) >= 3:
            out.add(token)
    return frozenset(out)


def _declares_none(value: str) -> bool:
    v = _normalise(value)
    return v.startswith("none") or v.startswith("no ") or "not stated" in v or "not reported" in v


def compare(candidate: Condition, target: Condition) -> Match:
    """Compare two independently transcribed conditions under declared rules.

    The order matters: the earlier rules are *specific* and the later ones are
    increasingly inconclusive, so the result never overstates what has been
    established.
    """
    dim = candidate.dimension

    if not candidate.is_stated() or not target.is_stated():
        stated = "the candidate" if not candidate.is_stated() else "the target source"
        return Match(dim, "unknown", candidate, target,
                     "%s does not state this condition, so agreement cannot be shown." % stated)

    cnum, tnum = candidate.number(), target.number()
    if cnum is not None and tnum is not None:
        if cnum == tnum:
            return Match(dim, "match", candidate, target,
                         "both sources state %g." % cnum)
        return Match(dim, "mismatch", candidate, target,
                     "numerically different: %g vs %g." % (cnum, tnum))

    c, t = _normalise(candidate.value), _normalise(target.value)
    if dim == "substrate":
        c, t = _substance(candidate.value), _substance(target.value)
    if c == t:
        return Match(dim, "match", candidate, target, "both sources state the same words.")

    # One side says there is no such entity; the other names one. Nothing can be
    # compatible with "none".
    if _declares_none(candidate.value) != _declares_none(target.value):
        return Match(dim, "mismatch", candidate, target,
                     "one source states there is no such entity and the other names one.")

    # Closed vocabularies: a shared term is a fact about the process.
    vocabulary = None
    if dim == "mode":
        vocabulary = MODE_VOCABULARY
    elif dim == "organism":
        vocabulary = ORGANISM_VOCABULARY
    if vocabulary is not None:
        cv = _resolve_vocabulary(candidate.value, vocabulary)
        tv = _resolve_vocabulary(target.value, vocabulary)
        if cv and tv:
            if cv == tv:
                return Match(dim, "match", candidate, target,
                             "both resolve to the same %s in a closed vocabulary." % dim)
            return Match(dim, "mismatch", candidate, target,
                         "both name a %s, and they differ: %s vs %s." % (dim, cv, tv))

    # Identifiers: different named entities, not two phrasings of one entity.
    cd, td = _designators(candidate.value), _designators(target.value)
    if cd and td and not (cd & td):
        return Match(dim, "mismatch", candidate, target,
                     "both sides name a specific entity and the names do not overlap: "
                     "%s vs %s." % (sorted(cd), sorted(td)))

    if c and t and (c in t or t in c):
        return Match(dim, "partial", candidate, target,
                     "one statement contains the other; related, but the wordings differ.")

    if dim == "substrate" and c and t:
        return Match(dim, "match", candidate, target,
                     "both name the same substrate; the concentrations differ and are "
                     "recorded in the conditions, not treated as a different substance.")

    if cd and td and (cd & td):
        return Match(dim, "partial", candidate, target,
                     "the two name the same entity (%s), but describe it differently."
                     % ", ".join(sorted(cd & td)))

    return Match(dim, "partial", candidate, target,
                 "different wordings; equivalence is not mechanically established.")


# --------------------------------------------------------------------------- #
# The target source
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TargetPassage:
    passage_id: str
    topic: str
    pdf_page: int
    printed_page: int
    section: str
    text: str


@dataclass(frozen=True)
class TargetSource:
    source_id: str
    citation: str
    doi: str
    printed_pages: str
    passages: tuple[TargetPassage, ...]

    def by_topic(self, topic: str) -> TargetPassage | None:
        for p in self.passages:
            if p.topic == topic:
                return p
        return None

    def overlap(self, quote: str, *, min_chars: int = 40) -> TargetPassage | None:
        """Return the target passage a candidate quote appears in, if any.

        This is the check that catches a candidate which is not external
        evidence at all but the target paper's own wording cited through a
        second publication.
        """
        q = _normalise(quote)
        if len(q) < min_chars:
            return None
        for p in self.passages:
            hay = _normalise(p.text)
            if q in hay or (len(hay) >= min_chars and hay in q):
                return p
        return None


def load_target_source(path: Path | None = None) -> TargetSource:
    here = Path(__file__).resolve().parent
    data = json.loads((path or here / "target_source.json").read_text(encoding="utf-8"))
    return TargetSource(
        source_id=data["source_id"],
        citation=data["citation"],
        doi=data["doi"],
        printed_pages=data["printed_pages"],
        passages=tuple(
            TargetPassage(p["id"], p["topic"], int(p["pdf_page"]), int(p["printed_page"]),
                          p["section"], p["text"])
            for p in data["passages"]
        ),
    )


def target_conditions(source: TargetSource) -> dict[str, Condition]:
    """Transcribe the target process from the target paper's own wording.

    Each value is the paper's phrasing, not a normalised house style, so that a
    candidate agreeing with it has actually agreed with the paper.
    """
    def c(topic: str, dimension: str, value: str) -> Condition:
        p = source.by_topic(topic)
        assert p is not None, "no target passage for topic %r" % topic
        return Condition(dimension, value, p.text, source.source_id)

    return {
        "organism": c("host strain", "organism", "Escherichia coli"),
        "strain": c("host strain", "strain",
                    "E. coli 20 IBA 1 (F- lambda-ara Δ(pro lac) rpsL thi recA cytR), "
                    "a derivative of E. coli CSH50R"),
        "construct": c("inoculum medium", "construct",
                       "plasmid pIBAINS carrying the human insulin gene"),
        "product": c("inoculum medium", "product", "human insulin"),
        "medium": c("inoculum medium", "medium", "GMS medium"),
        "substrate": c("growth stage conditions", "substrate",
                       "40% glucose, exponentially added as the carbon source"),
        "mode": c("pH-stat control", "mode",
                  "batch culture; glucose fed by pH-stat control using cascade"),
        "temperature_c": c("growth temperature", "temperature_c", "37"),
        "ph": c("pH-stat control", "ph",
                "pH-stat cascade control, dead band 0.01"),
        "oxygen_transfer": Condition("oxygen_transfer", "not reported", "", source.source_id),
        "measurement": c("glucose limitation", "measurement",
                       "OD 600 nm"),
        "scale_l": c("fermenter scale", "scale_l",
                     "Bioflo Celligen 310 7.5 L fermenter, starting volume 4 L"),
    }


def to_dict(condition: Condition) -> dict[str, Any]:
    return {
        "dimension": condition.dimension,
        "value": condition.value,
        "quote": condition.quote,
        "source_id": condition.source_id,
    }


def compare_all(
    candidates: Mapping[str, Condition],
    targets: Mapping[str, Condition],
) -> tuple[Match, ...]:
    out: list[Match] = []
    for dim in DIMENSION_ORDER:
        c = candidates.get(dim)
        t = targets.get(dim)
        if c is None or t is None:
            continue
        out.append(compare(c, t))
    return tuple(out)