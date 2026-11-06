"""Build the bundled bilingual ICD catalogue from downloaded source tables.

The generated gzip TSV is deterministic and intentionally contains only the
fields needed by the patient-card lookup. Source archives are not committed.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import re
from pathlib import Path


def _clean_title(value: str | None) -> str:
    return re.sub(r"^(?:-\s*)+", "", (value or "").strip()).strip()


def _read_icd11(path: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            code = (row.get("Code") or "").strip()
            if not code or row.get("ClassKind") != "category":
                continue
            title_en = _clean_title(row.get("TitleEN"))
            title_ru = _clean_title(row.get("Title"))
            if title_en:
                result[code] = (title_en, title_ru)
    return result


def _read_icd10_ru(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter=";"):
            code = row["code"].strip()
            title = row["name"].strip()
            if code and title:
                result[code] = title
    return result


def _read_icd10_en(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.reader(source, delimiter=";"):
            code = row[5].removesuffix(".-").strip()
            title = row[8].strip()
            if code and title:
                result[code] = title
    return result


def build(args: argparse.Namespace) -> None:
    icd11 = _read_icd11(args.icd11_ru)
    icd10_ru = _read_icd10_ru(args.icd10_ru)
    icd10_en = _read_icd10_en(args.icd10_en)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(("classification", "code", "title_en", "title_ru"))
        for code in sorted(icd10_ru.keys() | icd10_en.keys()):
            # Releases differ in a small number of national/optional codes.
            # Keep every code and let the application fall back to the title
            # available in the other language when a translation is absent.
            writer.writerow(("ICD-10", code, icd10_en.get(code, ""), icd10_ru.get(code, "")))
        for code, (title_en, title_ru) in icd11.items():
            writer.writerow(("ICD-11", code, title_en, title_ru))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--icd11-ru", type=Path, required=True)
    parser.add_argument("--icd10-ru", type=Path, required=True)
    parser.add_argument("--icd10-en", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
