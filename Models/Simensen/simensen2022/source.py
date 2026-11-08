"""Bibliographic source and evidence helpers for Simensen et al. (2022).

**The printed page equals the PDF page for this article.** It was published as
*PLOS ONE* 17(1): e0262450 with page footers of the form ``1 / 17``, ``2 / 17``
... and no separate journal pagination, so a printed page and the 1-based PDF
page are the same integer. The footers are asserted against the extracted page
text by the test suite.

``paper_pages()`` holds the extracted text of every page so a citation can be
*checked* rather than trusted. The PDF is a publication by other authors and is
not read at run time. Regenerate with

    python -c "from simensen2022.source import rebuild_paper_pages; rebuild_paper_pages()"

run from ``Models/Simensen``, which needs pypdf.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SOURCE_ID = "simensen2022"

AUTHORS = (
    "Vetle Simensen",
    "Christian Schulz",
    "Emil Karlsen",
    "Signe Bratelund",
    "Idun Burgos",
    "Lilja Brekke Thorfinnsdottir",
    "Laura Garcia-Calvo",
    "Per Bruheim",
    "Eivind Almaas",
)

TITLE = (
    "Experimental determination of Escherichia coli biomass composition for "
    "constraint-based metabolic modeling"
)

JOURNAL = "PLOS ONE"
YEAR = 2022
VOLUME = "17"
ISSUE = "1"
ARTICLE_NUMBER = "e0262450"
PAGES = "1-17"
DOI = "10.1371/journal.pone.0262450"

CITATION = (
    "V. Simensen, C. Schulz, E. Karlsen, S. Bratelund, I. Burgos, L. B. "
    "Thorfinnsdottir, L. Garcia-Calvo, P. Bruheim, E. Almaas, 'Experimental "
    "determination of Escherichia coli biomass composition for constraint-based "
    "metabolic modeling', PLOS ONE 17(1):e0262450, 2022."
)

#: The article is paginated 1-17 and the PDF reproduces those numbers.
FIRST_PRINTED_PAGE = 1
PAGE_COUNT = 17
LAST_PRINTED_PAGE = FIRST_PRINTED_PAGE + PAGE_COUNT - 1

#: Every page carries a footer of the form "N / 17".
FOOTER_TEMPLATE = "%d / %d"

DATA_DIR = Path(__file__).parent / "data"


def pdf_page(printed_page: int) -> int:
    """1-based PDF page holding `printed_page` (the same integer here)."""
    return printed_page - FIRST_PRINTED_PAGE + 1


def printed_page_of(pdf_page_number: int) -> int:
    """Printed page number of a 1-based PDF page."""
    return pdf_page_number + FIRST_PRINTED_PAGE - 1


def footer_for(printed_page: int) -> str:
    return FOOTER_TEMPLATE % (printed_page, PAGE_COUNT)


def citation_for(printed_page: int, *, section: str | None = None) -> str:
    bits = [CITATION.rstrip("."), f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def reference(printed_page: int, *, section: str | None = None) -> str:
    bits = ["Simensen et al. 2022", f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


@lru_cache(maxsize=1)
def paper_pages() -> dict[int, str]:
    """Extracted text of each PDF page, keyed by 1-based PDF page."""
    path = DATA_DIR / "paper_pages.json"
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def page_text(printed_page: int) -> str:
    """Normalised text of one printed page, or '' when it is not extracted."""
    return paper_pages().get(pdf_page(printed_page), "")


def normalise(text: str) -> str:
    """Fold a page of extracted text into the form citations are checked in."""
    text = unicodedata.normalize("NFKD", text)
    for src, dst in (
        ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
        ("\u2010", "-"), ("\u2011", "-"), ("\u2013", "-"), ("\u2014", "-"),
        ("\u00a0", " "), ("\u2212", "-"),
    ):
        text = text.replace(src, dst)
    text = text.replace(",", "")
    return re.sub(r"\s+", " ", text)


def _loose(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", text)


def page_contains(printed_page: int, fragment: str) -> bool:
    """True when `fragment` appears on the printed page, verbatim or nearly."""
    page = page_text(printed_page)
    if not page:
        return False
    if fragment in page:
        return True
    return _loose(fragment) in _loose(page)


def page_states_its_own_number(printed_page: int) -> bool:
    """True when the page prints its own footer ``N / 17``."""
    page = page_text(printed_page)
    if not page:
        return False
    return f"{printed_page} / {PAGE_COUNT}" in page or f"{printed_page}/{PAGE_COUNT}" in page


def resolve_source_pdf() -> Path:
    """The article PDF to regenerate page text from."""
    local = sorted((DATA_DIR.parent.parent).glob("*.pdf"))
    if local:
        return local[0]
    raise FileNotFoundError(
        "no article PDF beside the package; put the paper back at "
        f"{DATA_DIR.parent.parent}"
    )


def rebuild_paper_pages(
    pdf_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[int, str]:
    """Re-extract page text from the article PDF (needs pypdf; developer step)."""
    from pypdf import PdfReader

    if pdf_path is None:
        pdf_path = resolve_source_pdf()
    reader = PdfReader(str(Path(pdf_path)))
    pages = {
        i: normalise(page.extract_text() or "")
        for i, page in enumerate(reader.pages, 1)
    }
    out = Path(output_path) if output_path is not None else DATA_DIR / "paper_pages.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump({str(k): v for k, v in pages.items()}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return pages
