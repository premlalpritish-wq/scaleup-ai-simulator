"""Bibliographic source and evidence helpers for Lin et al. (2001).

One publication, cited once, with the printed page for every value.

**The printed page is not the PDF page for this article.** It appeared as
``Biotechnology and Bioengineering, Vol. 73, No. 5, June 5, 2001, pp. 347-357``
and the PDF reproduces those page numbers in a running footer
(``348   BIOTECHNOLOGY AND BIOENGINEERING, VOL. 73, NO. 5, JUNE 5, 2001``), so a
printed page maps to a PDF page by arithmetic rather than by assumption:
``pdf_page = printed_page - 346``. The footer is asserted against the extracted
page text in the test suite, so the arithmetic is checked, not trusted.

``paper_pages()`` holds the extracted text of every page so that a citation can
be *checked* rather than trusted. The PDFs under ``Models/`` are publications by
other authors and are deliberately not read at run time; only this extracted
text is. Regenerate with

    python -c "from lin2000.source import rebuild_paper_pages; rebuild_paper_pages()"

run from ``Models/Lin``, which needs pypdf and is never called by the model.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SOURCE_ID = "lin2000"

AUTHORS = (
    "H. Y. Lin",
    "B. Mathiszik",
    "B. Xu",
    "S.-O. Enfors",
    "P. Neubauer",
)

TITLE = (
    "Determination of the Maximum Specific Uptake Capacities for Glucose and "
    "Oxygen in Glucose-Limited Fed-Batch Cultivations of Escherichia coli"
)

JOURNAL = "Biotechnology and Bioengineering"
YEAR = 2001
VOLUME = "73"
ISSUE = "5"
PAGES = "347-357"
DOI = "10.1002/bit.1078"

CITATION = (
    "H. Y. Lin, B. Mathiszik, B. Xu, S.-O. Enfors, P. Neubauer, 'Determination "
    "of the Maximum Specific Uptake Capacities for Glucose and Oxygen in "
    "Glucose-Limited Fed-Batch Cultivations of Escherichia coli', "
    "Biotechnology and Bioengineering 73(5):347-357, 2001."
)

#: The article is paginated 347-357; the PDF reproduces those numbers, so the
#: printed page and the 1-based PDF page differ by a fixed offset.
FIRST_PRINTED_PAGE = 347
PAGE_COUNT = 11
LAST_PRINTED_PAGE = FIRST_PRINTED_PAGE + PAGE_COUNT - 1

#: Every page from 348 onwards carries a footer whose leading integer is the
#: printed page number, followed by the running head.
FOOTER_HEAD = "BIOTECHNOLOGY AND BIOENGINEERING, VOL. 73, NO. 5, JUNE 5, 2001"

DATA_DIR = Path(__file__).parent / "data"


def pdf_page(printed_page: int) -> int:
    """1-based PDF page holding `printed_page`."""
    return printed_page - FIRST_PRINTED_PAGE + 1


def printed_page_of(pdf_page_number: int) -> int:
    """Printed page number of a 1-based PDF page."""
    return pdf_page_number + FIRST_PRINTED_PAGE - 1


def citation_for(printed_page: int, *, section: str | None = None) -> str:
    """The citation string used on every record, page-qualified."""
    bits = [CITATION.rstrip("."), f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def reference(printed_page: int, *, section: str | None = None) -> str:
    """Short form used where a full citation would be redundant."""
    bits = ["Lin et al. 2001", f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def footer_for(printed_page: int) -> str:
    """The running head this article prints in the footer of `printed_page`.

    Odd (recto) pages put the printed page number before the head
    (``348   BIOTECHNOLOGY AND BIOENGINEERING, ...``); even (verso) pages put it
    after (``LIN ET AL.: UPTAKE CAPACITIES FOR GLUCOSE AND OXYGEN   355``). Page
    347, the opening page, carries no footer.
    """
    return f"{printed_page}   {FOOTER_HEAD}"


def page_states_its_own_number(printed_page: int) -> bool:
    """True when the page prints its own number at the head or foot of the column.

    The opening page carries no footer, so it returns False by design.
    """
    if printed_page == FIRST_PRINTED_PAGE:
        return False
    page = page_text(printed_page)
    if not page:
        return False
    needle = str(printed_page)
    return needle in page[:80] or needle in page[-160:]


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
    """Fold a page of extracted text into the form citations are checked in.

    Unicode decomposition, the typesetter's thousands separators and the
    printed minus/en-dash are removed, and whitespace is collapsed so a line
    break in the PDF column is not a difference.
    """
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
    """Reduce text to its alphanumeric characters, for hyphen-tolerant matching."""
    return re.sub(r"[^0-9A-Za-z]", "", text)


def page_contains(printed_page: int, fragment: str) -> bool:
    """True when `fragment` appears on the printed page, verbatim or nearly.

    A strict substring match on the normalised page text is tried first; if it
    fails the comparison is retried with punctuation and spaces removed, which
    is what a typesetter's line-end hyphenation needs. Reported *values* are
    always checked strictly by the test suite.
    """
    page = page_text(printed_page)
    if not page:
        return False
    if fragment in page:
        return True
    return _loose(fragment) in _loose(page)


# --------------------------------------------------------------------------- #
# locating the article PDF (regeneration only; never read by the model)
# --------------------------------------------------------------------------- #

PDF_FILENAME = "Lin et al 2000.pdf"


class SourcePdfNotFound(FileNotFoundError):
    """No copy of the article PDF could be located.

    The message lists every path that was searched, so the failure says what to
    do next instead of only reporting that something is absent.
    """


def repository_root() -> Path | None:
    """The repository root, found by walking up; ``None`` if there is none.

    A directory is taken as the repository root when it contains a ``papers/``
    directory *and* a ``Models/`` directory. Fixed-depth arithmetic is not used:
    the depth of a model package is the repository's business, not the model's.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "papers").is_dir() and (candidate / "Models").is_dir():
            return candidate
    return None


def pdf_candidates() -> tuple[tuple[str, Path], ...]:
    """Every place the article PDF is looked for, in priority order."""
    out: list[tuple[str, Path]] = []
    root = repository_root()
    if root is not None:
        out.append(("repository papers/", root / "papers" / PDF_FILENAME))
    out.append(("package-local", DATA_DIR.parent.parent / PDF_FILENAME))
    return tuple(out)


def resolve_source_pdf() -> tuple[Path, str]:
    """The article PDF to regenerate page text from, and which rule matched."""
    for rule, path in pdf_candidates():
        if path.is_file():
            return path, rule
    searched = "\n  ".join(f"[{rule}] {path}" for rule, path in pdf_candidates())
    raise SourcePdfNotFound(
        "could not locate the article PDF needed to regenerate the page text.\n"
        f"Searched:\n  {searched}\n"
        "Put a copy beside the package as " + PDF_FILENAME + ", or pass an "
        "explicit pdf_path= to rebuild_paper_pages()."
    )


def rebuild_paper_pages(
    pdf_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[int, str]:
    """Re-extract page text from the article PDF.

    Needs pypdf, which is not a runtime dependency. The model never calls this;
    it exists so the checked-in text can be rebuilt from the published PDF by
    hand. `output_path` defaults to the package's own ``data/paper_pages.json``.
    """
    from pypdf import PdfReader

    if pdf_path is None:
        pdf_path, _rule = resolve_source_pdf()
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
