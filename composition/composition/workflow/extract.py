"""Full-text extraction with section locators.

JATS XML and plain text use the standard library.  PDF extraction is optional:
``pypdf`` is imported only when a PDF is actually read.  The project promises no
third-party runtime dependencies, so a missing ``pypdf`` is reported as an
acquisition failure rather than silently producing an empty document.

The extractor never paraphrases.  It normalises whitespace (runs of spaces,
tabs and newlines become one space) so a quote can be matched across a line
break, but it preserves every character of the source otherwise.  The encoder
then verifies each quote against this text.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .schema import SourceText, TextSection


class ExtractionError(RuntimeError):
    """The document could not be read as text."""


def normalise_whitespace(text: str) -> str:
    return " ".join(str(text).split())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text_of(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return normalise_whitespace("".join(element.itertext()))


@dataclass
class _RawSection:
    title: str
    path: str
    text: str


def _jats_sections(root: ET.Element) -> list[_RawSection]:
    body = root.find(".//body")
    if body is None:
        return []
    out: list[_RawSection] = []

    def own_text(element: ET.Element) -> str:
        pieces: list[str] = []
        for child in element:
            name = _local_name(child.tag)
            if name in ("sec", "title"):
                continue
            if name in ("p", "list", "list-item", "table-wrap", "fig", "caption",
                        "disp-quote", "statement", "boxed-text", "supplementary-material"):
                value = _text_of(child)
                if value:
                    pieces.append(value)
        return normalise_whitespace(" ".join(pieces))

    def walk(section: ET.Element, parent_path: str) -> None:
        title = _text_of(section.find("title"))
        path = f"{parent_path} > {title}" if parent_path and title else (title or parent_path)
        text = own_text(section)
        if text:
            out.append(_RawSection(title=title or parent_path or "Body", path=path or "Body",
                                   text=text))
        for child in section:
            if _local_name(child.tag) == "sec":
                walk(child, path)

    body_text = own_text(body)
    if body_text:
        out.append(_RawSection(title="Body", path="Body", text=body_text))
    for child in body:
        if _local_name(child.tag) == "sec":
            walk(child, "")
    if not out:
        whole = _text_of(body)
        if whole:
            out.append(_RawSection(title="Body", path="Body", text=whole))
    return out


def _build_source_text(
    source_id: str,
    title: str,
    raw_sections: Iterable[_RawSection],
    extraction_method: str,
    diagnostics: tuple[str, ...] = (),
) -> SourceText:
    sections: list[TextSection] = []
    cursor = 0
    chunks: list[str] = []
    for raw in raw_sections:
        text = normalise_whitespace(raw.text)
        if not text:
            continue
        if chunks:
            cursor += 1  # the single space joining chunks
        start = cursor
        chunks.append(text)
        cursor += len(text)
        sections.append(
            TextSection(
                title=raw.title,
                path=raw.path,
                text=text,
                start=start,
                end=start + len(text),
            )
        )
    full = " ".join(chunks)
    return SourceText(
        source_id=source_id,
        title=title,
        text=full,
        sections=tuple(sections),
        extraction_method=extraction_method,
        diagnostics=diagnostics,
    )


def extract_jats(path: Path, source_id: str) -> SourceText:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ExtractionError(f"{path} is not well-formed XML: {exc}") from None
    title = _text_of(root.find(".//article-title")) or path.stem
    return _build_source_text(
        source_id, title, _jats_sections(root), "jats_xml_stdlib"
    )


def extract_pdf(path: Path, source_id: str) -> SourceText:
    try:
        from pypdf import PdfReader  # noqa: PLC0415 - optional dependency
    except ImportError:
        raise ExtractionError(
            "PDF extraction requires the optional 'pypdf' package. The project's "
            "runtime has no third-party dependencies, so install pypdf or supply "
            "the source as JATS XML / plain text."
        ) from None
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - pypdf raises several types
        raise ExtractionError(f"{path} could not be opened as a PDF: {exc}") from None
    raw: list[_RawSection] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = normalise_whitespace(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            raw.append(_RawSection(f"Page {index}", f"Page {index}",
                                   f"[page {index} extraction failed: {exc}]"))
            continue
        if text:
            raw.append(_RawSection(f"Page {index}", f"Page {index}", text))
    if not raw:
        raise ExtractionError(f"{path} produced no extractable text")
    return _build_source_text(
        source_id, path.stem, raw, "pdf_pypdf",
        diagnostics=(
            "PDF text is positional; tables and figures may be reordered. "
            "Quotes are still verified against the extracted characters.",
        ),
    )


def extract_text_file(path: Path, source_id: str) -> SourceText:
    text = path.read_text(encoding="utf-8")
    paragraphs = [
        normalise_whitespace(p) for p in re.split(r"\n\s*\n", text) if p.strip()
    ]
    raw = [
        _RawSection(f"Paragraph {i}", f"Paragraph {i}", p)
        for i, p in enumerate(paragraphs, start=1)
    ]
    return _build_source_text(source_id, path.stem, raw, "plain_text_stdlib")


def extract_document(path: Path, source_id: str) -> SourceText:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xml", ".jats", ".nxml"):
        return extract_jats(path, source_id)
    if suffix == ".pdf":
        return extract_pdf(path, source_id)
    if suffix in (".txt", ".md", ".text"):
        return extract_text_file(path, source_id)
    raise ExtractionError(
        f"unsupported source format {suffix!r}; supported: .xml, .jats, .nxml, "
        f".pdf, .txt, .md"
    )


def find_quote(document: SourceText, quote: str) -> tuple[int, int, TextSection | None]:
    """Locate a verbatim quote, or raise.

    The comparison is exact after whitespace normalisation.  A quote that is not
    present is an encoder failure, never a reason to soften the wording until it
    matches.
    """
    needle = normalise_whitespace(quote)
    if not needle:
        raise ExtractionError("an empty quote cannot be verified")
    start = document.text.find(needle)
    if start < 0:
        raise ExtractionError(
            f"quote not found in {document.source_id}: {needle[:160]!r}"
        )
    end = start + len(needle)
    section = None
    for candidate in document.sections:
        if candidate.start <= start < candidate.end:
            if section is None or (candidate.end - candidate.start) < (
                section.end - section.start
            ):
                section = candidate
    return start, end, section
