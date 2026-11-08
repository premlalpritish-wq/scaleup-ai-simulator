"""Locating and reading the article's printed equations.

Two things about this PDF drive the design.

First, the text layer is not a reliable witness for mathematical typography:
it drops fraction bars, so ``100/C*`` comes out of it as ``100C*``. That single
omission is the whole reason this package carried a wrong oxygen equation for a
while. Any transcription check that reads the text layer therefore cannot
settle a question about a fraction, and must say so.

Second, the glyph geometry *can* settle it. In the rendered page, the
numerator of a fraction sits on a different baseline from its denominator, while
tokens printed side by side share a baseline to within a point or so. So the
vertical offset between two tokens is evidence, and it is evidence that can be
re-measured rather than remembered.

Everything here is optional: it needs the article PDF and PyMuPDF. The package
runs without them, and the tests that use this module state their dependence
loudly rather than passing silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PaperNotAvailable(RuntimeError):
    """The article PDF or a PDF reader is unavailable."""


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def repository_root() -> Path:
    """Walk upwards for the marker that identifies the checkout root.

    Structural, not positional: the depth from the repository root to this file
    is not something to hard-code as ``parents[n]``.
    """
    for candidate in package_root().parents:
        if (candidate / "composition" / "composition" / "adapters" / "__init__.py").is_file():
            return candidate
        if (candidate / "Models").is_dir() and (candidate / "composition").is_dir():
            return candidate
    raise PaperNotAvailable(
        "could not locate the repository root by walking up from "
        f"{package_root()}; expected to find a Models/ and composition/ pair"
    )


def pdf_candidates() -> tuple[Path, ...]:
    """Places the article PDF may live, most authoritative first."""
    root = package_root()
    out: list[Path] = []
    try:
        out.append(repository_root() / "papers" / "Ganjave et al 2022.pdf")
    except PaperNotAvailable:
        pass
    out.append(root.parent / "Ganjave et al 2022.pdf")
    out.append(root / "Ganjave et al 2022.pdf")
    seen: set[Path] = set()
    unique = []
    for path in out:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return tuple(unique)


def resolve_source_pdf() -> Path:
    for candidate in pdf_candidates():
        if candidate.is_file():
            return candidate
    raise PaperNotAvailable(
        "the article PDF was not found; looked in "
        f"{[str(p) for p in pdf_candidates()]}"
    )


@dataclass(frozen=True)
class Token:
    """A word from the page, with its box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def baseline(self) -> float:
        return self.y1


def page_words(pdf_path: Path, page_index: int) -> tuple[Token, ...]:
    """All words on a page, as tokens with their boxes."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise PaperNotAvailable(
            "PyMuPDF is required to read the article's glyph geometry; install "
            "it to run the PDF-backed tests (it is not a runtime dependency)"
        ) from exc

    with pymupdf.open(pdf_path) as doc:
        page = doc[page_index]
        return tuple(
            Token(text=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3])
            for w in page.get_text("words")
        )


def equation_label_height(pdf_path: Path, page_index: int, label: str,
                          column: str) -> float:
    """Vertical centre of a right-margin equation label in one column.

    ``column`` is ``"left"`` or ``"right"``; the two columns of this two-column
    layout put their equation numbers at different x positions, and the label is
    the most reliable anchor for "where is equation N".
    """
    tokens = page_words(pdf_path, page_index)
    page_width = 595.276  # A4 in points, as the article is typeset
    mid = page_width / 2
    hits = [
        t for t in tokens
        if t.text == label
        and ((column == "right" and t.x0 > mid) or (column == "left" and t.x0 < mid))
    ]
    if not hits:
        raise PaperNotAvailable(
            f"equation label {label!r} not found in the {column} column of "
            f"printed page {page_index + 1}"
        )
    return min(hits, key=lambda t: t.y0).y0


def tokens_near(pdf_path: Path, page_index: int, label: str, column: str,
                above: float = 14.0, below: float = 20.0) -> tuple[Token, ...]:
    """Tokens in the vertical band that holds a numbered equation."""
    centre = equation_label_height(pdf_path, page_index, label, column)
    return tuple(
        t for t in page_words(pdf_path, page_index)
        if centre - above <= t.y0 <= centre + below
    )


def baseline_spread(tokens: tuple[Token, ...], exclude: tuple[str, ...] = ()) -> float:
    """How tightly a set of tokens shares a baseline.

    Tokens printed on one line agree closely; a stacked fraction does not. Used
    to show that ``100`` and ``C*`` are on different lines while their
    neighbours are not.
    """
    kept = [t for t in tokens if t.text not in exclude]
    if len(kept) < 2:
        return 0.0
    baselines = sorted(t.baseline for t in kept)
    return baselines[-1] - baselines[0]


def _normalise(text: str) -> str:
    """Strip the junk a math font leaves in front of a token.

    The text layer renders the italic Greek and some operators as ``?``, and
    glues them to the following token: the numerator of the printed factor comes
    out as ``'?100'``. Comparing on the alphanumeric tail is enough to find the
    box, and the *geometry* -- which is what actually settles the question -- is
    unaffected by the substitution.
    """
    out = "".join(ch for ch in text if ch.isalnum() or ch in "*.()+-/")
    while out and not out[0].isalnum():
        out = out[1:]
    return out


def fraction_numerator_above(pdf_path: Path, page_index: int, label: str,
                             column: str, numerator: str, denominator: str,
                             threshold: float = 3.0) -> dict[str, Any]:
    """Is `numerator` stacked above `denominator`, as a fraction requires?

    Returns the measured offsets and the verdict, so a caller can inspect the
    numbers rather than trusting a boolean.
    """
    tokens = tokens_near(pdf_path, page_index, label, column)
    num = [t for t in tokens if _normalise(t.text) == numerator]
    den = [t for t in tokens if _normalise(t.text) == denominator]
    if not num or not den:
        raise PaperNotAvailable(
            f"could not locate {numerator!r} / {denominator!r} in the band of "
            f"equation {label} on printed page {page_index + 1}"
        )
    num_t = min(num, key=lambda t: t.y0)
    den_t = min(den, key=lambda t: t.y0)
    offset = den_t.y0 - num_t.y0
    return {
        "equation": label,
        "printed_page": page_index + 1,
        "numerator_text": num_t.text,
        "numerator_y0": num_t.y0,
        "numerator_y1": num_t.y1,
        "denominator_text": den_t.text,
        "denominator_y0": den_t.y0,
        "denominator_y1": den_t.y1,
        "vertical_offset_pt": offset,
        "threshold_pt": threshold,
        "stacked": offset > threshold,
    }


__all__ = [
    "PaperNotAvailable",
    "Token",
    "baseline_spread",
    "equation_label_height",
    "fraction_numerator_above",
    "package_root",
    "page_words",
    "pdf_candidates",
    "repository_root",
    "resolve_source_pdf",
    "tokens_near",
]