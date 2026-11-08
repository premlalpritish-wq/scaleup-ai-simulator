"""Bibliographic source and evidence helpers for Nanchen, Schicker & Sauer (2006).

**The printed page is not the PDF page.** The article appeared as *Applied and
Environmental Microbiology*, Feb. 2006, Vol. 72, No. 2, pp. 1164-1172, and the
PDF reproduces those page numbers in a running footer that states its own
number, so ``pdf_page = printed_page - 1163``. The footers are asserted against
the extracted page text by the test suite, so the arithmetic is checked.

``paper_pages()`` holds the extracted text of every page so a citation can be
*checked* rather than trusted. The PDF is a publication by other authors and is
not read at run time. Regenerate with

    python -c "from nanchen2006.source import rebuild_paper_pages; rebuild_paper_pages()"

run from ``Models/nanchen``, which needs pypdf.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SOURCE_ID = "nanchen2006"

AUTHORS = ("Annik Nanchen", "Alexander Schicker", "Uwe Sauer")

TITLE = (
    "Nonlinear Dependency of Intracellular Fluxes on Growth Rate in "
    "Miniaturized Continuous Cultures of Escherichia coli"
)

JOURNAL = "Applied and Environmental Microbiology"
YEAR = 2006
VOLUME = "72"
ISSUE = "2"
PAGES = "1164-1172"
DOI = "10.1128/AEM.72.2.1164-1172.2006"

CITATION = (
    "A. Nanchen, A. Schicker, U. Sauer, 'Nonlinear Dependency of Intracellular "
    "Fluxes on Growth Rate in Miniaturized Continuous Cultures of Escherichia "
    "coli', Applied and Environmental Microbiology 72(2):1164-1172, 2006."
)

#: The article is paginated 1164-1172 and the PDF reproduces those numbers, so
#: printed and 1-based PDF pages differ by a fixed offset.
FIRST_PRINTED_PAGE = 1164
PAGE_COUNT = 9
LAST_PRINTED_PAGE = FIRST_PRINTED_PAGE + PAGE_COUNT - 1

#: Every page carries a running footer whose integers include the printed page.
FOOTER_HEAD = "GROWTH RATE DEPENDENCE OF METABOLIC FLUXES"

DATA_DIR = Path(__file__).parent / "data"


def pdf_page(printed_page: int) -> int:
    """1-based PDF page holding `printed_page`."""
    return printed_page - FIRST_PRINTED_PAGE + 1


def printed_page_of(pdf_page_number: int) -> int:
    """Printed page number of a 1-based PDF page."""
    return pdf_page_number + FIRST_PRINTED_PAGE - 1


def citation_for(printed_page: int, *, section: str | None = None) -> str:
    bits = [CITATION.rstrip("."), f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def reference(printed_page: int, *, section: str | None = None) -> str:
    bits = ["Nanchen et al. 2006", f"p. {printed_page}"]
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
    """True when the page prints its own number at the head or foot of its text."""
    page = page_text(printed_page)
    if not page:
        return False
    needle = str(printed_page)
    return needle in page[:80] or needle in page[-160:]


# --------------------------------------------------------------------------- #
# locating the article PDF (regeneration only; never read by the model)
# --------------------------------------------------------------------------- #


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
