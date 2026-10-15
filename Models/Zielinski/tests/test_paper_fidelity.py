"""Citation fidelity: every reported value must actually appear on its cited page.

This is the mechanical form of "a reviewer can trace every reported number to the
paper". The extracted page text lives in `models/data/paper_pages.json`; regenerate
it from the PDF with `models.source.rebuild_paper_pages()`.
"""

from __future__ import annotations

import re

from scaleup_ai import Provenance

from models.source import paper_pages

#: the PDF prints "15,000 x g"; thousands separators are stripped on extraction
NUMBERS_IN_TEXT = re.compile(r"\d+(?:\.\d+)?")


def _candidates(value: float) -> set[str]:
    """String forms a value may legitimately take in the paper's typesetting."""
    out: set[str] = set()
    for text in (f"{value:g}", f"{value:.1f}", f"{value:.2f}", f"{value:.0f}"):
        out.add(text)
        if "." in text:
            out.add(text.rstrip("0").rstrip("."))
    # 99 is printed as "99%" but also as part of "7-8"; tolerate both signs
    return {c for c in out if c}


def test_paper_pages_cover_the_whole_article():
    pages = paper_pages()
    assert sorted(pages) == [1, 2, 3, 4, 5, 6, 7]
    for page, text in pages.items():
        assert len(text) > 500, f"page {page} text looks truncated"


def test_every_reported_scalar_appears_on_its_cited_page(graph):
    pages = paper_pages()
    checked, missing = 0, []
    for location, qid, q in graph.iter_quantities():
        if q.provenance is not Provenance.REPORTED or q.value is None:
            continue
        ref = q.evidence[0]
        text = pages[ref.pdf_page]
        checked += 1
        if not any(c in text for c in _candidates(q.value)):
            missing.append(f"{location}:{qid}={q.value}{q.unit} -> p.{ref.printed_page}")
    assert not missing, "reported values not found on their cited page:\n" + "\n".join(missing)
    assert checked >= 120


def test_every_reported_range_matches_its_cited_page(graph):
    pages = paper_pages()
    ranges = [
        (location, qid, q)
        for location, qid, q in graph.iter_quantities()
        if q.provenance is Provenance.REPORTED and q.value_range is not None
    ]
    assert ranges
    for location, qid, q in ranges:
        lo, hi = q.value_range
        text = pages[q.evidence[0].pdf_page]
        assert any(c in text for c in _candidates(lo)), f"{location}:{qid} lower bound"
        assert any(c in text for c in _candidates(hi)), f"{location}:{qid} upper bound"


def test_source_expression_numbers_appear_on_their_cited_page(graph):
    """Every number printed in a preserved formula must be on the cited page."""
    pages = paper_pages()
    seen = 0
    for node in graph.nodes:
        for expr in node.source_expressions:
            text = pages[expr.evidence[0].pdf_page]
            for number in NUMBERS_IN_TEXT.findall(expr.expression_text):
                assert number in text, (
                    f"{expr.expression_id}: number {number!r} from "
                    f"{expr.expression_text!r} not on p.{expr.evidence[0].printed_page}"
                )
                seen += 1
    assert seen >= 15


def test_source_expression_subjects_appear_on_their_cited_page(graph):
    pages = paper_pages()
    subjects = {
        "E-ZNCL2": "zinc chloride",
        "E-WATER": "protein obtained after DEAE",
        "E-EDTA": "EDTA",
        "E-CITRACONYLATION-ANHYDRIDE": "citraconic anhydride",
        "E-TRYPSIN": "trypsin",
        "E-ETHANOLAMINE": "ethanolamine",
        "E-APROTININ": "aprotinin",
        "E-CPB": "carboxypeptidase B",
    }
    found = 0
    for node in graph.nodes:
        for expr in node.source_expressions:
            needle = subjects.get(expr.expression_id)
            assert needle, f"no subject recorded for {expr.expression_id}"
            assert needle.lower() in pages[expr.evidence[0].pdf_page].lower(), expr.expression_id
            found += 1
    assert found == len(subjects)


def test_original_text_quotes_are_grounded_in_the_paper(graph):
    """Verbatim `original_text` fragments must really occur in the article."""
    pages = paper_pages()
    checked = 0
    for location, qid, q in graph.iter_quantities():
        if not q.original_text:
            continue
        ref = q.evidence[0]
        needle = re.sub(r"\s+", " ", q.original_text).strip()
        # quotes are transcribed with ASCII substitutions (x, uL, degrees); compare
        # on a reduced form so typography does not cause false failures
        haystack = pages[ref.pdf_page]
        reduced_needle = (
            needle.replace("×", "x").replace("μ", "u").replace("°", "").replace(",", "")
        )
        reduced_hay = (
            haystack.replace("×", "x").replace("μ", "u").replace("°", "").replace(",", "")
        )
        # the PDF renders subscripts and superscripts with a stray space
        # ("16% NH 4OH"), so fall back to a fully de-spaced comparison
        despaced = re.sub(r"\s+", "", reduced_hay)
        tokens = [t for t in re.split(r"[ ]", reduced_needle) if len(t) > 3]
        hits = sum(1 for t in tokens if t in reduced_hay or t in despaced)
        assert hits / max(1, len(tokens)) >= 0.6, (
            f"{location}:{qid} quote not grounded in p.{ref.printed_page}: {needle!r}"
        )
        checked += 1
    assert checked >= 50