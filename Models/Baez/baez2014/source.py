"""Bibliographic source and evidence helpers for Baez et al. (2014).

One publication, cited once, with its printed page for every value.

**Printed page == PDF page for this article.** The article is published as
`Microbial Cell Factories 2014, 13:50`, pages 1-7, and each page carries the
running footer ``Baez et al. Microbial Cell Factories 2014, 13:50 Page N of
7``. `PAGE_COUNT` is 7 and `FIRST_PRINTED_PAGE` is 1, so `EvidenceRef` can
check a printed-page reference arithmetically instead of trusting it. The
footer is itself asserted against the extracted page text in the test suite.

`paper_pages()` holds the extracted text of every page so that a citation can
be *checked* rather than trusted: the test suite asserts that each reported
value appears verbatim on the printed page the model cites. The PDFs under
`papers/` are publications by other authors and are deliberately not read at
run time; only this extracted text is. Regenerate with

    python -c "from baez2014.source import rebuild_paper_pages; rebuild_paper_pages()"

run from ``Models/Baez``, which needs pypdf and is never called by the model.
It writes to `baez2014/data/paper_pages.json` unless an explicit
`output_path=` is given.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SOURCE_ID = "baez2014"

AUTHORS = ("Antonino Baez", "Nadim Majdalani", "Joseph Shiloach")

TITLE = "Production of recombinant protein by a novel oxygen-induced system in Escherichia coli"

JOURNAL = "Microbial Cell Factories"
YEAR = 2014
VOLUME = "13"
ARTICLE_NUMBER = "50"
PAGES = "1-7"
DOI = "10.1186/1475-2859-13-50"

CITATION = (
    "A. Baez, N. Majdalani, J. Shiloach, 'Production of recombinant protein "
    "by a novel oxygen-induced system in Escherichia coli', Microbial Cell "
    "Factories 2014, 13:50."
)

#: The article is paginated 1-7 and the PDF reproduces those numbers, so the
#: printed page and the 1-based PDF page are the same integer.
FIRST_PRINTED_PAGE = 1
PAGE_COUNT = 7

DATA_DIR = Path(__file__).parent / "data"

#: Running footer that states the printed page number on every page.
FOOTER_TEMPLATE = "Page %d of %d"


def citation_for(printed_page: int, *, section: str | None = None) -> str:
    """The citation string used on every record, page-qualified."""
    bits = [CITATION.rstrip("."), f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def reference(printed_page: int, *, section: str | None = None) -> str:
    """Short form used where a full citation would be redundant."""
    bits = ["Baez et al. 2014", f"p. {printed_page}"]
    if section:
        bits.append(section)
    return ", ".join(bits)


def footer_for(printed_page: int) -> str:
    return FOOTER_TEMPLATE % (printed_page, PAGE_COUNT)


@lru_cache(maxsize=1)
def paper_pages() -> dict[int, str]:
    """Extracted text of each PDF page, keyed by 1-based PDF page."""
    path = DATA_DIR / "paper_pages.json"
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def page_text(printed_page: int) -> str:
    """Normalised text of one printed page, or '' when it is not extracted."""
    return paper_pages().get(printed_page, "")


def normalise(text: str) -> str:
    """Fold a page of extracted text into the form citations are checked in.

    Two classes of difference are removed: unicode decomposition, so that
    characters with or without a combining mark compare equal, and the
    thousands separators the typesetter inserts into large numbers. Whitespace
    is collapsed so a line break in the PDF column is not a difference.
    """
    text = unicodedata.normalize("NFKD", text)
    for src, dst in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                     ("‐", "-"), ("‑", "-"), ("–", "-"), ("—", "-"),
                     (" ", " "), ("−", "-")):
        text = text.replace(src, dst)
    text = text.replace(",", "")
    return re.sub(r"\s+", " ", text)


def _loose(text: str) -> str:
    """Reduce text to its alphanumeric characters, for hyphen-tolerant matching."""
    return re.sub(r"[^0-9A-Za-z]", "", text)


def page_contains(printed_page: int, fragment: str) -> bool:
    """True when `fragment` appears on the printed page, verbatim or not.

    A strict substring match on the normalised page text is tried first. If it
    fails, the comparison is retried with hyphens and spaces removed from both
    sides, which is what a typesetter's line-end hyphenation needs: the paper
    prints "air satur-" at the end of one line and "ation" at the start of the
    next, so a faithful quote of "air saturation" is not a contiguous substring
    of the extracted text.

    This weakens the check to word-level rather than character-level, which is
    why the numeric values are always checked strictly (see
    `tests/test_citation_fidelity.py`).
    """
    page = page_text(printed_page)
    if not page:
        return False
    if fragment in page:
        return True
    return _loose(fragment) in _loose(page)


# --------------------------------------------------------------------------- #
# locating the article PDF
# --------------------------------------------------------------------------- #

PDF_FILENAME = "Baez et al 2014.pdf"


class SourcePdfNotFound(FileNotFoundError):
    """No copy of the article PDF could be located.

    The message lists every path that was searched, so the failure says what
    to do next instead of only reporting that something is absent.
    """


def repository_root() -> Path | None:
    """The repository root, found by walking up; ``None`` if there is none.

    This package sits at ``<repo>/Models/Baez``, so the repository's own
    ``papers/`` directory is two levels above it -- but the model must not
    hard-code that depth. Fixed-depth arithmetic (``parents[n]``) is exactly
    what broke when this package was relocated, and the depth of a model
    package is the repository's business, not the model's.

    A directory is taken as the repository root when it contains a ``papers/``
    directory *and* a ``Models/`` directory: both are present in every copy of
    this layout, whatever depth the package itself happens to sit at.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "papers").is_dir() and (candidate / "Models").is_dir():
            return candidate
    return None


