"""Bibliographic source and evidence helpers for Zielinski et al. 2019."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from scaleup_ai import EvidenceRef

SOURCE_ID = "zielinski2019"

CITATION = (
    "M. Zielinski, A. Romanik-Chruscielewska, D. Mikiewicz, N. Lukasiewicz, "
    "I. Sokolowska, J. Antosik, A. Sobolewska-Ruta, A. Bierczynska-Krzysik, "
    "P. Zaleski, A. Plucienniczak, 'Expression and purification of recombinant "
    "human insulin from E. coli 20 strain', Protein Expression and Purification "
    "157 (2019) 63-69."
)
DOI = "10.1016/j.pep.2019.02.002"

#: The article occupies pp. 63-69; the PDF page and the printed page differ by 62.
PRINTED_PAGE_OFFSET = 62

DATA_DIR = Path(__file__).parent / "data"


def ev(
    pdf_page: int,
    *,
    section: str | None = None,
    figure: str | None = None,
    quote: str | None = None,
) -> EvidenceRef:
    """Build an EvidenceRef for a location in the paper.

    `pdf_page` is 1-based within the article PDF; the printed journal page is
    derived from it and cross-checked by `EvidenceRef.__post_init__`.
    """
    return EvidenceRef(
        source_id=SOURCE_ID,
        pdf_page=pdf_page,
        printed_page=pdf_page + PRINTED_PAGE_OFFSET,
        section=section,
        figure=figure,
        quote=quote,
    )


# --------------------------------------------------------------------------- #
# digitized figure data
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def fig3_trajectory() -> dict:
    """The digitized Fig. 3 growth trajectory with its declared uncertainty."""
    path = DATA_DIR / "fig3_growth_trajectory.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# source text, used to verify that citations actually say what we claim
# --------------------------------------------------------------------------- #

#: models/data -> models -> Zielinski -> Models -> pilot ; then papers/
PAPER_PDF = DATA_DIR.parents[3] / "papers" / "Zielinski et al 2019.pdf"


@lru_cache(maxsize=1)
def paper_pages() -> dict[int, str]:
    """Extracted text of each article PDF page, keyed by 1-based PDF page.

    This exists so citations can be checked mechanically rather than trusted: the
    test suite asserts that every `reported` value appears verbatim on the page
    the model cites. See `rebuild_paper_pages` to regenerate from the PDF.
    """
    path = DATA_DIR / "paper_pages.json"
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def rebuild_paper_pages(pdf_path: Path | None = None) -> dict[int, str]:
    """Re-extract page text from the article PDF into the verification dataset."""
    import re
    import unicodedata

    from pypdf import PdfReader

    pdf = Path(pdf_path or PAPER_PDF)
    reader = PdfReader(str(pdf))

    def normalise(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        for src, dst in (("ł", "l"), ("ø", "o"), ("ń", "n"), ("ś", "s"),
                         ("ź", "z"), ("ż", "z"), ("ć", "c"), ("ę", "e"),
                         ("ą", "a"), ("ó", "o"), ("ń", "n")):
            text = text.replace(src, dst)
        # the paper prints thousands separators ("15,000 x g"); drop them so a
        # numeric citation check is not defeated by formatting
        text = text.replace(",", "")
        return re.sub(r"\s+", " ", text)

    pages = {i: normalise(p.extract_text() or "") for i, p in enumerate(reader.pages, 1)}
    out = DATA_DIR / "paper_pages.json"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump({str(k): v for k, v in pages.items()}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return pages