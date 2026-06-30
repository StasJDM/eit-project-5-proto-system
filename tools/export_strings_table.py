#!/usr/bin/env python3
"""Export all STRINGS from app/i18n.py to DOCX and Markdown tables."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.i18n import STRINGS  # noqa: E402

DOCX_PATH = ROOT / "docs" / "все_строки_приложения.docx"
MD_PATH = ROOT / "docs" / "все_строки_приложения.md"

HEADERS = ["Термин (RU)", "Русский", "English", "中文", "Tiếng Việt"]

# CJK-capable fonts (verified on macOS; Word substitutes if missing)
CJK_FONTS = ("Songti SC", "Arial Unicode MS", "STSong", "SimSun", "Microsoft YaHei")


def _pick_cjk_font() -> str:
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in CJK_FONTS:
            if name in available:
                return name
    except Exception:
        pass
    return "Arial Unicode MS"

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _display(text: str) -> str:
    return text.replace("\n", " ")


def _rows() -> list[tuple[str, str, str, str, str]]:
    out = []
    for key in sorted(STRINGS.keys(), key=lambda k: STRINGS[k]["ru"].casefold()):
        entry = STRINGS[key]
        ru = _display(entry["ru"])
        out.append((
            ru,
            ru,
            _display(entry["en"]),
            _display(entry["zh"]),
            _display(entry["vi"]),
        ))
    return out


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def export_md(rows: list[tuple[str, ...]]) -> None:
    lines = [
        "# Все строки приложения",
        "",
        f"> Источник: `app/i18n.py` ({len(rows)} строк). "
        "Сгенерировано `tools/export_strings_table.py`.",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "| " + " | ".join(["---"] * len(HEADERS)) + " |",
    ]
    for row in rows:
        cells = [_escape_md_cell(c) for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def _set_run_font(run, latin_font: str, cjk_font: str, size_pt: int, bold: bool = False):
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run.bold = bold
    run.font.size = Pt(size_pt)
    run.font.name = latin_font
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.rFonts
    if rFonts is None:
        from docx.oxml import OxmlElement
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), latin_font)
    rFonts.set(qn("w:hAnsi"), latin_font)
    rFonts.set(qn("w:cs"), latin_font)
    rFonts.set(qn("w:eastAsia"), cjk_font)


def _write_cell(cell, text: str, *, bold: bool = False, size: int = 9, cjk_font: str = "Times New Roman"):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    _set_run_font(run, "Times New Roman", cjk_font, size, bold=bold)


def verify_chinese(rows: list[tuple[str, ...]]) -> dict:
    """Collect unique CJK characters and sample strings for verification."""
    chars: set[str] = set()
    samples: list[str] = []
    for row in rows:
        zh = row[3]
        if zh:
            samples.append(zh)
            chars.update(_CJK_RE.findall(zh))
    return {
        "unique_cjk_chars": len(chars),
        "sample_strings": samples[:8],
        "sample_chars": "".join(sorted(chars)[:40]),
    }


def export_docx(rows: list[tuple[str, ...]]) -> None:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    cjk_font = _pick_cjk_font()
    doc = Document()
    section = doc.sections[0]
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.0)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = title.add_run("Все строки приложения")
    tr.bold = True
    tr.font.size = Pt(14)
    tr.font.name = "Times New Roman"

    sub = doc.add_paragraph(
        f"Источник: app/i18n.py — {len(rows)} строк. "
        f"Китайский: шрифт {cjk_font} (eastAsia)."
    )
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in sub.runs:
        run.font.size = Pt(10)

    doc.add_paragraph()

    table = doc.add_table(rows=1 + len(rows), cols=len(HEADERS))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(HEADERS):
        font = cjk_font if j == 3 else "Times New Roman"
        _write_cell(table.rows[0].cells[j], h, bold=True, size=9, cjk_font=font)

    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            use_cjk = j == 3 or _CJK_RE.search(val)
            font = cjk_font if use_cjk else "Times New Roman"
            _write_cell(
                table.rows[i].cells[j],
                val,
                bold=False,
                size=8,
                cjk_font=font,
            )

    widths = [Cm(3.8), Cm(4.2), Cm(4.2), Cm(3.5), Cm(4.0)]
    for tbl_row in table.rows:
        for j, w in enumerate(widths):
            tbl_row.cells[j].width = w

    doc.save(DOCX_PATH)


def main() -> None:
    rows = _rows()
    cjk_font = _pick_cjk_font()
    export_md(rows)
    export_docx(rows)
    info = verify_chinese(rows)
    print(f"MD:   {MD_PATH}")
    print(f"DOCX: {DOCX_PATH}")
    print(f"Rows: {len(rows)}")
    print(f"CJK font: {cjk_font}")
    print(f"CJK:  {info['unique_cjk_chars']} unique characters")
    print(f"Sample chars: {info['sample_chars']}")
    print("Sample zh strings:")
    for s in info["sample_strings"]:
        print(f"  - {s}")


if __name__ == "__main__":
    main()