def pdf_candidates() -> tuple[tuple[str, Path], ...]:
    """Every place the article PDF is looked for, in priority order.

    1. ``<repository root>/papers/Baez et al 2014.pdf`` -- the canonical copy;
    2. ``<package>/Baez et al 2014.pdf`` -- the package-local copy, which is the
       repository convention for reference papers (both sibling model packages
       keep a copy beside their own source).
    """
    out: list[tuple[str, Path]] = []
    root = repository_root()
    if root is not None:
        out.append(("repository papers/", root / "papers" / PDF_FILENAME))
    out.append(("package-local", DATA_DIR.parent.parent / PDF_FILENAME))
    return tuple(out)


def resolve_source_pdf() -> tuple[Path, str]:
    """The article PDF to regenerate page text from, and which rule matched.

    Selection is deterministic: the first existing candidate in
    `pdf_candidates()` wins, and the rule that selected it is returned, so the
    choice is visible rather than implied.
    """
    for rule, path in pdf_candidates():
        if path.is_file():
            return path, rule
    searched = "\n  ".join(f"[{rule}] {path}" for rule, path in pdf_candidates())
    raise SourcePdfNotFound(
        "could not locate the article PDF needed to regenerate the page text.\n"
        f"Searched:\n  {searched}\n"
        "Put a copy at <repository root>/papers/" + PDF_FILENAME
        + " (the canonical location, matching the other model packages), or "
        "pass an explicit pdf_path= to rebuild_paper_pages()."
    )


#: The canonical copy, resolved once. ``None`` when the package is not inside a
#: repository checkout.
PAPER_PDF = (repository_root() / "papers" / PDF_FILENAME) if repository_root() else None


def rebuild_paper_pages(
    pdf_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[int, str]:
    """Re-extract page text from the article PDF.

    Needs pypdf, which is not a runtime dependency of this package. The model
    never calls this; it exists so the checked-in text can be rebuilt from the
    published PDF by hand.

    `output_path` defaults to the package's own ``data/paper_pages.json``.
    Pass an explicit path to write elsewhere: the test suite does exactly that,
    so regenerating can never overwrite the tracked snapshot by accident.
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