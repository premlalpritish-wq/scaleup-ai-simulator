"""Report what the supplementary document actually contains.

    python composition/tools/inspect_supplementary.py

Enumerates every paragraph and table in ``mmc1.docx`` so the recovery report can
state exactly what was searched and what was found, rather than asserting an absence.

This exists because "the data are not there" and "nobody looked" look identical from
the outside. Every table is dumped with its cells, and every embedded image is listed
with its pixel dimensions, so the search is auditable.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "data" / "ganjave2022" / "source_data"
DOCX = SOURCE_DIR / "mmc1_supplementary.docx"
OUT = SOURCE_DIR / "supplementary_inventory.json"

NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def paragraph_text(element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{NS_W}t")).strip()


def main() -> int:
    import xml.etree.ElementTree as ET

    if not DOCX.exists():
        print(f"{DOCX} is absent; nothing to inspect.")
        return 1

    document = zipfile.ZipFile(DOCX)
    root = ET.fromstring(document.read("word/document.xml"))
    body = root.find(f"{NS_W}body")

    paragraphs: list[str] = []
    tables: list[dict] = []
    order: list[str] = []

    for child in body:
        if child.tag == f"{NS_W}p":
            text = paragraph_text(child)
            if text:
                paragraphs.append(text)
                order.append(f"P: {text[:160]}")
        elif child.tag == f"{NS_W}tbl":
            rows = []
            for row in child.findall(f"{NS_W}tr"):
                cells = [
                    paragraph_text(cell) for cell in row.findall(f"{NS_W}tc")
                ]
                rows.append(cells)
            tables.append({"n_rows": len(rows), "rows": rows})
            order.append(f"TABLE ({len(rows)} rows): {rows[0] if rows else []}")

    # Images, with pixel dimensions where the format exposes them.
    images: list[dict] = []
    for name in document.namelist():
        if not name.startswith("word/media/"):
            continue
        record = {"part": name, "size_bytes": document.getinfo(name).file_size}
        data = document.read(name)
        if name.endswith((".png", ".jpg", ".jpeg", ".gif")):
            try:
                from PIL import Image

                with Image.open(io.BytesIO(data)) as image:
                    record["pixels"] = list(image.size)
                    record["format"] = image.format
            except Exception as error:  # noqa: BLE001 - reported, not swallowed
                record["pixels"] = None
                record["note"] = f"could not read: {error}"
        images.append(record)

    # Anything that could be a data file.
    data_parts = [
        name for name in document.namelist()
        if name.lower().endswith((".xlsx", ".xls", ".csv", ".tsv", ".txt", ".dat"))
    ]

    inventory = {
        "document": DOCX.name,
        "n_paragraphs": len(paragraphs),
        "n_tables": len(tables),
        "paragraphs": paragraphs,
        "tables": tables,
        "images": images,
        "spreadsheet_or_data_parts": data_parts,
        "charts": [n for n in document.namelist() if "/charts/" in n],
    }

    OUT.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")

    print(f"paragraphs: {len(paragraphs)}   tables: {len(tables)}   "
          f"images: {len(images)}   data parts: {len(data_parts)}")
    print()
    print("--- captions / headings ---")
    for line in order:
        if line.startswith("TABLE"):
            print("  ", line[:200])
        elif re.match(r"^(Figure|Table|Fig\.)\s", line[3:].strip()) or \
                "supplement" in line.lower():
            print("  ", line[:200])
    print()
    print("--- tables, full ---")
    for index, table in enumerate(tables):
        print(f"  Table {index + 1}: {table['n_rows']} rows")
        for row in table["rows"][:14]:
            print("     ", " | ".join(c[:38] for c in row))
    print()
    print("--- images ---")
    for image in images:
        print(f"  {image['part']:<28} {image['size_bytes']:>9} bytes  "
              f"{image.get('pixels')}")
    if data_parts:
        print("\n  SPREADSHEET/DATA PARTS FOUND:", data_parts)
    else:
        print("\n  no spreadsheet or data files embedded in the supplementary")

    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
